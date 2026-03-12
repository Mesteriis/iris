from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


def _float_or_none(value: object) -> float | None:
    return float(value) if value is not None else None


def _str_or_none(value: object) -> str | None:
    return str(value) if value is not None else None


@dataclass(slots=True, frozen=True)
class PatternStatisticReadModel:
    timeframe: int
    market_regime: str
    sample_size: int
    total_signals: int
    successful_signals: int
    success_rate: float
    avg_return: float
    avg_drawdown: float
    temperature: float
    enabled: bool
    last_evaluated_at: datetime | None
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class PatternReadModel:
    slug: str
    category: str
    enabled: bool
    cpu_cost: int
    lifecycle_state: str
    created_at: datetime
    statistics: tuple[PatternStatisticReadModel, ...]


@dataclass(slots=True, frozen=True)
class PatternFeatureReadModel:
    feature_slug: str
    enabled: bool
    created_at: datetime


@dataclass(slots=True, frozen=True)
class DiscoveredPatternReadModel:
    structure_hash: str
    timeframe: int
    sample_size: int
    avg_return: float
    avg_drawdown: float
    confidence: float


@dataclass(slots=True, frozen=True)
class RegimeTimeframeReadModel:
    timeframe: int
    regime: str
    confidence: float


@dataclass(slots=True, frozen=True)
class CoinRegimeReadModel:
    coin_id: int
    symbol: str
    canonical_regime: str | None
    items: tuple[RegimeTimeframeReadModel, ...]


@dataclass(slots=True, frozen=True)
class SectorReadModel:
    id: int
    name: str
    description: str | None
    created_at: datetime
    coin_count: int


@dataclass(slots=True, frozen=True)
class SectorMetricReadModel:
    sector_id: int
    name: str
    description: str | None
    timeframe: int
    sector_strength: float
    relative_strength: float
    capital_flow: float
    avg_price_change_24h: float
    avg_volume_change_24h: float
    volatility: float
    trend: str | None
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class SectorNarrativeReadModel:
    timeframe: int
    top_sector: str | None
    rotation_state: str | None
    btc_dominance: float | None
    capital_wave: str | None


@dataclass(slots=True, frozen=True)
class SectorMetricsReadModel:
    items: tuple[SectorMetricReadModel, ...]
    narratives: tuple[SectorNarrativeReadModel, ...]


@dataclass(slots=True, frozen=True)
class MarketCycleReadModel:
    coin_id: int
    symbol: str
    name: str
    timeframe: int
    cycle_phase: str
    confidence: float
    detected_at: datetime


@dataclass(slots=True, frozen=True)
class PatternSignalReadModel:
    id: int
    coin_id: int
    symbol: str
    name: str
    sector: str | None
    timeframe: int
    signal_type: str
    confidence: float
    priority_score: float
    context_score: float
    regime_alignment: float
    candle_timestamp: datetime
    created_at: datetime
    market_regime: str | None
    cycle_phase: str | None
    cycle_confidence: float | None
    cluster_membership: tuple[str, ...]


def pattern_statistic_read_model_from_orm(stat) -> PatternStatisticReadModel:
    return PatternStatisticReadModel(
        timeframe=int(stat.timeframe),
        market_regime=str(stat.market_regime),
        sample_size=int(stat.sample_size),
        total_signals=int(stat.total_signals),
        successful_signals=int(stat.successful_signals),
        success_rate=float(stat.success_rate),
        avg_return=float(stat.avg_return),
        avg_drawdown=float(stat.avg_drawdown),
        temperature=float(stat.temperature),
        enabled=bool(stat.enabled),
        last_evaluated_at=stat.last_evaluated_at,
        updated_at=stat.updated_at,
    )


def pattern_read_model_from_orm(pattern, statistics: tuple[PatternStatisticReadModel, ...]) -> PatternReadModel:
    return PatternReadModel(
        slug=str(pattern.slug),
        category=str(pattern.category),
        enabled=bool(pattern.enabled),
        cpu_cost=int(pattern.cpu_cost),
        lifecycle_state=str(pattern.lifecycle_state),
        created_at=pattern.created_at,
        statistics=statistics,
    )


def pattern_feature_read_model_from_orm(feature) -> PatternFeatureReadModel:
    return PatternFeatureReadModel(
        feature_slug=str(feature.feature_slug),
        enabled=bool(feature.enabled),
        created_at=feature.created_at,
    )


def discovered_pattern_read_model_from_orm(pattern) -> DiscoveredPatternReadModel:
    return DiscoveredPatternReadModel(
        structure_hash=str(pattern.structure_hash),
        timeframe=int(pattern.timeframe),
        sample_size=int(pattern.sample_size),
        avg_return=float(pattern.avg_return),
        avg_drawdown=float(pattern.avg_drawdown),
        confidence=float(pattern.confidence),
    )


