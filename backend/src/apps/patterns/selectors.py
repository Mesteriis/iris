from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from src.apps.cross_market.models import Sector, SectorMetric
from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.models import Coin
from src.apps.market_data.service_layer import get_coin_by_symbol
from src.apps.patterns.domain.lifecycle import PatternLifecycleState
from src.apps.patterns.domain.narrative import build_sector_narratives
from src.apps.patterns.domain.regime import RegimeRead, compute_live_regimes, read_regime_details
from src.apps.patterns.domain.registry import feature_enabled
from src.apps.patterns.models import DiscoveredPattern, MarketCycle, PatternFeature, PatternRegistry, PatternStatistic
from src.apps.patterns.query_builders import pattern_signal_ordering
from src.apps.patterns.query_builders import signal_select
from src.apps.patterns.read_models import (
    CoinRegimeReadModel,
    DiscoveredPatternReadModel,
    MarketCycleReadModel,
    PatternFeatureReadModel,
    PatternReadModel,
    PatternSignalReadModel,
    PatternStatisticReadModel,
    RegimeTimeframeReadModel,
    SectorMetricsReadModel,
    SectorMetricReadModel,
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
from src.core.db.persistence import PERSISTENCE_LOGGER, sanitize_log_value


def _pattern_statistic_payload(item: PatternStatisticReadModel) -> dict[str, Any]:
    return {
        "timeframe": int(item.timeframe),
        "market_regime": str(item.market_regime),
        "sample_size": int(item.sample_size),
        "total_signals": int(item.total_signals),
        "successful_signals": int(item.successful_signals),
        "success_rate": float(item.success_rate),
        "avg_return": float(item.avg_return),
        "avg_drawdown": float(item.avg_drawdown),
        "temperature": float(item.temperature),
        "enabled": bool(item.enabled),
        "last_evaluated_at": item.last_evaluated_at,
        "updated_at": item.updated_at,
    }


def _pattern_payload(item: PatternReadModel) -> dict[str, Any]:
    return {
        "slug": str(item.slug),
        "category": str(item.category),
        "enabled": bool(item.enabled),
        "cpu_cost": int(item.cpu_cost),
        "lifecycle_state": str(item.lifecycle_state),
        "created_at": item.created_at,
        "statistics": [_pattern_statistic_payload(stat) for stat in item.statistics],
    }


def _pattern_feature_payload(item: PatternFeatureReadModel) -> dict[str, Any]:
    return {
        "feature_slug": str(item.feature_slug),
        "enabled": bool(item.enabled),
        "created_at": item.created_at,
    }


def _discovered_pattern_payload(item: DiscoveredPatternReadModel) -> dict[str, Any]:
    return {
        "structure_hash": str(item.structure_hash),
        "timeframe": int(item.timeframe),
        "sample_size": int(item.sample_size),
        "avg_return": float(item.avg_return),
        "avg_drawdown": float(item.avg_drawdown),
        "confidence": float(item.confidence),
    }


def _pattern_signal_payload(item: PatternSignalReadModel) -> dict[str, Any]:
    return {
        "id": int(item.id),
        "coin_id": int(item.coin_id),
        "symbol": str(item.symbol),
        "name": str(item.name),
        "sector": item.sector,
        "timeframe": int(item.timeframe),
        "signal_type": str(item.signal_type),
        "confidence": float(item.confidence),
        "priority_score": float(item.priority_score),
        "context_score": float(item.context_score),
        "regime_alignment": float(item.regime_alignment),
        "candle_timestamp": item.candle_timestamp,
        "created_at": item.created_at,
        "market_regime": item.market_regime,
        "cycle_phase": item.cycle_phase,
        "cycle_confidence": float(item.cycle_confidence) if item.cycle_confidence is not None else None,
        "cluster_membership": list(item.cluster_membership),
    }


def _coin_regime_payload(item: CoinRegimeReadModel) -> dict[str, Any]:
    return {
        "coin_id": int(item.coin_id),
        "symbol": str(item.symbol),
        "canonical_regime": item.canonical_regime,
        "items": [
            {
                "timeframe": int(regime.timeframe),
                "regime": str(regime.regime),
                "confidence": float(regime.confidence),
            }
            for regime in item.items
        ],
    }


def _sector_payload(item: SectorReadModel) -> dict[str, Any]:
    return {
        "id": int(item.id),
        "name": str(item.name),
        "description": item.description,
        "created_at": item.created_at,
        "coin_count": int(item.coin_count),
    }


def _sector_metric_payload(item: SectorMetricReadModel) -> dict[str, Any]:
    return {
        "sector_id": int(item.sector_id),
        "name": str(item.name),
        "description": item.description,
        "timeframe": int(item.timeframe),
        "sector_strength": float(item.sector_strength),
        "relative_strength": float(item.relative_strength),
        "capital_flow": float(item.capital_flow),
        "avg_price_change_24h": float(item.avg_price_change_24h),
        "avg_volume_change_24h": float(item.avg_volume_change_24h),
        "volatility": float(item.volatility),
        "trend": item.trend,
        "updated_at": item.updated_at,
    }


def _sector_narrative_payload(item: SectorNarrativeReadModel) -> dict[str, Any]:
    return {
        "timeframe": int(item.timeframe),
        "top_sector": item.top_sector,
        "rotation_state": item.rotation_state,
        "btc_dominance": float(item.btc_dominance) if item.btc_dominance is not None else None,
        "capital_wave": item.capital_wave,
    }


def _sector_metrics_payload(item: SectorMetricsReadModel) -> dict[str, Any]:
    return {
        "items": [_sector_metric_payload(metric) for metric in item.items],
        "narratives": [_sector_narrative_payload(narrative) for narrative in item.narratives],
    }


def _market_cycle_payload(item: MarketCycleReadModel) -> dict[str, Any]:
    return {
        "coin_id": int(item.coin_id),
        "symbol": str(item.symbol),
        "name": str(item.name),
        "timeframe": int(item.timeframe),
        "cycle_phase": str(item.cycle_phase),
        "confidence": float(item.confidence),
        "detected_at": item.detected_at,
    }


def _pattern_statistics_by_slug(db: Session) -> dict[str, tuple[PatternStatisticReadModel, ...]]:
    rows = db.scalars(
        select(PatternStatistic).order_by(PatternStatistic.pattern_slug.asc(), PatternStatistic.timeframe.asc())
    ).all()
    stats_by_slug: dict[str, list[PatternStatisticReadModel]] = defaultdict(list)
    for row in rows:
        stats_by_slug[str(row.pattern_slug)].append(pattern_statistic_read_model_from_orm(row))
    return {slug: tuple(items) for slug, items in stats_by_slug.items()}


def _get_pattern_read_model(db: Session, slug: str) -> PatternReadModel | None:
    normalized_slug = slug.strip()
    row = db.get(PatternRegistry, normalized_slug)
    if row is None:
        return None
    stats = db.scalars(
        select(PatternStatistic)
        .where(PatternStatistic.pattern_slug == normalized_slug)
        .order_by(PatternStatistic.timeframe.asc())
    ).all()
    return pattern_read_model_from_orm(
        row,
        tuple(pattern_statistic_read_model_from_orm(stat) for stat in stats),
    )


def _cluster_membership_map(
    db: Session,
    rows: Sequence[object],
) -> dict[tuple[int, int, object], tuple[str, ...]]:
    if not rows:
        return {}
    coin_ids = sorted({int(row.coin_id) for row in rows})
    timeframes = sorted({int(row.timeframe) for row in rows})
    timestamps = sorted({row.candle_timestamp for row in rows})
    cluster_rows = db.execute(
        select(Signal.coin_id, Signal.timeframe, Signal.candle_timestamp, Signal.signal_type).where(
            Signal.coin_id.in_(coin_ids),
            Signal.timeframe.in_(timeframes),
            Signal.candle_timestamp.in_(timestamps),
            Signal.signal_type.like("pattern_cluster_%"),
        )
    ).all()
    membership: dict[tuple[int, int, object], list[str]] = defaultdict(list)
    for row in cluster_rows:
        membership[(int(row.coin_id), int(row.timeframe), row.candle_timestamp)].append(str(row.signal_type))
    return {key: tuple(value) for key, value in membership.items()}


def _serialize_signal_rows(
    db: Session,
    rows: Sequence[object],
) -> tuple[PatternSignalReadModel, ...]:
    membership = _cluster_membership_map(db, rows)
    items: list[PatternSignalReadModel] = []
    for row in rows:
        regime_snapshot = read_regime_details(row.market_regime_details, int(row.timeframe))
        market_regime = row.signal_market_regime or (
            regime_snapshot.regime if regime_snapshot is not None else row.market_regime
        )
        items.append(
            pattern_signal_read_model_from_mapping(
                row._mapping if hasattr(row, "_mapping") else row,
                cluster_membership=membership.get((int(row.coin_id), int(row.timeframe), row.candle_timestamp), ()),
                market_regime=market_regime,
            )
        )
    return tuple(items)


def _coin_regime_read_model_for_symbol(db: Session, symbol: str) -> CoinRegimeReadModel | None:
    coin = get_coin_by_symbol(db, symbol)
    if coin is None:
        return None
    metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin.id))
    regime_enabled = feature_enabled(db, "market_regime_engine")
    items: tuple[RegimeTimeframeReadModel, ...]
    if not regime_enabled:
        items = ()
    elif metrics is not None and metrics.market_regime_details:
        items = tuple(
            regime_timeframe_read_model(
                timeframe=int(item.timeframe),
                regime=str(item.regime),
                confidence=float(item.confidence),
            )
            for timeframe in (15, 60, 240, 1440)
            if (item := read_regime_details(metrics.market_regime_details, timeframe)) is not None
        )
    else:
        items = tuple(
            regime_timeframe_read_model(
                timeframe=int(item.timeframe),
                regime=str(item.regime),
                confidence=float(item.confidence),
            )
            for item in compute_live_regimes(db, coin.id)
        )
    return coin_regime_read_model(
        coin_id=int(coin.id),
        symbol=str(coin.symbol),
        canonical_regime=metrics.market_regime if metrics is not None and regime_enabled else None,
        items=items,
    )


