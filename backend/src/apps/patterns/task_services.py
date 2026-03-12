from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from math import floor, sqrt
from typing import Any, cast

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from src.apps.cross_market.models import Sector, SectorMetric
from src.apps.indicators.models import CoinMetrics, IndicatorCache
from src.apps.market_data.domain import ensure_utc, utc_now
from src.apps.market_data.models import Candle, Coin
from src.apps.market_data.repositories import CandleRepository, CoinRepository
from src.apps.patterns.cache import read_cached_regime_async
from src.apps.patterns.domain.base import PatternDetection, PatternDetector
from src.apps.patterns.domain.context import (
    _cycle_alignment as context_cycle_alignment,
)
from src.apps.patterns.domain.context import (
    _liquidity_score,
    _sector_alignment,
    _volatility_alignment,
    calculate_priority_score,
)
from src.apps.patterns.domain.context import (
    _regime_alignment as context_regime_alignment,
)
from src.apps.patterns.domain.cycle import MARKET_CYCLE_PHASES, _detect_cycle_phase
from src.apps.patterns.domain.decision import (
    MATERIAL_CONFIDENCE_DELTA,
    MATERIAL_SCORE_DELTA,
    RECENT_DECISION_LOOKBACK_DAYS,
    DecisionFactors,
    _decision_confidence,
    _decision_from_score,
    _decision_reason,
    _sector_strength_factor,
    calculate_decision_score,
)
from src.apps.patterns.domain.decision import (
    _clamp as decision_clamp,
)
from src.apps.patterns.domain.decision import (
    _regime_alignment as decision_regime_alignment,
)
from src.apps.patterns.domain.detectors import build_pattern_detectors
from src.apps.patterns.domain.discovery import (
    DISCOVERY_HORIZON,
    DISCOVERY_STEP,
    DISCOVERY_WINDOW_BARS,
    _window_signature,
)
from src.apps.patterns.domain.lifecycle import lifecycle_allows_detection, resolve_lifecycle_state
from src.apps.patterns.domain.narrative import CAPITAL_WAVES
from src.apps.patterns.domain.pattern_context import apply_pattern_context, dependencies_satisfied
from src.apps.patterns.domain.regime import detect_market_regime, read_regime_details
from src.apps.patterns.domain.registry import PATTERN_CATALOG, SUPPORTED_PATTERN_FEATURES
from src.apps.patterns.domain.risk import (
    MATERIAL_RISK_CONFIDENCE_DELTA,
    MATERIAL_RISK_SCORE_DELTA,
    RECENT_FINAL_SIGNAL_LOOKBACK_DAYS,
    _final_signal_reason,
    _risk_adjusted_decision,
    _risk_confidence,
    calculate_liquidity_score,
    calculate_risk_adjusted_score,
    calculate_slippage_risk,
    calculate_volatility_risk,
)
from src.apps.patterns.domain.semantics import (
    is_cluster_signal,
    is_hierarchy_signal,
    is_pattern_signal,
    pattern_bias,
    slug_from_signal_type,
)
from src.apps.patterns.domain.statistics import (
    STATISTICS_LOOKBACK_DAYS,
    SUPPORTED_STATISTIC_TIMEFRAMES,
    PatternOutcome,
    _rolling_window,
    calculate_temperature,
)
from src.apps.patterns.domain.strategy import (
    HORIZON_BARS_BY_TIMEFRAME,
    MAX_DISCOVERED_STRATEGIES,
    MIN_AVG_RETURN,
    MIN_DISCOVERY_SAMPLE,
    MIN_MAX_DRAWDOWN,
    MIN_SHARPE_RATIO,
    MIN_WIN_RATE,
    STRATEGY_LOOKBACK_DAYS,
    StrategyCandidate,
    StrategyObservation,
    _candidate_definitions,
    _context_from_window,
    _sharpe_ratio,
    _signal_outcome,
    _strategy_description,
    _strategy_enabled,
    _strategy_name,
)
from src.apps.patterns.domain.success import (
    BOOST_SUCCESS_RATE,
    DEGRADE_SUCCESS_RATE,
    DISABLE_SUCCESS_RATE,
    GLOBAL_MARKET_REGIME,
    MIN_SAMPLE_FOR_DEGRADE,
    MIN_SAMPLE_FOR_DISABLE,
    PatternSuccessSnapshot,
    apply_pattern_success_validation,
    normalize_market_regime,
    publish_pattern_state_event,
)
from src.apps.patterns.domain.utils import current_indicator_map
from src.apps.patterns.models import DiscoveredPattern, MarketCycle, PatternFeature, PatternRegistry, PatternStatistic
from src.apps.patterns.query_services import PatternQueryService
from src.apps.signals.history import (
    SIGNAL_HISTORY_LOOKBACK_DAYS,
    _close_timestamps,
    _evaluate_signal,
    _open_timestamp_from_signal,
)
from src.apps.signals.models import (
    FinalSignal,
    InvestmentDecision,
    RiskMetric,
    Signal,
    SignalHistory,
    Strategy,
    StrategyPerformance,
    StrategyRule,
)
from src.core.db.persistence import PersistenceComponent
from src.core.db.uow import BaseAsyncUnitOfWork
from src.runtime.streams.messages import publish_investment_decision_message, publish_investment_signal_message


