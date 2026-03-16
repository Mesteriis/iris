from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol, cast

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.apps.cross_market.models import Sector, SectorMetric
from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.candles import CandlePoint
from src.apps.market_data.domain import ensure_utc
from src.apps.market_data.models import Candle, Coin
from src.apps.patterns.domain.regime import RegimeRead, detect_market_regime, read_regime_details
from src.apps.patterns.domain.utils import current_indicator_map
from src.apps.patterns.engines.contracts import (
    PatternCoinMetricsSnapshot,
    PatternRuntimeSignalSnapshot,
    PatternSectorMetricSnapshot,
)
from src.apps.patterns.models import DiscoveredPattern, MarketCycle, PatternFeature, PatternRegistry, PatternStatistic
from src.apps.patterns.query_builders import pattern_signal_ordering as _pattern_signal_ordering
from src.apps.patterns.query_builders import signal_select as _signal_select
from src.apps.patterns.read_models import (
    CoinRegimeReadModel,
    DiscoveredPatternReadModel,
    MarketCycleReadModel,
    PatternFeatureReadModel,
    PatternReadModel,
    PatternSignalReadModel,
    PatternStatisticReadModel,
    RegimeTimeframeReadModel,
    SectorMetricReadModel,
    SectorMetricsReadModel,
    SectorNarrativeReadModel,
    SectorReadModel,
    coin_regime_read_model,
    discovered_pattern_read_model_from_orm,
    market_cycle_read_model_from_mapping,
    pattern_feature_read_model_from_orm,
    pattern_read_model_from_orm,
    pattern_signal_read_model_from_mapping,
    pattern_statistic_read_model_from_orm,
    regime_timeframe_read_model,
    sector_metric_read_model_from_mapping,
    sector_narrative_read_model,
    sector_read_model_from_mapping,
)
from src.apps.signals.models import Signal
from src.core.db.persistence import AsyncQueryService


class _SignalRowLike(Protocol):
    coin_id: object
    timeframe: object
    candle_timestamp: datetime
    market_regime_details: dict[str, Any] | None
    signal_market_regime: str | None
    market_regime: str | None
    _mapping: Mapping[str, object]


class _ClusterSignalRowLike(Protocol):
    coin_id: object
    timeframe: object
    candle_timestamp: datetime
    signal_type: object


def _row_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"Expected int-compatible row value, got {type(value).__name__}")


class PatternQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="patterns", service_name="PatternQueryService")

    @staticmethod
    def _serialize_pattern_statistics(
        stats: Sequence[PatternStatistic],
    ) -> dict[str, tuple[PatternStatisticReadModel, ...]]:
        stats_by_slug: dict[str, list[PatternStatisticReadModel]] = defaultdict(list)
        for stat in stats:
            stats_by_slug[str(stat.pattern_slug)].append(pattern_statistic_read_model_from_orm(stat))
        return {slug: tuple(items) for slug, items in stats_by_slug.items()}

    @staticmethod
    def capital_wave_bucket(
        coin: Coin,
        metrics: CoinMetrics | None,
        *,
        top_sector_id: int | None,
    ) -> str:
        market_cap = float(metrics.market_cap or 0.0) if metrics is not None else 0.0
        if coin.symbol == "BTCUSD":
            return "btc"
        if market_cap >= 15_000_000_000:
            return "large_caps"
        if top_sector_id is not None and coin.sector_id == top_sector_id:
            return "sector_leaders"
        if market_cap >= 1_000_000_000:
            return "mid_caps"
        return "micro_caps"

    async def fetch_candle_points(
        self,
        *,
        coin_id: int,
        timeframe: int,
        limit: int,
    ) -> list[CandlePoint]:
        rows = (
            await self.session.execute(
                select(Candle.timestamp, Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume)
                .where(Candle.coin_id == coin_id, Candle.timeframe == timeframe)
                .order_by(Candle.timestamp.desc())
                .limit(max(limit, 1))
            )
        ).all()
        return [
            CandlePoint(
                timestamp=ensure_utc(row.timestamp),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume) if row.volume is not None else None,
            )
            for row in reversed(rows)
        ]

    async def compute_live_regimes(
        self,
        coin_id: int,
    ) -> tuple[RegimeTimeframeReadModel, ...]:
        items: list[RegimeTimeframeReadModel] = []
        for timeframe in (15, 60, 240, 1440):
            candles = await self.fetch_candle_points(coin_id=coin_id, timeframe=timeframe, limit=200)
            if len(candles) < 20:
                continue
            regime, confidence = detect_market_regime(current_indicator_map(candles))
            items.append(regime_timeframe_read_model(timeframe=timeframe, regime=regime, confidence=confidence))
        return tuple(items)

    async def cluster_membership_map(
        self,
        rows: Sequence[_SignalRowLike],
    ) -> dict[tuple[int, int, datetime], tuple[str, ...]]:
        if not rows:
            return {}
        coin_ids = sorted({_row_int(row.coin_id) for row in rows})
        timeframes = sorted({_row_int(row.timeframe) for row in rows})
        timestamps = sorted({row.candle_timestamp for row in rows})
        cluster_rows = cast(
            Sequence[_ClusterSignalRowLike],
            (
                await self.session.execute(
                select(Signal.coin_id, Signal.timeframe, Signal.candle_timestamp, Signal.signal_type).where(
                    Signal.coin_id.in_(coin_ids),
                    Signal.timeframe.in_(timeframes),
                    Signal.candle_timestamp.in_(timestamps),
                    Signal.signal_type.like("pattern_cluster_%"),
                )
            )
            ).all(),
        )
        membership: dict[tuple[int, int, datetime], list[str]] = defaultdict(list)
        for row in cluster_rows:
            membership[(_row_int(row.coin_id), _row_int(row.timeframe), row.candle_timestamp)].append(str(row.signal_type))
        return {key: tuple(value) for key, value in membership.items()}

    async def serialize_signal_rows(
        self,
        rows: Sequence[_SignalRowLike],
    ) -> tuple[PatternSignalReadModel, ...]:
        membership = await self.cluster_membership_map(rows)
        items: list[PatternSignalReadModel] = []
        for row in rows:
            coin_id = _row_int(row.coin_id)
            timeframe = _row_int(row.timeframe)
            regime_snapshot = read_regime_details(row.market_regime_details, timeframe)
            market_regime = row.signal_market_regime or (
                regime_snapshot.regime if regime_snapshot is not None else row.market_regime
            )
            items.append(
                pattern_signal_read_model_from_mapping(
                    row._mapping,
                    cluster_membership=membership.get((coin_id, timeframe, row.candle_timestamp), ()),
                    market_regime=market_regime,
                )
            )
        return tuple(items)

    async def coin_bar_return(
        self,
        *,
        coin_id: int,
        timeframe: int,
    ) -> tuple[float | None, float | None]:
        candles = await self.fetch_candle_points(coin_id=coin_id, timeframe=timeframe, limit=25)
        if len(candles) < 2:
            return None, None
        previous = float(candles[-2].close)
        current = float(candles[-1].close)
        change = (current - previous) / previous if previous else 0.0
        closes = [float(item.close) for item in candles[-20:]]
        mean_close = sum(closes) / len(closes)
        volatility = (sum((value - mean_close) ** 2 for value in closes) / len(closes)) ** 0.5 if closes else 0.0
        return change, (volatility / current if current else 0.0)

    async def list_signal_types_at_timestamp(
        self,
        *,
        coin_id: int,
        timeframe: int,
        timestamp: object,
    ) -> tuple[str, ...]:
        rows = (
            (
                await self.session.execute(
                    select(Signal.signal_type).where(
                        Signal.coin_id == int(coin_id),
                        Signal.timeframe == int(timeframe),
                        Signal.candle_timestamp == timestamp,
                    )
                )
            )
            .scalars()
            .all()
        )
        return tuple(_signal_type_name(value) for value in rows)

    async def list_runtime_signal_snapshots_at_timestamp(
        self,
        *,
        coin_id: int,
        timeframe: int,
        timestamp: object,
    ) -> tuple[PatternRuntimeSignalSnapshot, ...]:
        rows = (
            await self.session.execute(
                select(Signal.signal_type, Signal.confidence).where(
                    Signal.coin_id == int(coin_id),
                    Signal.timeframe == int(timeframe),
                    Signal.candle_timestamp == timestamp,
                    Signal.signal_type.like("pattern_%"),
                )
            )
        ).all()
        return tuple(
            PatternRuntimeSignalSnapshot(
                signal_type=_signal_type_name(row.signal_type),
                confidence=float(row.confidence or 0.0),
            )
            for row in rows
        )

    async def list_runtime_signal_snapshots_between(
        self,
        *,
        coin_id: int,
        timeframe: int,
        window_start: object,
        window_end: object,
    ) -> tuple[PatternRuntimeSignalSnapshot, ...]:
        rows = (
            await self.session.execute(
                select(Signal.signal_type, Signal.confidence).where(
                    Signal.coin_id == int(coin_id),
                    Signal.timeframe == int(timeframe),
                    Signal.candle_timestamp >= window_start,
                    Signal.candle_timestamp <= window_end,
                    Signal.signal_type.like("pattern_%"),
                )
            )
        ).all()
        return tuple(
            PatternRuntimeSignalSnapshot(
                signal_type=_signal_type_name(row.signal_type),
                confidence=float(row.confidence or 0.0),
            )
            for row in rows
        )

    async def count_pattern_signals(self, *, coin_id: int, timeframe: int) -> int:
        return int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(Signal)
                    .where(
                        Signal.coin_id == int(coin_id),
                        Signal.timeframe == int(timeframe),
                        Signal.signal_type.like("pattern_%"),
                        ~Signal.signal_type.like("pattern_cluster_%"),
                        ~Signal.signal_type.like("pattern_hierarchy_%"),
                    )
                )
            ).scalar_one()
            or 0
        )

    async def count_cluster_signals(self, *, coin_id: int, timeframe: int) -> int:
        return int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(Signal)
                    .where(
                        Signal.coin_id == int(coin_id),
                        Signal.timeframe == int(timeframe),
                        Signal.signal_type.like("pattern_cluster_%"),
                    )
                )
            ).scalar_one()
            or 0
        )

    async def get_coin_metrics_snapshot(
        self,
        *,
        coin_id: int,
        timeframe: int | None = None,
    ) -> PatternCoinMetricsSnapshot | None:
        row = await self.session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(coin_id)).limit(1))
        if row is None:
            return None
        resolved_regime = None
        if timeframe is not None:
            details = read_regime_details(row.market_regime_details, int(timeframe))
            resolved_regime = details.regime if details is not None else row.market_regime
        return PatternCoinMetricsSnapshot(
            trend_score=int(row.trend_score) if row.trend_score is not None else None,
            market_regime=str(row.market_regime) if row.market_regime is not None else None,
            resolved_regime=str(resolved_regime) if resolved_regime is not None else None,
            volatility=float(row.volatility) if row.volatility is not None else None,
            price_current=float(row.price_current) if row.price_current is not None else None,
        )

    async def get_sector_metric_snapshot(
        self,
        *,
        coin_id: int,
        timeframe: int,
    ) -> PatternSectorMetricSnapshot | None:
        coin = await self.session.scalar(select(Coin).where(Coin.id == int(coin_id), Coin.deleted_at.is_(None)).limit(1))
        if coin is None or coin.sector_id is None:
            return None
        row = await self.session.get(SectorMetric, (int(coin.sector_id), int(timeframe)))
        if row is None:
            return None
        return PatternSectorMetricSnapshot(
            sector_strength=float(row.sector_strength) if row.sector_strength is not None else None,
            capital_flow=float(row.capital_flow) if row.capital_flow is not None else None,
        )

    async def build_sector_narratives(self) -> tuple[SectorNarrativeReadModel, ...]:
        metrics = (
            (
                await self.session.execute(
                    select(SectorMetric)
                    .options(selectinload(SectorMetric.sector))
                    .order_by(SectorMetric.timeframe.asc(), SectorMetric.relative_strength.desc())
                )
            )
            .scalars()
            .all()
        )
        by_timeframe: dict[int, list[SectorMetric]] = defaultdict(list)
        for metric in metrics:
            by_timeframe[int(metric.timeframe)].append(metric)

        btc_metrics = (
            await self.session.execute(
                select(CoinMetrics).join(Coin, CoinMetrics.coin_id == Coin.id).where(Coin.symbol == "BTCUSD")
            )
        ).scalar_one_or_none()
        market_caps = (
            (
                await self.session.execute(
                    select(CoinMetrics.market_cap)
                    .join(Coin, CoinMetrics.coin_id == Coin.id)
                    .where(Coin.asset_type == "crypto", Coin.deleted_at.is_(None))
                )
            )
            .scalars()
            .all()
        )
        total_market_cap = sum(float(value or 0.0) for value in market_caps)
        btc_dominance = (
            float(btc_metrics.market_cap or 0.0) / total_market_cap
            if btc_metrics is not None and total_market_cap > 0
            else None
        )
        crypto_coins = (
            (
                await self.session.execute(
                    select(Coin)
                    .where(Coin.asset_type == "crypto", Coin.enabled.is_(True), Coin.deleted_at.is_(None))
                    .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
                )
            )
            .scalars()
            .all()
        )
        metrics_by_coin: dict[int, CoinMetrics] = {}
        if crypto_coins:
            metrics_rows = (
                (
                    await self.session.execute(
                        select(CoinMetrics).where(CoinMetrics.coin_id.in_([coin.id for coin in crypto_coins]))
                    )
                )
                .scalars()
                .all()
            )
            metrics_by_coin = {int(item.coin_id): item for item in metrics_rows}

        items: list[SectorNarrativeReadModel] = []
        for timeframe, timeframe_items in by_timeframe.items():
            leader = next((item for item in timeframe_items if item.sector is not None), None)
            top_sector = leader.sector.name if leader is not None and leader.sector is not None else None
            top_sector_id = int(leader.sector_id) if leader is not None else None
            btc_price_change_24h = float(btc_metrics.price_change_24h or 0.0) if btc_metrics is not None else 0.0
            if btc_dominance is None:
                rotation_state = None
            elif btc_dominance >= 0.45 and btc_price_change_24h >= 0:
                rotation_state = "btc_dominance_rising"
            elif btc_dominance < 0.45 and btc_price_change_24h < 0:
                rotation_state = "btc_dominance_falling"
            else:
                rotation_state = "sector_leadership_change" if top_sector is not None else None

            bucket_scores: dict[str, list[float]] = defaultdict(list)
            for coin in crypto_coins:
                metrics_row = metrics_by_coin.get(int(coin.id))
                price_change, _ = await self.coin_bar_return(coin_id=int(coin.id), timeframe=timeframe)
                if price_change is None:
                    continue
                bucket = self.capital_wave_bucket(coin, metrics_row, top_sector_id=top_sector_id)
                market_cap_weight = (
                    min(float(metrics_row.market_cap or 0.0) / 25_000_000_000, 2.0) if metrics_row is not None else 0.0
                )
                volume_flow = float(metrics_row.volume_change_24h or 0.0) / 100 if metrics_row is not None else 0.0
                bucket_scores[bucket].append(price_change + volume_flow + (market_cap_weight * price_change))

            capital_wave = None
            if bucket_scores:
                capital_wave = max(
                    ("btc", "large_caps", "sector_leaders", "mid_caps", "micro_caps"),
                    key=lambda bucket: sum(bucket_scores.get(bucket, [])) / len(bucket_scores.get(bucket, [1e-9])),
                )
            items.append(
                sector_narrative_read_model(
                    timeframe=timeframe,
                    top_sector=top_sector,
                    rotation_state=rotation_state,
                    btc_dominance=btc_dominance,
                    capital_wave=capital_wave,
                )
            )
        return tuple(items)

    async def list_patterns(self) -> tuple[PatternReadModel, ...]:
        self._log_debug("query.list_patterns", mode="read")
        rows = (
            (
                await self.session.execute(
                    select(PatternRegistry).order_by(PatternRegistry.category.asc(), PatternRegistry.slug.asc())
                )
            )
            .scalars()
            .all()
        )
        stats = (
            (
                await self.session.execute(
                    select(PatternStatistic).order_by(
                        PatternStatistic.pattern_slug.asc(), PatternStatistic.timeframe.asc()
                    )
                )
            )
            .scalars()
            .all()
        )
        stats_by_slug = self._serialize_pattern_statistics(stats)
        items = tuple(pattern_read_model_from_orm(row, stats_by_slug.get(str(row.slug), ())) for row in rows)
        self._log_debug("query.list_patterns.result", mode="read", count=len(items))
        return items

    async def get_pattern_read_by_slug(self, slug: str) -> PatternReadModel | None:
        normalized_slug = slug.strip()
        self._log_debug("query.get_pattern_read_by_slug", mode="read", slug=normalized_slug)
        row = await self.session.get(PatternRegistry, normalized_slug)
        if row is None:
            self._log_debug("query.get_pattern_read_by_slug.result", mode="read", found=False)
            return None
        stats = (
            (
                await self.session.execute(
                    select(PatternStatistic)
                    .where(PatternStatistic.pattern_slug == normalized_slug)
                    .order_by(PatternStatistic.timeframe.asc())
                )
            )
            .scalars()
            .all()
        )
        item = pattern_read_model_from_orm(
            row,
            tuple(pattern_statistic_read_model_from_orm(stat) for stat in stats),
        )
        self._log_debug("query.get_pattern_read_by_slug.result", mode="read", found=True)
        return item

    async def list_pattern_features(self) -> tuple[PatternFeatureReadModel, ...]:
        self._log_debug("query.list_pattern_features", mode="read")
        rows = (
            (await self.session.execute(select(PatternFeature).order_by(PatternFeature.feature_slug.asc())))
            .scalars()
            .all()
        )
        items = tuple(pattern_feature_read_model_from_orm(row) for row in rows)
        self._log_debug("query.list_pattern_features.result", mode="read", count=len(items))
        return items

    async def get_pattern_feature_read_by_slug(self, feature_slug: str) -> PatternFeatureReadModel | None:
        normalized_slug = feature_slug.strip()
        self._log_debug("query.get_pattern_feature_read_by_slug", mode="read", feature_slug=normalized_slug)
        row = await self.session.get(PatternFeature, normalized_slug)
        if row is None:
            self._log_debug("query.get_pattern_feature_read_by_slug.result", mode="read", found=False)
            return None
        item = pattern_feature_read_model_from_orm(row)
        self._log_debug("query.get_pattern_feature_read_by_slug.result", mode="read", found=True)
        return item

    async def list_discovered_patterns(
        self,
        *,
        timeframe: int | None = None,
        limit: int = 200,
    ) -> tuple[DiscoveredPatternReadModel, ...]:
        self._log_debug("query.list_discovered_patterns", mode="read", timeframe=timeframe, limit=limit)
        stmt = (
            select(DiscoveredPattern)
            .order_by(DiscoveredPattern.confidence.desc(), DiscoveredPattern.sample_size.desc())
            .limit(max(limit, 1))
        )
        if timeframe is not None:
            stmt = stmt.where(DiscoveredPattern.timeframe == timeframe)
        rows = (await self.session.execute(stmt)).scalars().all()
        items = tuple(discovered_pattern_read_model_from_orm(row) for row in rows)
        self._log_debug("query.list_discovered_patterns.result", mode="read", count=len(items))
        return items

    async def list_coin_patterns(
        self,
        symbol: str,
        *,
        limit: int = 200,
    ) -> tuple[PatternSignalReadModel, ...]:
        normalized_symbol = symbol.strip().upper()
        self._log_debug("query.list_coin_patterns", mode="read", symbol=normalized_symbol, limit=limit)
        rows = (
            await self.session.execute(
                _signal_select()
                .where(Coin.symbol == normalized_symbol, Signal.signal_type.like("pattern_%"))
                .order_by(*_pattern_signal_ordering())
                .limit(max(limit, 1))
            )
        ).all()
        items = await self.serialize_signal_rows(cast(Sequence[_SignalRowLike], rows))
        self._log_debug("query.list_coin_patterns.result", mode="read", count=len(items))
        return items

    async def get_coin_regime_read_by_symbol(self, symbol: str) -> CoinRegimeReadModel | None:
        normalized_symbol = symbol.strip().upper()
        self._log_debug("query.get_coin_regime_read_by_symbol", mode="read", symbol=normalized_symbol)
        coin = await self.session.scalar(
            select(Coin).where(Coin.symbol == normalized_symbol, Coin.deleted_at.is_(None)).limit(1)
        )
        if coin is None:
            self._log_debug("query.get_coin_regime_read_by_symbol.result", mode="read", found=False)
            return None
        metrics = await self.session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin.id))
        regime_enabled = bool(
            (
                await self.session.execute(
                    select(PatternFeature.enabled).where(PatternFeature.feature_slug == "market_regime_engine")
                )
            ).scalar_one_or_none()
        )
        if not regime_enabled:
            items: tuple[RegimeTimeframeReadModel, ...] = ()
        elif metrics is not None and metrics.market_regime_details:
            regime_details: list[RegimeRead] = []
            for timeframe in (15, 60, 240, 1440):
                detail = read_regime_details(metrics.market_regime_details, timeframe)
                if detail is not None:
                    regime_details.append(detail)
            items = tuple(
                regime_timeframe_read_model(
                    timeframe=int(detail.timeframe),
                    regime=str(detail.regime),
                    confidence=float(detail.confidence),
                )
                for detail in regime_details
            )
        else:
            items = await self.compute_live_regimes(int(coin.id))
        item: CoinRegimeReadModel = coin_regime_read_model(
            coin_id=int(coin.id),
            symbol=str(coin.symbol),
            canonical_regime=str(metrics.market_regime)
            if metrics is not None and regime_enabled and metrics.market_regime is not None
            else None,
            items=items,
        )
        self._log_debug("query.get_coin_regime_read_by_symbol.result", mode="read", found=True, count=len(item.items))
        return item

    async def list_sectors(self) -> tuple[SectorReadModel, ...]:
        self._log_debug("query.list_sectors", mode="read")
        rows = (
            await self.session.execute(
                select(
                    Sector.id,
                    Sector.name,
                    Sector.description,
                    Sector.created_at,
                    func.count(Coin.id).label("coin_count"),
                )
                .outerjoin(Coin, and_(Coin.sector_id == Sector.id, Coin.deleted_at.is_(None), Coin.enabled.is_(True)))
                .group_by(Sector.id)
                .order_by(Sector.name.asc())
            )
        ).all()
        items = tuple(sector_read_model_from_mapping(cast(Mapping[str, object], row._mapping)) for row in rows)
        self._log_debug("query.list_sectors.result", mode="read", count=len(items))
        return items

    async def list_sector_metrics(
        self,
        *,
        timeframe: int | None = None,
    ) -> SectorMetricsReadModel:
        self._log_debug("query.list_sector_metrics", mode="read", timeframe=timeframe, loading_profile="full")
        stmt = (
            select(
                SectorMetric.sector_id,
                Sector.name,
                Sector.description,
                SectorMetric.timeframe,
                SectorMetric.sector_strength,
                SectorMetric.relative_strength,
                SectorMetric.capital_flow,
                SectorMetric.avg_price_change_24h,
                SectorMetric.avg_volume_change_24h,
                SectorMetric.volatility,
                SectorMetric.trend,
                SectorMetric.updated_at,
            )
            .join(Sector, Sector.id == SectorMetric.sector_id)
            .order_by(SectorMetric.timeframe.asc(), SectorMetric.relative_strength.desc())
        )
        if timeframe is not None:
            stmt = stmt.where(SectorMetric.timeframe == timeframe)
        rows = (await self.session.execute(stmt)).all()
        narratives = await self.build_sector_narratives()
        item = SectorMetricsReadModel(
            items=tuple(
                sector_metric_read_model_from_mapping(cast(Mapping[str, object], row._mapping)) for row in rows
            ),
            narratives=tuple(
                narrative for narrative in narratives if timeframe is None or narrative.timeframe == timeframe
            ),
        )
        self._log_debug(
            "query.list_sector_metrics.result",
            mode="read",
            count=len(item.items),
            narrative_count=len(item.narratives),
        )
        return item

    async def list_market_cycles(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
    ) -> tuple[MarketCycleReadModel, ...]:
        normalized_symbol = symbol.strip().upper() if symbol is not None else None
        self._log_debug(
            "query.list_market_cycles",
            mode="read",
            symbol=normalized_symbol,
            timeframe=timeframe,
        )
        stmt = (
            select(
                MarketCycle.coin_id,
                Coin.symbol,
                Coin.name,
                MarketCycle.timeframe,
                MarketCycle.cycle_phase,
                MarketCycle.confidence,
                MarketCycle.detected_at,
            )
            .join(Coin, Coin.id == MarketCycle.coin_id)
            .where(Coin.deleted_at.is_(None))
            .order_by(MarketCycle.confidence.desc(), Coin.sort_order.asc(), Coin.symbol.asc())
        )
        if normalized_symbol is not None:
            stmt = stmt.where(Coin.symbol == normalized_symbol)
        if timeframe is not None:
            stmt = stmt.where(MarketCycle.timeframe == timeframe)
        rows = (await self.session.execute(stmt)).all()
        items = tuple(market_cycle_read_model_from_mapping(cast(Mapping[str, object], row._mapping)) for row in rows)
        self._log_debug("query.list_market_cycles.result", mode="read", count=len(items))
        return items


__all__ = ["PatternQueryService"]


def _signal_type_name(value: object) -> str:
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    return str(value)