def _list_sector_narrative_read_models(
    db: Session,
    *,
    timeframe: int | None = None,
) -> tuple[SectorNarrativeReadModel, ...]:
    return tuple(
        sector_narrative_read_model(
            timeframe=int(item.timeframe),
            top_sector=item.top_sector,
            rotation_state=item.rotation_state,
            btc_dominance=item.btc_dominance,
            capital_wave=item.capital_wave,
        )
        for item in build_sector_narratives(db)
        if timeframe is None or item.timeframe == timeframe
    )


def _sector_metrics_read_model(
    db: Session,
    *,
    timeframe: int | None = None,
) -> SectorMetricsReadModel:
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
    rows = db.execute(stmt).all()
    return SectorMetricsReadModel(
        items=tuple(sector_metric_read_model_from_mapping(row._mapping) for row in rows),
        narratives=_list_sector_narrative_read_models(db, timeframe=timeframe),
    )


def _signal_select():
    return signal_select()


class PatternCompatibilityQuery:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _log(self, level: int, event: str, /, **fields: Any) -> None:
        PERSISTENCE_LOGGER.log(
            level,
            event,
            extra={
                "persistence": {
                    "event": event,
                    "component_type": "compatibility_query",
                    "domain": "patterns",
                    "component": "PatternCompatibilityQuery",
                    **{key: sanitize_log_value(value) for key, value in fields.items()},
                }
            },
        )

    def list_patterns(self) -> Sequence[dict[str, Any]]:
        self._log(logging.WARNING, "compat.list_patterns.deprecated", mode="read")
        rows = self._db.scalars(select(PatternRegistry).order_by(PatternRegistry.category.asc(), PatternRegistry.slug.asc())).all()
        stats_by_slug = _pattern_statistics_by_slug(self._db)
        return [_pattern_payload(pattern_read_model_from_orm(row, stats_by_slug.get(str(row.slug), ()))) for row in rows]

    def get_pattern(self, slug: str) -> dict[str, Any] | None:
        normalized_slug = slug.strip()
        self._log(logging.WARNING, "compat.get_pattern.deprecated", mode="read", slug=normalized_slug)
        item = _get_pattern_read_model(self._db, normalized_slug)
        return _pattern_payload(item) if item is not None else None

    def list_pattern_features(self) -> Sequence[dict[str, Any]]:
        self._log(logging.WARNING, "compat.list_pattern_features.deprecated", mode="read")
        rows = self._db.scalars(select(PatternFeature).order_by(PatternFeature.feature_slug.asc())).all()
        return [_pattern_feature_payload(pattern_feature_read_model_from_orm(row)) for row in rows]

    def list_discovered_patterns(self, *, timeframe: int | None = None, limit: int = 200) -> Sequence[dict[str, Any]]:
        self._log(
            logging.WARNING,
            "compat.list_discovered_patterns.deprecated",
            mode="read",
            timeframe=timeframe,
            limit=limit,
        )
        stmt = (
            select(DiscoveredPattern)
            .order_by(DiscoveredPattern.confidence.desc(), DiscoveredPattern.sample_size.desc())
            .limit(max(limit, 1))
        )
        if timeframe is not None:
            stmt = stmt.where(DiscoveredPattern.timeframe == timeframe)
        rows = self._db.scalars(stmt).all()
        return [_discovered_pattern_payload(discovered_pattern_read_model_from_orm(row)) for row in rows]

    def list_enriched_signals(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
        limit: int = 100,
    ) -> Sequence[dict[str, Any]]:
        normalized_symbol = symbol.strip().upper() if symbol is not None else None
        self._log(
            logging.WARNING,
            "compat.list_enriched_signals.deprecated",
            mode="read",
            symbol=normalized_symbol,
            timeframe=timeframe,
            limit=limit,
        )
        stmt = _signal_select().order_by(Signal.candle_timestamp.desc(), Signal.created_at.desc()).limit(max(limit, 1))
        if normalized_symbol is not None:
            stmt = stmt.where(Coin.symbol == normalized_symbol)
        if timeframe is not None:
            stmt = stmt.where(Signal.timeframe == timeframe)
        rows = self._db.execute(stmt).all()
        return [_pattern_signal_payload(item) for item in _serialize_signal_rows(self._db, rows)]

    def list_top_signals(self, *, limit: int = 20) -> Sequence[dict[str, Any]]:
        self._log(logging.WARNING, "compat.list_top_signals.deprecated", mode="read", limit=limit)
        rows = self._db.execute(
            _signal_select()
            .order_by(Signal.priority_score.desc(), Signal.candle_timestamp.desc(), Signal.created_at.desc())
            .limit(max(limit, 1))
        ).all()
        return [_pattern_signal_payload(item) for item in _serialize_signal_rows(self._db, rows)]

    def list_coin_patterns(self, symbol: str, *, limit: int = 200) -> Sequence[dict[str, Any]]:
        normalized_symbol = symbol.strip().upper()
        self._log(
            logging.WARNING,
            "compat.list_coin_patterns.deprecated",
            mode="read",
            symbol=normalized_symbol,
            limit=limit,
        )
        rows = self._db.execute(
            _signal_select()
            .where(Coin.symbol == normalized_symbol, Signal.signal_type.like("pattern_%"))
            .order_by(*pattern_signal_ordering())
            .limit(max(limit, 1))
        ).all()
        return [_pattern_signal_payload(item) for item in _serialize_signal_rows(self._db, rows)]

    def get_coin_regimes(self, symbol: str) -> dict[str, Any] | None:
        normalized_symbol = symbol.strip().upper()
        self._log(
            logging.WARNING,
            "compat.get_coin_regimes.deprecated",
            mode="read",
            symbol=normalized_symbol,
        )
        item = _coin_regime_read_model_for_symbol(self._db, normalized_symbol)
        return _coin_regime_payload(item) if item is not None else None

    def list_sectors(self) -> Sequence[dict[str, Any]]:
        self._log(logging.WARNING, "compat.list_sectors.deprecated", mode="read")
        rows = self._db.execute(
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
        ).all()
        return [_sector_payload(sector_read_model_from_mapping(row._mapping)) for row in rows]

    def list_sector_metrics(self, *, timeframe: int | None = None) -> dict[str, Any]:
        self._log(
            logging.WARNING,
            "compat.list_sector_metrics.deprecated",
            mode="read",
            timeframe=timeframe,
            loading_profile="full",
        )
        return _sector_metrics_payload(_sector_metrics_read_model(self._db, timeframe=timeframe))

    def list_market_cycles(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
    ) -> Sequence[dict[str, Any]]:
        normalized_symbol = symbol.strip().upper() if symbol is not None else None
        self._log(
            logging.WARNING,
            "compat.list_market_cycles.deprecated",
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
        rows = self._db.execute(stmt).all()
        return [_market_cycle_payload(market_cycle_read_model_from_mapping(row._mapping)) for row in rows]


class PatternCompatibilityService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _log(self, level: int, event: str, /, **fields: Any) -> None:
        PERSISTENCE_LOGGER.log(
            level,
            event,
            extra={
                "persistence": {
                    "event": event,
                    "component_type": "compatibility_service",
                    "domain": "patterns",
                    "component": "PatternCompatibilityService",
                    **{key: sanitize_log_value(value) for key, value in fields.items()},
                }
            },
        )

    def update_pattern_feature(self, feature_slug: str, *, enabled: bool) -> dict[str, Any] | None:
        normalized_slug = feature_slug.strip()
        self._log(
            logging.WARNING,
            "compat.update_pattern_feature.deprecated",
            mode="write",
            feature_slug=normalized_slug,
            enabled=enabled,
        )
        self._log(
            logging.DEBUG,
            "compat.update_pattern_feature.execute",
            mode="write",
            feature_slug=normalized_slug,
            enabled=enabled,
        )
        row = self._db.get(PatternFeature, normalized_slug)
        if row is None:
            self._log(
                logging.INFO,
                "compat.update_pattern_feature.result",
                mode="write",
                feature_slug=normalized_slug,
                found=False,
            )
            return None
        row.enabled = enabled
        self._db.commit()
        self._db.refresh(row)
        result = _pattern_feature_payload(pattern_feature_read_model_from_orm(row))
        self._log(
            logging.INFO,
            "compat.update_pattern_feature.result",
            mode="write",
            feature_slug=normalized_slug,
            found=True,
            enabled=result["enabled"],
        )
        return result

    def update_pattern(
        self,
        slug: str,
        *,
        enabled: bool | None,
        lifecycle_state: str | None,
        cpu_cost: int | None,
    ) -> dict[str, Any] | None:
        normalized_slug = slug.strip()
        self._log(
            logging.WARNING,
            "compat.update_pattern.deprecated",
            mode="write",
            slug=normalized_slug,
            enabled=enabled,
            lifecycle_state=lifecycle_state,
            cpu_cost=cpu_cost,
        )
        self._log(
            logging.DEBUG,
            "compat.update_pattern.execute",
            mode="write",
            slug=normalized_slug,
            enabled=enabled,
            lifecycle_state=lifecycle_state,
            cpu_cost=cpu_cost,
        )
        row = self._db.get(PatternRegistry, normalized_slug)
        if row is None:
            self._log(
                logging.INFO,
                "compat.update_pattern.result",
                mode="write",
                slug=normalized_slug,
                found=False,
            )
            return None
        if enabled is not None:
            row.enabled = enabled
            if not enabled:
                row.lifecycle_state = PatternLifecycleState.DISABLED.value
        if lifecycle_state is not None:
            normalized_state = lifecycle_state.strip().upper()
            if normalized_state not in {item.value for item in PatternLifecycleState}:
                raise ValueError(f"Unsupported lifecycle state '{lifecycle_state}'.")
            row.lifecycle_state = normalized_state
        if cpu_cost is not None:
            row.cpu_cost = max(cpu_cost, 1)
        self._db.commit()
        self._db.refresh(row)
        item = _get_pattern_read_model(self._db, normalized_slug)
        result = _pattern_payload(item) if item is not None else None
        self._log(
            logging.INFO,
            "compat.update_pattern.result",
            mode="write",
            slug=normalized_slug,
            found=result is not None,
            enabled=result.get("enabled") if isinstance(result, dict) else None,
            lifecycle_state=result.get("lifecycle_state") if isinstance(result, dict) else None,
        )
        return result


def list_patterns(db: Session) -> Sequence[dict[str, Any]]:
    return PatternCompatibilityQuery(db).list_patterns()


def get_pattern(db: Session, slug: str) -> dict[str, Any] | None:
    return PatternCompatibilityQuery(db).get_pattern(slug)


def list_pattern_features(db: Session) -> Sequence[dict[str, Any]]:
    return PatternCompatibilityQuery(db).list_pattern_features()


def update_pattern_feature(db: Session, feature_slug: str, *, enabled: bool) -> dict[str, Any] | None:
    return PatternCompatibilityService(db).update_pattern_feature(feature_slug, enabled=enabled)


def update_pattern(
    db: Session,
    slug: str,
    *,
    enabled: bool | None,
    lifecycle_state: str | None,
    cpu_cost: int | None,
) -> dict[str, Any] | None:
    return PatternCompatibilityService(db).update_pattern(
        slug,
        enabled=enabled,
        lifecycle_state=lifecycle_state,
        cpu_cost=cpu_cost,
    )


def list_discovered_patterns(db: Session, *, timeframe: int | None = None, limit: int = 200) -> Sequence[dict[str, Any]]:
    return PatternCompatibilityQuery(db).list_discovered_patterns(timeframe=timeframe, limit=limit)


def list_enriched_signals(
    db: Session,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    limit: int = 100,
) -> Sequence[dict[str, Any]]:
    return PatternCompatibilityQuery(db).list_enriched_signals(symbol=symbol, timeframe=timeframe, limit=limit)


def list_top_signals(db: Session, *, limit: int = 20) -> Sequence[dict[str, Any]]:
    return PatternCompatibilityQuery(db).list_top_signals(limit=limit)


def list_coin_patterns(db: Session, symbol: str, *, limit: int = 200) -> Sequence[dict[str, Any]]:
    return PatternCompatibilityQuery(db).list_coin_patterns(symbol, limit=limit)


def get_coin_regimes(db: Session, symbol: str) -> dict[str, Any] | None:
    return PatternCompatibilityQuery(db).get_coin_regimes(symbol)


def list_sectors(db: Session) -> Sequence[dict[str, Any]]:
    return PatternCompatibilityQuery(db).list_sectors()


def list_sector_metrics(db: Session, *, timeframe: int | None = None) -> dict[str, Any]:
    return PatternCompatibilityQuery(db).list_sector_metrics(timeframe=timeframe)


def list_market_cycles(
    db: Session,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
) -> Sequence[dict[str, Any]]:
    return PatternCompatibilityQuery(db).list_market_cycles(symbol=symbol, timeframe=timeframe)


__all__ = [
    "PatternCompatibilityQuery",
    "PatternCompatibilityService",
    "_cluster_membership_map",
    "_signal_select",
    "get_coin_regimes",
    "get_pattern",
    "list_coin_patterns",
    "list_discovered_patterns",
    "list_enriched_signals",
    "list_market_cycles",
    "list_pattern_features",
    "list_patterns",
    "list_sector_metrics",
    "list_sectors",
    "list_top_signals",
    "update_pattern",
    "update_pattern_feature",
]
