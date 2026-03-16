from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from src.apps.cross_market.models import SectorMetric
from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.candles import CandlePoint
from src.apps.market_data.repositories import CandleRepository, CoinRepository
from src.apps.patterns.cache import read_cached_regime_async
from src.apps.patterns.domain.base import PatternDetector
from src.apps.patterns.domain.detectors import build_pattern_detectors
from src.apps.patterns.domain.lifecycle import lifecycle_allows_detection
from src.apps.patterns.domain.registry import PATTERN_CATALOG, SUPPORTED_PATTERN_FEATURES
from src.apps.patterns.domain.success import GLOBAL_MARKET_REGIME, PatternSuccessSnapshot, normalize_market_regime
from src.apps.patterns.models import DiscoveredPattern, PatternFeature, PatternRegistry, PatternStatistic
from src.apps.patterns.query_services import PatternQueryService
from src.apps.signals.models import Signal, SignalHistory, Strategy
from src.core.db.persistence import PersistenceComponent
from src.core.db.uow import BaseAsyncUnitOfWork


class PatternTaskBase(PersistenceComponent):
    def __init__(self, uow: BaseAsyncUnitOfWork, *, service_name: str) -> None:
        super().__init__(
            uow.session,
            component_type="service",
            domain="patterns",
            component_name=service_name,
        )
        self._uow = uow
        self._coins = CoinRepository(uow.session)
        self._candles = CandleRepository(uow.session)
        self._queries = PatternQueryService(uow.session)

    async def _ensure_catalog_metadata(self) -> None:
        feature_stmt = insert(PatternFeature).values(
            [{"feature_slug": slug, "enabled": True} for slug in SUPPORTED_PATTERN_FEATURES]
        )
        await self.session.execute(feature_stmt.on_conflict_do_nothing(index_elements=["feature_slug"]))
        registry_stmt = insert(PatternRegistry).values(
            [
                {
                    "slug": item.slug,
                    "category": item.category,
                    "enabled": True,
                    "cpu_cost": item.cpu_cost,
                    "lifecycle_state": "ACTIVE",
                }
                for item in PATTERN_CATALOG
            ]
        )
        await self.session.execute(registry_stmt.on_conflict_do_nothing(index_elements=["slug"]))
        await self._uow.flush()

    async def _feature_enabled(self, feature_slug: str) -> bool:
        await self._ensure_catalog_metadata()
        value = await self.session.scalar(
            select(PatternFeature.enabled).where(PatternFeature.feature_slug == feature_slug).limit(1)
        )
        return bool(value) if value is not None else False

    async def _load_active_detectors(self, *, timeframe: int) -> list[PatternDetector]:
        await self._ensure_catalog_metadata()
        rows = (
            await self.session.execute(
                select(PatternRegistry.slug, PatternRegistry.enabled, PatternRegistry.lifecycle_state)
            )
        ).all()
        enabled_slugs = {
            str(row.slug) for row in rows if lifecycle_allows_detection(str(row.lifecycle_state), bool(row.enabled))
        }
        return [
            detector
            for detector in build_pattern_detectors()
            if detector.slug in enabled_slugs and timeframe in detector.supported_timeframes
        ]

    async def _fetch_candle_points(
        self,
        *,
        coin_id: int,
        timeframe: int,
        limit: int,
    ) -> list[CandlePoint]:
        return await self._candles.fetch_points(coin_id=coin_id, timeframe=timeframe, limit=limit)

    async def _fetch_candle_points_between(
        self,
        *,
        coin_id: int,
        timeframe: int,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CandlePoint]:
        return await self._candles.fetch_points_between(
            coin_id=coin_id,
            timeframe=timeframe,
            window_start=window_start,
            window_end=window_end,
        )

    async def _pattern_success_snapshot(
        self,
        *,
        slug: str,
        timeframe: int,
        market_regime: str | None,
        snapshot_cache: dict[tuple[str, str], PatternSuccessSnapshot] | None = None,
    ) -> PatternSuccessSnapshot | None:
        normalized_regime = normalize_market_regime(market_regime)
        if snapshot_cache is not None:
            cached = snapshot_cache.get((slug, normalized_regime))
            if cached is not None:
                return cached
            return snapshot_cache.get((slug, GLOBAL_MARKET_REGIME))
        row = await self.session.get(PatternStatistic, (slug, timeframe, normalized_regime))
        if row is None and normalized_regime != GLOBAL_MARKET_REGIME:
            row = await self.session.get(PatternStatistic, (slug, timeframe, GLOBAL_MARKET_REGIME))
        if row is None:
            return None
        return PatternSuccessSnapshot(
            pattern_slug=str(row.pattern_slug),
            timeframe=int(row.timeframe),
            market_regime=str(row.market_regime),
            total_signals=int(row.total_signals or row.sample_size or 0),
            successful_signals=int(row.successful_signals or 0),
            success_rate=float(row.success_rate or 0.0),
            avg_return=float(row.avg_return or 0.0),
            avg_drawdown=float(row.avg_drawdown or 0.0),
            temperature=float(row.temperature or 0.0),
            enabled=bool(row.enabled),
        )

    async def _pattern_success_cache(
        self,
        *,
        timeframe: int,
        slugs: set[str],
        regimes: set[str] | None = None,
    ) -> dict[tuple[str, str], PatternSuccessSnapshot]:
        if not slugs:
            return {}
        normalized_regimes = {GLOBAL_MARKET_REGIME}
        if regimes:
            normalized_regimes.update(normalize_market_regime(item) for item in regimes)
        rows = (
            (
                await self.session.execute(
                    select(PatternStatistic).where(
                        PatternStatistic.pattern_slug.in_(sorted(slugs)),
                        PatternStatistic.timeframe == timeframe,
                        PatternStatistic.market_regime.in_(sorted(normalized_regimes)),
                    )
                )
            )
            .scalars()
            .all()
        )
        cache: dict[tuple[str, str], PatternSuccessSnapshot] = {}
        for row in rows:
            snapshot = PatternSuccessSnapshot(
                pattern_slug=str(row.pattern_slug),
                timeframe=int(row.timeframe),
                market_regime=str(row.market_regime),
                total_signals=int(row.total_signals or row.sample_size or 0),
                successful_signals=int(row.successful_signals or 0),
                success_rate=float(row.success_rate or 0.0),
                avg_return=float(row.avg_return or 0.0),
                avg_drawdown=float(row.avg_drawdown or 0.0),
                temperature=float(row.temperature or 0.0),
                enabled=bool(row.enabled),
            )
            cache[(snapshot.pattern_slug, snapshot.market_regime)] = snapshot
        return cache

    async def _upsert_signals(self, *, rows: Sequence[dict[str, object]]) -> int:
        if not rows:
            return 0
        stmt = insert(Signal).values(list(rows))
        stmt = stmt.on_conflict_do_update(
            index_elements=["coin_id", "timeframe", "candle_timestamp", "signal_type"],
            set_={
                "confidence": stmt.excluded.confidence,
                "market_regime": stmt.excluded.market_regime,
            },
        )
        result = await self.session.execute(stmt)
        await self._uow.flush()
        return int(result.rowcount or 0)

    async def _upsert_signal_history(self, *, rows: Sequence[dict[str, object]]) -> None:
        if not rows:
            return
        stmt = insert(SignalHistory).values(list(rows))
        stmt = stmt.on_conflict_do_update(
            index_elements=["coin_id", "timeframe", "signal_type", "candle_timestamp"],
            set_={
                "confidence": stmt.excluded.confidence,
                "market_regime": stmt.excluded.market_regime,
                "profit_after_24h": stmt.excluded.profit_after_24h,
                "profit_after_72h": stmt.excluded.profit_after_72h,
                "maximum_drawdown": stmt.excluded.maximum_drawdown,
                "result_return": stmt.excluded.result_return,
                "result_drawdown": stmt.excluded.result_drawdown,
                "evaluated_at": stmt.excluded.evaluated_at,
            },
        )
        await self.session.execute(stmt)
        await self._uow.flush()

    async def _upsert_pattern_statistics(self, *, rows: Sequence[dict[str, object]]) -> None:
        if not rows:
            return
        stmt = insert(PatternStatistic).values(list(rows))
        stmt = stmt.on_conflict_do_update(
            index_elements=["pattern_slug", "timeframe", "market_regime"],
            set_={
                "sample_size": stmt.excluded.sample_size,
                "total_signals": stmt.excluded.total_signals,
                "successful_signals": stmt.excluded.successful_signals,
                "success_rate": stmt.excluded.success_rate,
                "avg_return": stmt.excluded.avg_return,
                "avg_drawdown": stmt.excluded.avg_drawdown,
                "temperature": stmt.excluded.temperature,
                "enabled": stmt.excluded.enabled,
                "last_evaluated_at": stmt.excluded.last_evaluated_at,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self.session.execute(stmt)
        await self._uow.flush()

    async def _replace_discovered_patterns(self, *, rows: Sequence[dict[str, object]]) -> None:
        await self.session.execute(delete(DiscoveredPattern))
        if rows:
            stmt = insert(DiscoveredPattern).values(list(rows))
            stmt = stmt.on_conflict_do_update(
                index_elements=["structure_hash", "timeframe"],
                set_={
                    "sample_size": stmt.excluded.sample_size,
                    "avg_return": stmt.excluded.avg_return,
                    "avg_drawdown": stmt.excluded.avg_drawdown,
                    "confidence": stmt.excluded.confidence,
                },
            )
            await self.session.execute(stmt)
        await self._uow.flush()

    async def _replace_sector_metrics(self, *, timeframe: int, rows: Sequence[dict[str, object]]) -> int:
        await self.session.execute(delete(SectorMetric).where(SectorMetric.timeframe == timeframe))
        created = 0
        if rows:
            stmt = insert(SectorMetric).values(list(rows))
            stmt = stmt.on_conflict_do_update(
                index_elements=["sector_id", "timeframe"],
                set_={
                    "sector_strength": stmt.excluded.sector_strength,
                    "relative_strength": stmt.excluded.relative_strength,
                    "capital_flow": stmt.excluded.capital_flow,
                    "volatility": stmt.excluded.volatility,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            result = await self.session.execute(stmt)
            created = int(result.rowcount or 0)
        await self._uow.flush()
        return created

    async def _load_enabled_strategies(self) -> list[Strategy]:
        return (
            (
                await self.session.execute(
                    select(Strategy)
                    .options(selectinload(Strategy.rules), selectinload(Strategy.performance))
                    .where(Strategy.enabled.is_(True))
                    .order_by(Strategy.id.asc())
                )
            )
            .scalars()
            .all()
        )

    async def _strategy_alignment(
        self,
        *,
        strategies: Sequence[Strategy],
        tokens: set[str],
        token_confidence: dict[str, float],
        regime: str | None,
        sector: str | None,
        cycle: str | None,
    ) -> tuple[float, list[str]]:
        from src.apps.patterns.domain.decision import _clamp as decision_clamp
        from src.apps.patterns.domain.strategy import MIN_DISCOVERY_SAMPLE

        matched_names: list[str] = []
        best_alignment = 1.0
        for row in strategies:
            performance = row.performance
            if performance is None or performance.sample_size < MIN_DISCOVERY_SAMPLE:
                continue
            matched = True
            for rule in row.rules:
                if rule.pattern_slug not in tokens:
                    matched = False
                    break
                if rule.regime != "*" and regime != rule.regime:
                    matched = False
                    break
                if rule.sector != "*" and sector != rule.sector:
                    matched = False
                    break
                if rule.cycle != "*" and cycle != rule.cycle:
                    matched = False
                    break
                if token_confidence.get(rule.pattern_slug, 0.0) < float(rule.min_confidence or 0.0):
                    matched = False
                    break
            if not matched:
                continue
            matched_names.append(row.name)
            alignment = 1.0
            alignment += decision_clamp((float(performance.win_rate) - 0.5) * 0.6, 0.0, 0.18)
            alignment += decision_clamp(float(performance.sharpe_ratio) * 0.05, 0.0, 0.12)
            alignment += decision_clamp(float(performance.avg_return) * 4.0, 0.0, 0.08)
            alignment -= decision_clamp(abs(min(float(performance.max_drawdown), 0.0)) * 0.15, 0.0, 0.05)
            best_alignment = max(best_alignment, decision_clamp(alignment, 1.0, 1.3))
        return best_alignment, matched_names[:3]

    async def _signal_regime(self, *, metrics: CoinMetrics | None, timeframe: int) -> str | None:
        from src.apps.patterns.domain.regime import read_regime_details

        if metrics is not None:
            cached = await read_cached_regime_async(coin_id=int(metrics.coin_id), timeframe=timeframe)
            if cached is not None:
                return cached.regime
        if metrics is None:
            return None
        detailed = read_regime_details(metrics.market_regime_details, timeframe)
        return detailed.regime if detailed is not None else metrics.market_regime


__all__ = ["PatternTaskBase"]