def regime_timeframe_read_model(
    *,
    timeframe: int,
    regime: str,
    confidence: float,
) -> RegimeTimeframeReadModel:
    return RegimeTimeframeReadModel(
        timeframe=int(timeframe),
        regime=str(regime),
        confidence=float(confidence),
    )


def sector_read_model_from_mapping(mapping: Mapping[str, object]) -> SectorReadModel:
    return SectorReadModel(
        id=int(mapping["id"]),
        name=str(mapping["name"]),
        description=_str_or_none(mapping.get("description")),
        created_at=mapping["created_at"],
        coin_count=int(mapping["coin_count"]),
    )


def sector_metric_read_model_from_mapping(mapping: Mapping[str, object]) -> SectorMetricReadModel:
    return SectorMetricReadModel(
        sector_id=int(mapping["sector_id"]),
        name=str(mapping["name"]),
        description=_str_or_none(mapping.get("description")),
        timeframe=int(mapping["timeframe"]),
        sector_strength=float(mapping["sector_strength"]),
        relative_strength=float(mapping["relative_strength"]),
        capital_flow=float(mapping["capital_flow"]),
        avg_price_change_24h=float(mapping["avg_price_change_24h"]),
        avg_volume_change_24h=float(mapping["avg_volume_change_24h"]),
        volatility=float(mapping["volatility"]),
        trend=_str_or_none(mapping.get("trend")),
        updated_at=mapping["updated_at"],
    )


def sector_narrative_read_model(
    *,
    timeframe: int,
    top_sector: str | None,
    rotation_state: str | None,
    btc_dominance: float | None,
    capital_wave: str | None,
) -> SectorNarrativeReadModel:
    return SectorNarrativeReadModel(
        timeframe=int(timeframe),
        top_sector=_str_or_none(top_sector),
        rotation_state=_str_or_none(rotation_state),
        btc_dominance=_float_or_none(btc_dominance),
        capital_wave=_str_or_none(capital_wave),
    )


def market_cycle_read_model_from_mapping(mapping: Mapping[str, object]) -> MarketCycleReadModel:
    return MarketCycleReadModel(
        coin_id=int(mapping["coin_id"]),
        symbol=str(mapping["symbol"]),
        name=str(mapping["name"]),
        timeframe=int(mapping["timeframe"]),
        cycle_phase=str(mapping["cycle_phase"]),
        confidence=float(mapping["confidence"]),
        detected_at=mapping["detected_at"],
    )


def pattern_signal_read_model_from_mapping(
    mapping: Mapping[str, object],
    *,
    cluster_membership: tuple[str, ...],
    market_regime: str | None,
) -> PatternSignalReadModel:
    return PatternSignalReadModel(
        id=int(mapping["id"]),
        coin_id=int(mapping["coin_id"]),
        symbol=str(mapping["symbol"]),
        name=str(mapping["name"]),
        sector=_str_or_none(mapping.get("sector")),
        timeframe=int(mapping["timeframe"]),
        signal_type=str(mapping["signal_type"]),
        confidence=float(mapping["confidence"]),
        priority_score=float(mapping.get("priority_score") or 0.0),
        context_score=float(mapping.get("context_score") or 0.0),
        regime_alignment=float(mapping.get("regime_alignment") or 0.0),
        candle_timestamp=mapping["candle_timestamp"],
        created_at=mapping["created_at"],
        market_regime=_str_or_none(market_regime),
        cycle_phase=_str_or_none(mapping.get("cycle_phase")),
        cycle_confidence=_float_or_none(mapping.get("cycle_confidence")),
        cluster_membership=cluster_membership,
    )


def coin_regime_read_model(
    *,
    coin_id: int,
    symbol: str,
    canonical_regime: str | None,
    items: tuple[RegimeTimeframeReadModel, ...],
) -> CoinRegimeReadModel:
    return CoinRegimeReadModel(
        coin_id=int(coin_id),
        symbol=str(symbol),
        canonical_regime=_str_or_none(canonical_regime),
        items=items,
    )


__all__ = [
    "CoinRegimeReadModel",
    "DiscoveredPatternReadModel",
    "MarketCycleReadModel",
    "PatternFeatureReadModel",
    "PatternReadModel",
    "PatternSignalReadModel",
    "PatternStatisticReadModel",
    "RegimeTimeframeReadModel",
    "SectorMetricReadModel",
    "SectorMetricsReadModel",
    "SectorNarrativeReadModel",
    "SectorReadModel",
    "coin_regime_read_model",
    "discovered_pattern_read_model_from_orm",
    "market_cycle_read_model_from_mapping",
    "pattern_feature_read_model_from_orm",
    "pattern_read_model_from_orm",
    "pattern_signal_read_model_from_mapping",
    "pattern_statistic_read_model_from_orm",
    "regime_timeframe_read_model",
    "sector_metric_read_model_from_mapping",
    "sector_narrative_read_model",
    "sector_read_model_from_mapping",
]