class _PatternTaskSupport(PersistenceComponent):
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
    ):
        return await self._candles.fetch_points(coin_id=coin_id, timeframe=timeframe, limit=limit)

    async def _fetch_candle_points_between(
        self,
        *,
        coin_id: int,
        timeframe: int,
        window_start: datetime,
        window_end: datetime,
    ):
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
        if metrics is not None:
            cached = await read_cached_regime_async(coin_id=int(metrics.coin_id), timeframe=timeframe)
            if cached is not None:
                return cached.regime
        if metrics is None:
            return None
        detailed = read_regime_details(metrics.market_regime_details, timeframe)
        return detailed.regime if detailed is not None else metrics.market_regime

    async def _refresh_signal_history(
        self,
        *,
        lookback_days: int = SIGNAL_HISTORY_LOOKBACK_DAYS,
        coin_id: int | None = None,
        timeframe: int | None = None,
        limit_per_scope: int | None = None,
    ) -> dict[str, object]:
        cutoff = utc_now() - timedelta(days=lookback_days)
        stmt = (
            select(Signal)
            .where(Signal.candle_timestamp >= cutoff)
            .order_by(
                Signal.coin_id.asc(), Signal.timeframe.asc(), Signal.candle_timestamp.asc(), Signal.created_at.asc()
            )
        )
        if coin_id is not None:
            stmt = stmt.where(Signal.coin_id == coin_id)
        if timeframe is not None:
            stmt = stmt.where(Signal.timeframe == timeframe)
        signals = (await self.session.execute(stmt)).scalars().all()
        if limit_per_scope is not None:
            grouped_rows: dict[tuple[int, int], list[Signal]] = defaultdict(list)
            for row in signals:
                grouped_rows[(int(row.coin_id), int(row.timeframe))].append(row)
            limited: list[Signal] = []
            for scoped_rows in grouped_rows.values():
                limited.extend(scoped_rows[-limit_per_scope:])
            limited.sort(key=lambda row: (row.coin_id, row.timeframe, row.candle_timestamp, row.created_at))
            signals = limited

        if not signals:
            return {
                "status": "ok",
                "rows": 0,
                "evaluated": 0,
                "coin_id": coin_id,
                "timeframe": timeframe,
            }

        groups: dict[tuple[int, int], list[Signal]] = defaultdict(list)
        for row in signals:
            groups[(int(row.coin_id), int(row.timeframe))].append(row)

        rows: list[dict[str, object]] = []
        evaluated = 0
        for (group_coin_id, group_timeframe), scoped_signals in groups.items():
            start = _open_timestamp_from_signal(scoped_signals[0])
            end = ensure_utc(scoped_signals[-1].candle_timestamp) + timedelta(hours=72)
            end += timedelta(minutes=group_timeframe)
            candles = await self._fetch_candle_points_between(
                coin_id=group_coin_id,
                timeframe=group_timeframe,
                window_start=start,
                window_end=end,
            )
            if not candles:
                rows.extend(
                    {
                        "coin_id": signal.coin_id,
                        "timeframe": signal.timeframe,
                        "signal_type": signal.signal_type,
                        "confidence": float(signal.confidence),
                        "market_regime": signal.market_regime,
                        "candle_timestamp": signal.candle_timestamp,
                        "profit_after_24h": None,
                        "profit_after_72h": None,
                        "maximum_drawdown": None,
                        "result_return": None,
                        "result_drawdown": None,
                        "evaluated_at": None,
                    }
                    for signal in scoped_signals
                )
                continue

            close_timestamps = _close_timestamps(candles, group_timeframe)
            close_index_map = {timestamp: index for index, timestamp in enumerate(close_timestamps)}
            for signal in scoped_signals:
                outcome = _evaluate_signal(signal, candles, close_timestamps, close_index_map)
                if outcome.evaluated_at is not None:
                    evaluated += 1
                rows.append(
                    {
                        "coin_id": signal.coin_id,
                        "timeframe": signal.timeframe,
                        "signal_type": signal.signal_type,
                        "confidence": float(signal.confidence),
                        "market_regime": signal.market_regime,
                        "candle_timestamp": signal.candle_timestamp,
                        "profit_after_24h": outcome.profit_after_24h,
                        "profit_after_72h": outcome.profit_after_72h,
                        "maximum_drawdown": outcome.maximum_drawdown,
                        "result_return": outcome.result_return,
                        "result_drawdown": outcome.result_drawdown,
                        "evaluated_at": outcome.evaluated_at,
                    }
                )
        await self._upsert_signal_history(rows=rows)
        return {"status": "ok", "rows": len(rows), "evaluated": evaluated, "coin_id": coin_id, "timeframe": timeframe}

    async def _refresh_pattern_statistics(self, *, emit_events: bool = True) -> dict[str, object]:
        await self._ensure_catalog_metadata()
        cutoff = utc_now() - timedelta(days=STATISTICS_LOOKBACK_DAYS)
        history_rows = (
            (
                await self.session.execute(
                    select(SignalHistory)
                    .where(
                        SignalHistory.candle_timestamp >= cutoff,
                        SignalHistory.signal_type.like("pattern_%"),
                        SignalHistory.result_return.is_not(None),
                        SignalHistory.result_drawdown.is_not(None),
                    )
                    .order_by(SignalHistory.timeframe.asc(), SignalHistory.candle_timestamp.asc())
                )
            )
            .scalars()
            .all()
        )

        outcomes_by_pattern: dict[tuple[str, int, str], list[PatternOutcome]] = defaultdict(list)
        for row in history_rows:
            if not is_pattern_signal(str(row.signal_type)):
                continue
            slug = slug_from_signal_type(str(row.signal_type))
            if slug is None:
                continue
            terminal_return = (
                float(row.profit_after_72h)
                if row.profit_after_72h is not None
                else float(row.profit_after_24h)
                if row.profit_after_24h is not None
                else float(row.result_return)
                if row.result_return is not None
                else None
            )
            drawdown = (
                float(row.maximum_drawdown)
                if row.maximum_drawdown is not None
                else float(row.result_drawdown)
                if row.result_drawdown is not None
                else None
            )
            if terminal_return is None or drawdown is None:
                continue
            market_regime = normalize_market_regime(row.market_regime)
            outcome = PatternOutcome(
                pattern_slug=slug,
                timeframe=int(row.timeframe),
                market_regime=market_regime,
                terminal_return=terminal_return,
                drawdown=drawdown,
                success=terminal_return > 0,
                age_days=max((utc_now() - ensure_utc(row.candle_timestamp)).days, 0),
                evaluated_at=row.evaluated_at,
            )
            outcomes_by_pattern[(outcome.pattern_slug, outcome.timeframe, market_regime)].append(outcome)
            outcomes_by_pattern[(outcome.pattern_slug, outcome.timeframe, GLOBAL_MARKET_REGIME)].append(outcome)

        outcomes_by_pattern = _rolling_window(outcomes_by_pattern)

        rows: list[dict[str, object]] = []
        lifecycle_updates: list[dict[str, object]] = []
        for entry in PATTERN_CATALOG:
            entry_rows: list[dict[str, object]] = []
            for timeframe in SUPPORTED_STATISTIC_TIMEFRAMES:
                scoped_regimes = {GLOBAL_MARKET_REGIME}
                scoped_regimes.update(
                    regime
                    for pattern_slug, scoped_timeframe, regime in outcomes_by_pattern
                    if pattern_slug == entry.slug and scoped_timeframe == timeframe and regime != GLOBAL_MARKET_REGIME
                )
                for market_regime in sorted(scoped_regimes):
                    outcomes = outcomes_by_pattern.get((entry.slug, timeframe, market_regime), [])
                    sample_size = len(outcomes)
                    successful_signals = sum(1 for item in outcomes if item.success)
                    success_rate = successful_signals / sample_size if sample_size else 0.0
                    avg_return = sum(item.terminal_return for item in outcomes) / sample_size if sample_size else 0.0
                    avg_drawdown = sum(item.drawdown for item in outcomes) / sample_size if sample_size else 0.0
                    age_days = min((item.age_days for item in outcomes), default=STATISTICS_LOOKBACK_DAYS)
                    last_evaluated_at = max(
                        (item.evaluated_at for item in outcomes if item.evaluated_at is not None),
                        default=None,
                    )
                    temperature = calculate_temperature(
                        success_rate=success_rate,
                        sample_size=sample_size,
                        days_since_sample=age_days,
                    )
                    enabled = not (sample_size >= MIN_SAMPLE_FOR_DISABLE and success_rate < DISABLE_SUCCESS_RATE)
                    entry_row = {
                        "pattern_slug": entry.slug,
                        "timeframe": timeframe,
                        "market_regime": market_regime,
                        "sample_size": sample_size,
                        "total_signals": sample_size,
                        "successful_signals": successful_signals,
                        "success_rate": success_rate,
                        "avg_return": avg_return,
                        "avg_drawdown": avg_drawdown,
                        "temperature": temperature,
                        "enabled": enabled,
                        "last_evaluated_at": last_evaluated_at,
                        "updated_at": utc_now(),
                    }
                    rows.append(entry_row)
                    if market_regime == GLOBAL_MARKET_REGIME:
                        entry_rows.append(entry_row)
            temps = [float(row["temperature"]) for row in entry_rows]
            aggregate_sample_size = sum(int(row["sample_size"]) for row in entry_rows)
            aggregate_success_rate = (
                sum(float(row["success_rate"]) * int(row["sample_size"]) for row in entry_rows) / aggregate_sample_size
                if aggregate_sample_size
                else 0.0
            )
            aggregate_temp = sum(temps) / len(temps) if temps else 0.0
            representative_timeframe = (
                int(max(entry_rows, key=lambda row: int(row["sample_size"]))["timeframe"]) if entry_rows else 15
            )
            registry_row = await self.session.get(PatternRegistry, entry.slug)
            registry_enabled = bool(registry_row.enabled) if registry_row is not None else True
            next_state = resolve_lifecycle_state(aggregate_temp, registry_enabled)
            if aggregate_sample_size >= MIN_SAMPLE_FOR_DISABLE and aggregate_success_rate < DISABLE_SUCCESS_RATE:
                next_state = resolve_lifecycle_state(-1.0, registry_enabled)
            lifecycle_updates.append(
                {
                    "slug": entry.slug,
                    "timeframe": representative_timeframe,
                    "lifecycle_state": next_state.value,
                    "success_rate": aggregate_success_rate,
                    "sample_size": aggregate_sample_size,
                }
            )

        await self._upsert_pattern_statistics(rows=rows)
        for update in lifecycle_updates:
            registry_row = await self.session.get(PatternRegistry, str(update["slug"]))
            if registry_row is None:
                continue
            previous_state = str(registry_row.lifecycle_state)
            registry_row.lifecycle_state = str(update["lifecycle_state"])
            if not emit_events:
                continue
            if previous_state != registry_row.lifecycle_state:
                became_enabled = previous_state == "DISABLED" and registry_row.lifecycle_state != "DISABLED"
                became_disabled = previous_state != "DISABLED" and registry_row.lifecycle_state == "DISABLED"
                if became_enabled:
                    publish_pattern_state_event(
                        "pattern_enabled",
                        pattern_slug=registry_row.slug,
                        timeframe=int(update["timeframe"]),
                        success_rate=float(update["success_rate"]),
                        total_signals=int(update["sample_size"]),
                        timestamp=utc_now(),
                    )
                elif became_disabled:
                    publish_pattern_state_event(
                        "pattern_disabled",
                        pattern_slug=registry_row.slug,
                        timeframe=int(update["timeframe"]),
                        success_rate=float(update["success_rate"]),
                        total_signals=int(update["sample_size"]),
                        timestamp=utc_now(),
                    )
            if int(update["sample_size"]) >= MIN_SAMPLE_FOR_DEGRADE:
                if float(update["success_rate"]) > BOOST_SUCCESS_RATE:
                    publish_pattern_state_event(
                        "pattern_boosted",
                        pattern_slug=registry_row.slug,
                        timeframe=int(update["timeframe"]),
                        success_rate=float(update["success_rate"]),
                        total_signals=int(update["sample_size"]),
                        timestamp=utc_now(),
                    )
                elif float(update["success_rate"]) < DEGRADE_SUCCESS_RATE:
                    publish_pattern_state_event(
                        "pattern_degraded",
                        pattern_slug=registry_row.slug,
                        timeframe=int(update["timeframe"]),
                        success_rate=float(update["success_rate"]),
                        total_signals=int(update["sample_size"]),
                        timestamp=utc_now(),
                    )
        await self._uow.flush()
        return {
            "status": "ok",
            "patterns": len(rows),
            "updated_registry": len(lifecycle_updates),
            "rolling_window": 200,
        }

    async def _enrich_signal_context(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: object | None = None,
    ) -> dict[str, object]:
        stmt = select(Signal).where(Signal.coin_id == coin_id, Signal.timeframe == timeframe)
        if candle_timestamp is not None:
            normalized_timestamp = (
                ensure_utc(datetime.fromisoformat(candle_timestamp))
                if isinstance(candle_timestamp, str)
                else candle_timestamp
            )
            stmt = stmt.where(Signal.candle_timestamp == normalized_timestamp)
        signals = (await self.session.execute(stmt)).scalars().all()
        if not signals:
            return {"status": "skipped", "reason": "signals_not_found", "coin_id": coin_id, "timeframe": timeframe}

        metrics = await self.session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id).limit(1))
        coin = await self.session.scalar(select(Coin).where(Coin.id == coin_id).limit(1))
        sector_metric = (
            await self.session.get(SectorMetric, (int(coin.sector_id), timeframe))
            if coin is not None and coin.sector_id is not None
            else None
        )
        cycle = await self.session.get(MarketCycle, (coin_id, timeframe))
        cluster_timestamps = {
            signal.candle_timestamp for signal in signals if is_cluster_signal(str(signal.signal_type))
        }
        signal_regimes: dict[int, str | None] = {}
        unique_slugs = {
            slug for signal in signals if (slug := slug_from_signal_type(str(signal.signal_type))) is not None
        }
        regime_values: set[str] = set()
        for signal in signals:
            resolved_regime = signal.market_regime or await self._signal_regime(
                metrics=metrics, timeframe=int(signal.timeframe)
            )
            signal_regimes[int(signal.id)] = resolved_regime
            if resolved_regime is not None:
                regime_values.add(resolved_regime)
        snapshot_cache = await self._pattern_success_cache(
            timeframe=timeframe,
            slugs=unique_slugs,
            regimes=regime_values,
        )
        for signal in signals:
            slug = slug_from_signal_type(str(signal.signal_type))
            bias = pattern_bias(slug or str(signal.signal_type), fallback_price_delta=float(signal.confidence) - 0.5)
            signal_regime = signal_regimes.get(int(signal.id))
            regime_alignment = context_regime_alignment(signal_regime, bias)
            volatility_alignment = _volatility_alignment(str(signal.signal_type), metrics)
            liquidity_score = _liquidity_score(metrics)
            sector_alignment = _sector_alignment(sector_metric, bias)
            cycle_alignment = context_cycle_alignment(cycle, bias)
            snapshot = (
                await self._pattern_success_snapshot(
                    slug=slug,
                    timeframe=int(signal.timeframe),
                    market_regime=signal_regime,
                    snapshot_cache=snapshot_cache,
                )
                if slug is not None
                else None
            )
            temperature = float(snapshot.temperature) if snapshot is not None and snapshot.temperature != 0 else 1.0
            cluster_bonus = (
                1.15
                if signal.candle_timestamp in cluster_timestamps and is_pattern_signal(str(signal.signal_type))
                else 1.0
            )
            context_score = max(
                temperature
                * volatility_alignment
                * liquidity_score
                * cluster_bonus
                * sector_alignment
                * cycle_alignment,
                0.0,
            )
            signal.regime_alignment = regime_alignment
            signal.context_score = context_score
            signal.priority_score = calculate_priority_score(
                confidence=float(signal.confidence),
                pattern_temperature=temperature,
                regime_alignment=regime_alignment,
                volatility_alignment=volatility_alignment * cluster_bonus * sector_alignment * cycle_alignment,
                liquidity_score=liquidity_score,
            )
        await self._uow.flush()
        return {"status": "ok", "coin_id": coin_id, "timeframe": timeframe, "signals": len(signals)}

    async def _refresh_recent_signal_contexts(
        self,
        *,
        lookback_days: int = 30,
    ) -> dict[str, object]:
        recent_cutoff = utc_now() - timedelta(days=max(lookback_days, 1))
        rows = (
            await self.session.execute(
                select(Signal.coin_id, Signal.timeframe, Signal.candle_timestamp)
                .where(Signal.candle_timestamp >= recent_cutoff)
                .distinct()
                .order_by(Signal.coin_id.asc(), Signal.timeframe.asc(), Signal.candle_timestamp.asc())
            )
        ).all()
        updated = 0
        for row in rows:
            result = await self._enrich_signal_context(
                coin_id=int(row.coin_id),
                timeframe=int(row.timeframe),
                candle_timestamp=row.candle_timestamp,
            )
            updated += int(result.get("signals", 0))
        return {"status": "ok", "signals": updated, "groups": len(rows)}

    async def _evaluate_investment_decision(
        self,
        *,
        coin_id: int,
        timeframe: int,
        narratives_by_timeframe: dict[int, object] | None = None,
        strategies: Sequence[Strategy] | None = None,
        emit_event: bool = True,
    ) -> dict[str, object]:
        latest_timestamp = await self.session.scalar(
            select(func.max(Signal.candle_timestamp)).where(
                Signal.coin_id == coin_id,
                Signal.timeframe == timeframe,
                Signal.signal_type.like("pattern_%"),
            )
        )
        if latest_timestamp is None:
            return {
                "status": "skipped",
                "reason": "pattern_signals_not_found",
                "coin_id": coin_id,
                "timeframe": timeframe,
            }
        signals = (
            (
                await self.session.execute(
                    select(Signal)
                    .where(
                        Signal.coin_id == coin_id,
                        Signal.timeframe == timeframe,
                        Signal.candle_timestamp == latest_timestamp,
                        Signal.signal_type.like("pattern_%"),
                    )
                    .order_by(Signal.created_at.asc(), Signal.id.asc())
                )
            )
            .scalars()
            .all()
        )
        if not signals:
            return {"status": "skipped", "reason": "signal_stack_not_found", "coin_id": coin_id, "timeframe": timeframe}

        coin = await self.session.scalar(
            select(Coin).options(selectinload(Coin.sector)).where(Coin.id == coin_id).limit(1)
        )
        if coin is None:
            return {"status": "skipped", "reason": "coin_not_found", "coin_id": coin_id, "timeframe": timeframe}
        metrics = await self.session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id).limit(1))
        cycle = await self.session.get(MarketCycle, (coin_id, timeframe))
        sector_metric = (
            await self.session.get(SectorMetric, (int(coin.sector_id), timeframe))
            if coin.sector_id is not None
            else None
        )
        narrative = narratives_by_timeframe.get(timeframe) if narratives_by_timeframe is not None else None
        if narrative is None:
            narrative = next(
                (item for item in await self._queries.build_sector_narratives() if item.timeframe == timeframe), None
            )

        relevant_signals = [signal for signal in signals if str(signal.signal_type).startswith("pattern_")]
        weights = [max(float(signal.priority_score or signal.confidence), 0.01) for signal in relevant_signals]
        signal_priority = sum(sorted(weights, reverse=True)[:5]) / max(min(len(weights), 5), 1)

        signed_weight = 0.0
        pattern_slugs: set[str] = set()
        token_confidence: dict[str, float] = {}
        strategy_tokens: set[str] = set()
        for signal in relevant_signals:
            slug = slug_from_signal_type(str(signal.signal_type))
            if slug is not None and is_pattern_signal(str(signal.signal_type)):
                pattern_slugs.add(slug)
                strategy_tokens.add(slug)
                token_confidence[slug] = max(token_confidence.get(slug, 0.0), float(signal.confidence))
            weight = max(float(signal.priority_score or signal.confidence), 0.01)
            signed_weight += weight * pattern_bias(
                slug or str(signal.signal_type), fallback_price_delta=float(signal.confidence) - 0.5
            )

        total_weight = sum(weights)
        bias_ratio = signed_weight / max(total_weight, 1e-9)
        bias = 1 if bias_ratio > 0 else -1 if bias_ratio < 0 else 0
        regime_snapshot = (
            read_regime_details(metrics.market_regime_details, timeframe)
            if metrics is not None and metrics.market_regime_details
            else None
        )
        regime = (
            regime_snapshot.regime
            if regime_snapshot is not None
            else (metrics.market_regime if metrics is not None else None)
        )
        regime_alignment = decision_regime_alignment(relevant_signals)
        sector_strength = _sector_strength_factor(coin, metrics, sector_metric, narrative)
        cycle_alignment = context_cycle_alignment(cycle, bias)

        success_rows = (
            (
                await self.session.execute(
                    select(PatternStatistic).where(
                        PatternStatistic.pattern_slug.in_(sorted(pattern_slugs)) if pattern_slugs else False,
                        PatternStatistic.timeframe == timeframe,
                        PatternStatistic.market_regime.in_([GLOBAL_MARKET_REGIME, normalize_market_regime(regime)]),
                    )
                )
            )
            .scalars()
            .all()
            if pattern_slugs
            else []
        )
        success_values: dict[str, float] = {}
        for row in success_rows:
            current = success_values.get(str(row.pattern_slug))
            candidate = float(row.success_rate or 0.0)
            if current is None or str(row.market_regime) != GLOBAL_MARKET_REGIME:
                success_values[str(row.pattern_slug)] = candidate
        historical_pattern_success = (
            decision_clamp(sum(success_values.values()) / len(success_values), 0.35, 0.95) if success_values else 0.55
        )

        loaded_strategies = list(strategies) if strategies is not None else await self._load_enabled_strategies()
        strategy_alignment_value, matched_strategies = await self._strategy_alignment(
            strategies=loaded_strategies,
            tokens=strategy_tokens,
            token_confidence=token_confidence,
            regime=regime,
            sector=coin.sector.name if coin.sector is not None else None,
            cycle=cycle.cycle_phase if cycle is not None else None,
        )
        factors = DecisionFactors(
            signal_priority=signal_priority,
            regime_alignment=regime_alignment,
            sector_strength=sector_strength,
            cycle_alignment=cycle_alignment,
            historical_pattern_success=historical_pattern_success,
            strategy_alignment=strategy_alignment_value,
        )
        score = calculate_decision_score(
            signal_priority=factors.signal_priority,
            regime_alignment=factors.regime_alignment,
            sector_strength=factors.sector_strength,
            cycle_alignment=factors.cycle_alignment,
            historical_pattern_success=factors.historical_pattern_success,
            strategy_alignment=factors.strategy_alignment,
        )
        decision = _decision_from_score(score, bias_ratio)
        confidence = _decision_confidence(score, bias_ratio, factors)
        reason = _decision_reason(
            decision=decision,
            score=score,
            bias_ratio=bias_ratio,
            signals=relevant_signals,
            regime=regime,
            sector_metric=sector_metric,
            narrative=narrative,
            cycle=cycle,
            historical_pattern_success=historical_pattern_success,
            strategy_alignment_value=strategy_alignment_value,
            matched_strategies=matched_strategies,
        )

        latest_decision = await self.session.scalar(
            select(InvestmentDecision)
            .where(InvestmentDecision.coin_id == coin_id, InvestmentDecision.timeframe == timeframe)
            .order_by(InvestmentDecision.created_at.desc(), InvestmentDecision.id.desc())
            .limit(1)
        )
        if (
            latest_decision is not None
            and latest_decision.decision == decision
            and abs(float(latest_decision.score) - score) < MATERIAL_SCORE_DELTA
            and abs(float(latest_decision.confidence) - confidence) < MATERIAL_CONFIDENCE_DELTA
            and latest_decision.reason == reason
        ):
            return {
                "status": "skipped",
                "reason": "decision_unchanged",
                "coin_id": coin_id,
                "timeframe": timeframe,
                "decision": decision,
                "score": score,
            }

        row = InvestmentDecision(
            coin_id=coin_id,
            timeframe=timeframe,
            decision=decision,
            confidence=confidence,
            score=score,
            reason=reason,
        )
        self.session.add(row)
        await self._uow.flush()
        if emit_event:
            publish_investment_decision_message(
                coin,
                timeframe=timeframe,
                decision=decision,
                confidence=confidence,
                score=score,
                reason=reason,
            )
        return {
            "status": "ok",
            "id": row.id,
            "coin_id": coin_id,
            "timeframe": timeframe,
            "decision": decision,
            "confidence": confidence,
            "score": score,
        }

    async def _refresh_investment_decisions(
        self,
        *,
        lookback_days: int = RECENT_DECISION_LOOKBACK_DAYS,
        emit_events: bool = False,
    ) -> dict[str, object]:
        cutoff = utc_now() - timedelta(days=max(lookback_days, 1))
        rows = (
            await self.session.execute(
                select(Signal.coin_id, Signal.timeframe)
                .where(Signal.signal_type.like("pattern_%"), Signal.candle_timestamp >= cutoff)
                .distinct()
                .order_by(Signal.coin_id.asc(), Signal.timeframe.asc())
            )
        ).all()
        candidates = [(int(row.coin_id), int(row.timeframe)) for row in rows]
        narratives_by_timeframe = {item.timeframe: item for item in await self._queries.build_sector_narratives()}
        strategies = await self._load_enabled_strategies()
        items = [
            await self._evaluate_investment_decision(
                coin_id=coin_id,
                timeframe=timeframe,
                narratives_by_timeframe=narratives_by_timeframe,
                strategies=strategies,
                emit_event=emit_events,
            )
            for coin_id, timeframe in candidates
        ]
        return {
            "status": "ok",
            "items": items,
            "updated": sum(1 for item in items if item.get("status") == "ok"),
            "candidates": len(candidates),
        }

    async def _update_risk_metrics(
        self,
        *,
        coin_id: int,
        timeframe: int,
    ) -> tuple[dict[str, object], RiskMetric | None]:
        coin = await self.session.scalar(select(Coin).where(Coin.id == coin_id).limit(1))
        if coin is None:
            return {"status": "skipped", "reason": "coin_not_found", "coin_id": coin_id, "timeframe": timeframe}, None
        metrics = await self.session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id).limit(1))
        volume_24h = float(metrics.volume_24h or 0.0) if metrics is not None else 0.0
        market_cap = float(metrics.market_cap or 0.0) if metrics is not None else 0.0
        atr_14 = (
            await self.session.execute(
                select(IndicatorCache.value)
                .where(
                    IndicatorCache.coin_id == coin_id,
                    IndicatorCache.timeframe == timeframe,
                    IndicatorCache.indicator == "atr_14",
                )
                .order_by(IndicatorCache.timestamp.desc(), IndicatorCache.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if atr_14 is None and metrics is not None:
            atr_14 = float(metrics.atr_14 or 0.0)
        price = (
            await self.session.execute(
                select(Candle.close)
                .where(Candle.coin_id == coin_id, Candle.timeframe == timeframe)
                .order_by(Candle.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if price is None and metrics is not None:
            price = float(metrics.price_current or 0.0)

        liquidity_score = calculate_liquidity_score(volume_24h=volume_24h, market_cap=market_cap)
        slippage_risk = calculate_slippage_risk(volume_24h=volume_24h, market_cap=market_cap)
        volatility_risk = calculate_volatility_risk(atr_14=float(atr_14 or 0.0), price=float(price or 0.0))

        row = await self.session.get(RiskMetric, (coin_id, timeframe))
        if row is None:
            row = RiskMetric(coin_id=coin_id, timeframe=timeframe)
            self.session.add(row)
        row.liquidity_score = liquidity_score
        row.slippage_risk = slippage_risk
        row.volatility_risk = volatility_risk
        row.updated_at = utc_now()
        await self._uow.flush()
        return {
            "status": "ok",
            "coin_id": coin_id,
            "timeframe": timeframe,
            "liquidity_score": liquidity_score,
            "slippage_risk": slippage_risk,
            "volatility_risk": volatility_risk,
        }, row

    async def _evaluate_final_signal(
        self,
        *,
        coin_id: int,
        timeframe: int,
        emit_event: bool = True,
    ) -> dict[str, object]:
        coin = await self.session.scalar(select(Coin).where(Coin.id == coin_id).limit(1))
        if coin is None:
            return {"status": "skipped", "reason": "coin_not_found", "coin_id": coin_id, "timeframe": timeframe}
        latest_decision = await self.session.scalar(
            select(InvestmentDecision)
            .where(InvestmentDecision.coin_id == coin_id, InvestmentDecision.timeframe == timeframe)
            .order_by(InvestmentDecision.created_at.desc(), InvestmentDecision.id.desc())
            .limit(1)
        )
        if latest_decision is None:
            return {"status": "skipped", "reason": "decision_not_found", "coin_id": coin_id, "timeframe": timeframe}

        metrics_payload, _ = await self._update_risk_metrics(coin_id=coin_id, timeframe=timeframe)
        risk_adjusted_score = calculate_risk_adjusted_score(
            decision_score=float(latest_decision.score),
            liquidity_score=float(metrics_payload["liquidity_score"]),
            slippage_risk=float(metrics_payload["slippage_risk"]),
            volatility_risk=float(metrics_payload["volatility_risk"]),
        )
        decision = _risk_adjusted_decision(str(latest_decision.decision), risk_adjusted_score)
        confidence = _risk_confidence(
            base_confidence=float(latest_decision.confidence),
            liquidity_score=float(metrics_payload["liquidity_score"]),
            slippage_risk=float(metrics_payload["slippage_risk"]),
            volatility_risk=float(metrics_payload["volatility_risk"]),
        )
        reason = _final_signal_reason(
            decision=decision,
            base_decision=str(latest_decision.decision),
            decision_score=float(latest_decision.score),
            risk_adjusted_score=risk_adjusted_score,
            liquidity_score=float(metrics_payload["liquidity_score"]),
            slippage_risk=float(metrics_payload["slippage_risk"]),
            volatility_risk=float(metrics_payload["volatility_risk"]),
        )

        latest_signal = await self.session.scalar(
            select(FinalSignal)
            .where(FinalSignal.coin_id == coin_id, FinalSignal.timeframe == timeframe)
            .order_by(FinalSignal.created_at.desc(), FinalSignal.id.desc())
            .limit(1)
        )
        if (
            latest_signal is not None
            and latest_signal.decision == decision
            and abs(float(latest_signal.risk_adjusted_score) - risk_adjusted_score) < MATERIAL_RISK_SCORE_DELTA
            and abs(float(latest_signal.confidence) - confidence) < MATERIAL_RISK_CONFIDENCE_DELTA
            and latest_signal.reason == reason
        ):
            return {
                "status": "skipped",
                "reason": "final_signal_unchanged",
                "coin_id": coin_id,
                "timeframe": timeframe,
                "decision": decision,
                "risk_adjusted_score": risk_adjusted_score,
            }

        row = FinalSignal(
            coin_id=coin_id,
            timeframe=timeframe,
            decision=decision,
            confidence=confidence,
            risk_adjusted_score=risk_adjusted_score,
            reason=reason,
        )
        self.session.add(row)
        await self._uow.flush()
        if emit_event:
            publish_investment_signal_message(
                coin,
                timeframe=timeframe,
                decision=decision,
                confidence=confidence,
                risk_score=risk_adjusted_score,
                reason=reason,
            )
        return {
            "status": "ok",
            "id": row.id,
            "coin_id": coin_id,
            "timeframe": timeframe,
            "decision": decision,
            "confidence": confidence,
            "risk_adjusted_score": risk_adjusted_score,
        }

    async def _refresh_final_signals(
        self,
        *,
        lookback_days: int = RECENT_FINAL_SIGNAL_LOOKBACK_DAYS,
        emit_events: bool = False,
    ) -> dict[str, object]:
        cutoff = utc_now() - timedelta(days=max(lookback_days, 1))
        rows = (
            await self.session.execute(
                select(InvestmentDecision.coin_id, InvestmentDecision.timeframe)
                .where(InvestmentDecision.created_at >= cutoff)
                .distinct()
                .order_by(InvestmentDecision.coin_id.asc(), InvestmentDecision.timeframe.asc())
            )
        ).all()
        candidates = [(int(row.coin_id), int(row.timeframe)) for row in rows]
        items = [
            await self._evaluate_final_signal(
                coin_id=coin_id,
                timeframe=timeframe,
                emit_event=emit_events,
            )
            for coin_id, timeframe in candidates
        ]
        return {
            "status": "ok",
            "items": items,
            "updated": sum(1 for item in items if item.get("status") == "ok"),
            "candidates": len(candidates),
        }

    async def _refresh_sector_metrics(self, *, timeframe: int | None = None) -> dict[str, object]:
        sectors = (await self.session.execute(select(Sector).order_by(Sector.name.asc()))).scalars().all()
        if not sectors:
            return {"status": "skipped", "reason": "sectors_not_found"}

        timeframes = [timeframe] if timeframe is not None else [15, 60, 240, 1440]
        coins = (
            (
                await self.session.execute(
                    select(Coin)
                    .where(Coin.enabled.is_(True), Coin.deleted_at.is_(None), Coin.sector_id.is_not(None))
                    .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
                )
            )
            .scalars()
            .all()
        )
        coins_by_sector: dict[int, list[Coin]] = defaultdict(list)
        for coin in coins:
            if coin.sector_id is not None:
                coins_by_sector[int(coin.sector_id)].append(coin)
        metrics_rows = (
            (
                await self.session.execute(
                    select(CoinMetrics).where(CoinMetrics.coin_id.in_([int(coin.id) for coin in coins]))
                    if coins
                    else select(CoinMetrics).where(False)
                )
            )
            .scalars()
            .all()
        )
        metrics_by_coin = {int(row.coin_id): row for row in metrics_rows}

        created = 0
        for current_timeframe in timeframes:
            market_returns: list[float] = []
            sector_rows: list[dict[str, object]] = []
            for sector in sectors:
                sector_coins = coins_by_sector.get(int(sector.id), [])
                if not sector_coins:
                    continue
                price_changes: list[float] = []
                volatility_values: list[float] = []
                capital_flow_components: list[float] = []
                for coin in sector_coins:
                    price_change, bar_volatility = await self._coin_bar_return(
                        coin_id=int(coin.id),
                        timeframe=current_timeframe,
                    )
                    metrics = metrics_by_coin.get(int(coin.id))
                    if price_change is not None:
                        price_changes.append(price_change)
                        market_returns.append(price_change)
                    if bar_volatility is not None:
                        volatility_values.append(bar_volatility)
                    if metrics is not None:
                        market_cap_component = ((metrics.market_cap or 0.0) / 1_000_000_000) * (price_change or 0.0)
                        volume_component = (metrics.volume_change_24h or 0.0) / 100
                        capital_flow_components.append(market_cap_component + volume_component)
                if not price_changes:
                    continue
                sector_rows.append(
                    {
                        "sector_id": int(sector.id),
                        "timeframe": current_timeframe,
                        "sector_strength": sum(price_changes) / len(price_changes),
                        "relative_strength": 0.0,
                        "capital_flow": sum(capital_flow_components) / len(capital_flow_components)
                        if capital_flow_components
                        else 0.0,
                        "volatility": sum(volatility_values) / len(volatility_values) if volatility_values else 0.0,
                        "updated_at": utc_now(),
                    }
                )
            market_return = sum(market_returns) / len(market_returns) if market_returns else 0.0
            for row in sector_rows:
                row["relative_strength"] = float(row["sector_strength"]) - market_return
            created += await self._replace_sector_metrics(timeframe=current_timeframe, rows=sector_rows)
        return {"status": "ok", "updated": created}

    async def _coin_bar_return(self, *, coin_id: int, timeframe: int) -> tuple[float | None, float | None]:
        candles = await self._fetch_candle_points(coin_id=coin_id, timeframe=timeframe, limit=25)
        if len(candles) < 2:
            return None, None
        previous = float(candles[-2].close)
        current = float(candles[-1].close)
        change = (current - previous) / previous if previous else 0.0
        closes = [float(item.close) for item in candles[-20:]]
        mean_close = sum(closes) / len(closes)
        volatility = (sum((value - mean_close) ** 2 for value in closes) / len(closes)) ** 0.5 if closes else 0.0
        return change, (volatility / current if current else 0.0)

    async def _refresh_market_cycles(self) -> dict[str, object]:
        coins = await self._coins.list(enabled_only=True)
        items = []
        for coin in coins:
            for timeframe in (15, 60, 240, 1440):
                metrics = await self.session.scalar(
                    select(CoinMetrics).where(CoinMetrics.coin_id == int(coin.id)).limit(1)
                )
                if metrics is None:
                    items.append({"status": "skipped", "reason": "coin_metrics_not_found", "coin_id": int(coin.id)})
                    continue
                pattern_density = int(
                    (
                        await self.session.execute(
                            select(func.count())
                            .select_from(Signal)
                            .where(
                                Signal.coin_id == int(coin.id),
                                Signal.timeframe == timeframe,
                                Signal.signal_type.like("pattern_%"),
                                ~Signal.signal_type.like("pattern_cluster_%"),
                                ~Signal.signal_type.like("pattern_hierarchy_%"),
                            )
                        )
                    ).scalar_one()
                    or 0
                )
                cluster_frequency = int(
                    (
                        await self.session.execute(
                            select(func.count())
                            .select_from(Signal)
                            .where(
                                Signal.coin_id == int(coin.id),
                                Signal.timeframe == timeframe,
                                Signal.signal_type.like("pattern_cluster_%"),
                            )
                        )
                    ).scalar_one()
                    or 0
                )
                sector_metric = (
                    await self.session.get(SectorMetric, (int(coin.sector_id), timeframe))
                    if coin.sector_id is not None
                    else None
                )
                regime_snapshot = read_regime_details(metrics.market_regime_details, timeframe)
                phase, confidence = _detect_cycle_phase(
                    trend_score=metrics.trend_score,
                    regime=regime_snapshot.regime if regime_snapshot is not None else metrics.market_regime,
                    volatility=metrics.volatility,
                    price_current=metrics.price_current,
                    pattern_density=pattern_density,
                    cluster_frequency=cluster_frequency,
                    sector_strength=sector_metric.sector_strength if sector_metric is not None else None,
                    capital_flow=sector_metric.capital_flow if sector_metric is not None else None,
                )
                stmt = insert(MarketCycle).values(
                    {
                        "coin_id": int(coin.id),
                        "timeframe": timeframe,
                        "cycle_phase": phase,
                        "confidence": confidence,
                        "detected_at": utc_now(),
                    }
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["coin_id", "timeframe"],
                    set_={
                        "cycle_phase": stmt.excluded.cycle_phase,
                        "confidence": stmt.excluded.confidence,
                        "detected_at": stmt.excluded.detected_at,
                    },
                )
                await self.session.execute(stmt)
                items.append(
                    {
                        "status": "ok",
                        "coin_id": int(coin.id),
                        "timeframe": timeframe,
                        "cycle_phase": phase,
                        "confidence": confidence,
                    }
                )
        await self._uow.flush()
        return {"status": "ok", "items": items, "cycles": len(items)}

    async def _refresh_discovered_patterns(self) -> dict[str, object]:
        if not await self._feature_enabled("pattern_discovery_engine"):
            return {"status": "skipped", "reason": "pattern_discovery_disabled"}

        aggregates: dict[tuple[str, int], list[tuple[float, float]]] = defaultdict(list)
        coins = await self._coins.list(enabled_only=True)
        for coin in coins:
            for candle_config in coin.candles_config or []:
                timeframe = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}.get(str(candle_config["interval"]))
                if timeframe is None:
                    continue
                candles = await self._fetch_candle_points(
                    coin_id=int(coin.id),
                    timeframe=timeframe,
                    limit=min(int(candle_config.get("retention_bars", 220)), 240),
                )
                if len(candles) < DISCOVERY_WINDOW_BARS + DISCOVERY_HORIZON:
                    continue
                closes = [float(item.close) for item in candles]
                lows = [float(item.low) for item in candles]
                for start_index in range(
                    0, len(candles) - DISCOVERY_WINDOW_BARS - DISCOVERY_HORIZON + 1, DISCOVERY_STEP
                ):
                    window_closes = closes[start_index : start_index + DISCOVERY_WINDOW_BARS]
                    future_closes = closes[
                        start_index + DISCOVERY_WINDOW_BARS : start_index + DISCOVERY_WINDOW_BARS + DISCOVERY_HORIZON
                    ]
                    future_lows = lows[
                        start_index + DISCOVERY_WINDOW_BARS : start_index + DISCOVERY_WINDOW_BARS + DISCOVERY_HORIZON
                    ]
                    structure_hash = _window_signature(window_closes)
                    entry = window_closes[-1]
                    avg_return = (future_closes[-1] - entry) / max(entry, 1e-9)
                    avg_drawdown = (min(future_lows) - entry) / max(entry, 1e-9)
                    aggregates[(structure_hash, timeframe)].append((avg_return, avg_drawdown))

        rows: list[dict[str, object]] = []
        for (structure_hash, timeframe), outcomes in aggregates.items():
            sample_size = len(outcomes)
            if sample_size < 3:
                continue
            avg_return = sum(item[0] for item in outcomes) / sample_size
            avg_drawdown = sum(item[1] for item in outcomes) / sample_size
            confidence = max(min(0.5 + sample_size / 20 + avg_return - abs(avg_drawdown) * 0.5, 0.95), 0.1)
            rows.append(
                {
                    "structure_hash": structure_hash,
                    "timeframe": timeframe,
                    "sample_size": sample_size,
                    "avg_return": avg_return,
                    "avg_drawdown": avg_drawdown,
                    "confidence": confidence,
                }
            )

        await self._replace_discovered_patterns(rows=rows)
        return {"status": "ok", "patterns": len(rows)}

    async def _refresh_strategies(self) -> dict[str, object]:
        cutoff = utc_now() - timedelta(days=STRATEGY_LOOKBACK_DAYS)
        signals = (
            (
                await self.session.execute(
                    select(Signal)
                    .where(Signal.candle_timestamp >= cutoff, Signal.signal_type.like("pattern_%"))
                    .order_by(
                        Signal.coin_id.asc(),
                        Signal.timeframe.asc(),
                        Signal.candle_timestamp.asc(),
                        Signal.created_at.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        grouped: dict[tuple[int, int], dict[object, list[Signal]]] = defaultdict(lambda: defaultdict(list))
        for signal in signals:
            grouped[(int(signal.coin_id), int(signal.timeframe))][ensure_utc(signal.candle_timestamp)].append(signal)

        coin_rows = (
            (
                await self.session.execute(
                    select(Coin).options(selectinload(Coin.sector)).where(Coin.deleted_at.is_(None))
                )
            )
            .scalars()
            .all()
        )
        coin_map = {int(coin.id): coin for coin in coin_rows}
        observations_by_candidate: dict[StrategyCandidate, list[StrategyObservation]] = defaultdict(list)

        for (coin_id, timeframe), groups in grouped.items():
            if not groups:
                continue
            ordered_timestamps = sorted(groups)
            start = ordered_timestamps[0] - timedelta(minutes=timeframe * 220)
            end = ordered_timestamps[-1] + timedelta(
                minutes=timeframe * (HORIZON_BARS_BY_TIMEFRAME.get(timeframe, 8) + 1)
            )
            candles = await self._fetch_candle_points_between(
                coin_id=coin_id,
                timeframe=timeframe,
                window_start=start,
                window_end=end,
            )
            if len(candles) < 30:
                continue
            index_map = {ensure_utc(candle.timestamp): index for index, candle in enumerate(candles)}
            coin = coin_map.get(coin_id)
            sector = coin.sector.name if coin is not None and coin.sector is not None else "*"
            sector_metric = (
                await self.session.get(SectorMetric, (int(coin.sector_id), timeframe))
                if coin is not None and coin.sector_id is not None
                else None
            )
            for candle_timestamp in ordered_timestamps:
                signal_stack = groups[candle_timestamp]
                outcome = _signal_outcome(
                    signals=signal_stack,
                    candles=candles,
                    index_map=index_map,
                    timeframe=timeframe,
                    candle_timestamp=candle_timestamp,
                )
                if outcome is None:
                    continue
                open_timestamp = candle_timestamp - timedelta(minutes=timeframe)
                candle_index = index_map.get(open_timestamp)
                if candle_index is None:
                    continue
                window = candles[max(0, candle_index - 199) : candle_index + 1]
                if len(window) < 20:
                    continue
                regime, cycle = _context_from_window(window=window, signals=signal_stack, sector_metric=sector_metric)
                for candidate in _candidate_definitions(
                    timeframe=timeframe,
                    signals=signal_stack,
                    regime=regime,
                    sector=sector,
                    cycle=cycle,
                ):
                    observations_by_candidate[candidate].append(
                        StrategyObservation(
                            candidate=candidate,
                            terminal_return=outcome[0],
                            drawdown=outcome[1],
                            success=outcome[2],
                        )
                    )

        ranked_candidates: list[tuple[StrategyCandidate, int, float, float, float, float, bool]] = []
        for candidate, observations in observations_by_candidate.items():
            sample_size = len(observations)
            if sample_size < MIN_DISCOVERY_SAMPLE:
                continue
            returns = [item.terminal_return for item in observations]
            win_rate = sum(1 for item in observations if item.success) / sample_size
            avg_return = sum(returns) / sample_size
            sharpe_ratio = _sharpe_ratio(returns)
            max_drawdown = min(item.drawdown for item in observations)
            enabled = _strategy_enabled(sample_size, win_rate, avg_return, sharpe_ratio, max_drawdown)
            ranked_candidates.append(
                (candidate, sample_size, win_rate, avg_return, sharpe_ratio, max_drawdown, enabled)
            )

        ranked_candidates.sort(
            key=lambda item: (item[6], item[4], item[2], item[3], item[1], -item[5]),
            reverse=True,
        )
        ranked_candidates = ranked_candidates[:MAX_DISCOVERED_STRATEGIES]

        existing_rows = (
            (
                await self.session.execute(
                    select(Strategy).options(selectinload(Strategy.rules), selectinload(Strategy.performance))
                )
            )
            .scalars()
            .all()
        )
        existing_by_name = {row.name: row for row in existing_rows}
        seen_ids: set[int] = set()
        for candidate, sample_size, win_rate, avg_return, sharpe_ratio, max_drawdown, enabled in ranked_candidates:
            name = _strategy_name(candidate)
            row = existing_by_name.get(name)
            if row is None:
                row = Strategy(name=name, description=_strategy_description(candidate), enabled=enabled)
                self.session.add(row)
                await self._uow.flush()
                existing_by_name[name] = row
            else:
                row.description = _strategy_description(candidate)
                row.enabled = enabled
            row.rules = [
                StrategyRule(
                    strategy_id=int(row.id),
                    pattern_slug=token,
                    regime=candidate.regime,
                    sector=candidate.sector,
                    cycle=candidate.cycle,
                    min_confidence=candidate.min_confidence,
                )
                for token in candidate.tokens
            ]
            if row.performance is None:
                row.performance = StrategyPerformance(strategy_id=int(row.id))
            row.performance.sample_size = sample_size
            row.performance.win_rate = win_rate
            row.performance.avg_return = avg_return
            row.performance.sharpe_ratio = sharpe_ratio
            row.performance.max_drawdown = max_drawdown
            row.performance.updated_at = utc_now()
            seen_ids.add(int(row.id))
        for row in existing_by_name.values():
            if int(row.id) not in seen_ids:
                row.enabled = False
        await self._uow.flush()
        return {
            "status": "ok",
            "strategies": len(ranked_candidates),
            "enabled": sum(1 for item in ranked_candidates if item[6]),
        }


class PatternBootstrapService(_PatternTaskSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternBootstrapService")

    async def bootstrap_scan(self, *, symbol: str | None = None, force: bool = False) -> dict[str, object]:
        from src.apps.market_data.services import (
            get_coin_by_symbol_async,
            list_coin_symbols_ready_for_latest_sync_async,
        )

        if symbol is not None:
            coin = await get_coin_by_symbol_async(self.session, symbol)
            if coin is None:
                return {"status": "error", "reason": "coin_not_found", "symbol": symbol.upper()}
            result = await self._bootstrap_coin(coin=coin, force=force)
            await self._uow.commit()
            return {"status": "ok", "coins": 1, "items": [result]}

        coin_symbols = await list_coin_symbols_ready_for_latest_sync_async(self.session)
        items = []
        for coin_symbol in coin_symbols:
            coin = await get_coin_by_symbol_async(self.session, coin_symbol)
            if coin is None:
                continue
            items.append(await self._bootstrap_coin(coin=coin, force=force))
            await self._uow.commit()
        return {
            "status": "ok",
            "coins": len(coin_symbols),
            "created": sum(int(item.get("created", 0)) for item in items),
            "items": items,
        }

    async def _bootstrap_coin(self, *, coin: Coin, force: bool) -> dict[str, object]:
        if not await self._feature_enabled("pattern_detection"):
            return {"status": "skipped", "reason": "pattern_detection_disabled", "coin_id": int(coin.id)}
        history_count = int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(Signal)
                    .where(
                        Signal.coin_id == int(coin.id),
                        Signal.signal_type.like("pattern_%"),
                    )
                )
            ).scalar_one()
            or 0
        )
        if not force and history_count > 0:
            return {
                "status": "skipped",
                "reason": "pattern_history_exists",
                "coin_id": int(coin.id),
                "symbol": coin.symbol,
            }

        total_created = 0
        total_detections = 0
        interval_to_timeframe = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
        for candle_config in coin.candles_config or []:
            timeframe = interval_to_timeframe.get(str(candle_config["interval"]))
            if timeframe is None:
                continue
            detectors = await self._load_active_detectors(timeframe=timeframe)
            if not detectors:
                continue
            candles = await self._fetch_candle_points(
                coin_id=int(coin.id),
                timeframe=timeframe,
                limit=int(candle_config.get("retention_bars", 200)),
            )
            if len(candles) < 30:
                continue
            success_cache = await self._pattern_success_cache(
                timeframe=timeframe,
                slugs={detector.slug for detector in detectors},
                regimes=set(),
            )
            detections: list[PatternDetection] = []
            for index in range(29, len(candles)):
                window = candles[max(0, index - 199) : index + 1]
                indicators = current_indicator_map(window)
                for detector in detectors:
                    if not detector.enabled or timeframe not in detector.supported_timeframes:
                        continue
                    if not dependencies_satisfied(detector, indicators):
                        continue
                    for detection in detector.detect(window, indicators):
                        adjusted = apply_pattern_context(
                            detection=detection,
                            detector=detector,
                            indicators=indicators,
                            regime=None,
                        )
                        if adjusted is None:
                            continue
                        validated = apply_pattern_success_validation(
                            cast(Any, None),
                            detection=adjusted,
                            timeframe=timeframe,
                            market_regime=None,
                            coin_id=int(coin.id),
                            emit_events=True,
                            snapshot_cache=success_cache,
                        )
                        if validated is not None:
                            detections.append(validated)
            rows = [
                {
                    "coin_id": int(coin.id),
                    "timeframe": timeframe,
                    "signal_type": detection.signal_type,
                    "confidence": detection.confidence,
                    "priority_score": 0.0,
                    "context_score": 1.0,
                    "regime_alignment": 1.0,
                    "market_regime": str(detection.attributes.get("regime"))
                    if detection.attributes.get("regime") is not None
                    else None,
                    "candle_timestamp": detection.candle_timestamp,
                }
                for detection in detections
            ]
            total_detections += len(detections)
            total_created += await self._upsert_signals(rows=rows)
        coin.history_backfill_completed_at = utc_now()
        await self._uow.flush()
        return {
            "status": "ok",
            "coin_id": int(coin.id),
            "symbol": coin.symbol,
            "detections": total_detections,
            "created": total_created,
        }


class PatternEvaluationService(_PatternTaskSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternEvaluationService")

    async def run(self) -> dict[str, object]:
        history_result = await self._refresh_signal_history(lookback_days=365)
        statistics_result = await self._refresh_pattern_statistics()
        context_result = await self._refresh_recent_signal_contexts(lookback_days=30)
        decision_result = await self._refresh_investment_decisions(lookback_days=30, emit_events=False)
        final_signal_result = await self._refresh_final_signals(lookback_days=30, emit_events=False)
        await self._uow.commit()
        return {
            "status": "ok",
            "signal_history": history_result,
            "statistics": statistics_result,
            "context": context_result,
            "decisions": decision_result,
            "final_signals": final_signal_result,
        }


class PatternSignalContextService(_PatternTaskSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternSignalContextService")

    async def enrich(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: str | None = None,
    ) -> dict[str, object]:
        context = await self._enrich_signal_context(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            candle_timestamp=candle_timestamp,
        )
        decision = await self._evaluate_investment_decision(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            emit_event=False,
        )
        final_signal = await self._evaluate_final_signal(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            emit_event=False,
        )
        await self._uow.commit()
        return {"status": "ok", "context": context, "decision": decision, "final_signal": final_signal}


class PatternMarketStructureService(_PatternTaskSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternMarketStructureService")

    async def refresh(self) -> dict[str, object]:
        sectors = await self._refresh_sector_metrics()
        cycles = await self._refresh_market_cycles()
        context = await self._refresh_recent_signal_contexts(lookback_days=30)
        decisions = await self._refresh_investment_decisions(lookback_days=30, emit_events=False)
        final_signals = await self._refresh_final_signals(lookback_days=30, emit_events=False)
        await self._uow.commit()
        return {
            "status": "ok",
            "sectors": sectors,
            "cycles": cycles,
            "context": context,
            "decisions": decisions,
            "final_signals": final_signals,
        }


class PatternDiscoveryService(_PatternTaskSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternDiscoveryService")

    async def refresh(self) -> dict[str, object]:
        result = await self._refresh_discovered_patterns()
        await self._uow.commit()
        return result


class PatternStrategyService(_PatternTaskSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternStrategyService")

    async def refresh(self) -> dict[str, object]:
        strategies = await self._refresh_strategies()
        decisions = await self._refresh_investment_decisions(lookback_days=30, emit_events=False)
        final_signals = await self._refresh_final_signals(lookback_days=30, emit_events=False)
        await self._uow.commit()
        return {
            "status": "ok",
            "strategies": strategies,
            "decisions": decisions,
            "final_signals": final_signals,
        }


__all__ = [
    "PatternBootstrapService",
    "PatternDiscoveryService",
    "PatternEvaluationService",
    "PatternMarketStructureService",
    "PatternSignalContextService",
    "PatternStrategyService",
]
