from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.core.db.persistence import freeze_json_value


def _float_or_none(value: object) -> float | None:
    return float(value) if value is not None else None


def _int_or_none(value: object) -> int | None:
    return int(value) if value is not None else None


def _str_or_none(value: object) -> str | None:
    return str(value) if value is not None else None


@dataclass(slots=True, frozen=True)
class CoinMetricsReadModel:
    coin_id: int
    symbol: str
    name: str
    price_current: float | None
    price_change_1h: float | None
    price_change_24h: float | None
    price_change_7d: float | None
    ema_20: float | None
    ema_50: float | None
    sma_50: float | None
    sma_200: float | None
    rsi_14: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    atr_14: float | None
    bb_upper: float | None
    bb_middle: float | None
    bb_lower: float | None
    bb_width: float | None
    adx_14: float | None
    volume_24h: float | None
    volume_change_24h: float | None
    volatility: float | None
    market_cap: float | None
    trend: str | None
    trend_score: int | None
    activity_score: float | None
    activity_bucket: str | None
    analysis_priority: int | None
    last_analysis_at: datetime | None
    market_regime: str | None
    market_regime_details: Any
    indicator_version: int
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class SignalSummaryReadModel:
    coin_id: int
    symbol: str
    name: str
    timeframe: int
    signal_type: str
    confidence: float
    candle_timestamp: datetime
    created_at: datetime


@dataclass(slots=True, frozen=True)
class MarketRadarCoinReadModel:
    coin_id: int
    symbol: str
    name: str
    activity_score: float | None
    activity_bucket: str | None
    analysis_priority: int | None
    price_change_24h: float | None
    price_change_7d: float | None
    volatility: float | None
    market_regime: str | None
    updated_at: datetime | None
    last_analysis_at: datetime | None


@dataclass(slots=True, frozen=True)
class MarketRegimeChangeReadModel:
    coin_id: int
    symbol: str
    name: str
    timeframe: int
    regime: str
    confidence: float
    timestamp: datetime


@dataclass(slots=True, frozen=True)
class MarketRadarReadModel:
    hot_coins: tuple[MarketRadarCoinReadModel, ...]
    emerging_coins: tuple[MarketRadarCoinReadModel, ...]
    regime_changes: tuple[MarketRegimeChangeReadModel, ...]
    volatility_spikes: tuple[MarketRadarCoinReadModel, ...]


@dataclass(slots=True, frozen=True)
class MarketLeaderReadModel:
    leader_coin_id: int
    symbol: str
    name: str
    sector: str | None
    regime: str | None
    confidence: float
    price_change_24h: float | None
    volume_change_24h: float | None
    timestamp: datetime


@dataclass(slots=True, frozen=True)
class CoinRelationReadModel:
    leader_coin_id: int
    leader_symbol: str
    follower_coin_id: int
    follower_symbol: str
    correlation: float
    lag_hours: int
    confidence: float
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class SectorMomentumReadModel:
    sector_id: int
    sector: str
    timeframe: int
    avg_price_change_24h: float
    avg_volume_change_24h: float
    volatility: float
    trend: str | None
    relative_strength: float
    capital_flow: float
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class SectorRotationReadModel:
    source_sector: str
    target_sector: str
    timeframe: int
    timestamp: datetime


@dataclass(slots=True, frozen=True)
class MarketFlowReadModel:
    leaders: tuple[MarketLeaderReadModel, ...]
    relations: tuple[CoinRelationReadModel, ...]
    sectors: tuple[SectorMomentumReadModel, ...]
    rotations: tuple[SectorRotationReadModel, ...]


def coin_metrics_read_model_from_mapping(mapping: Mapping[str, object]) -> CoinMetricsReadModel:
    details = mapping.get("market_regime_details")
    return CoinMetricsReadModel(
        coin_id=int(mapping["coin_id"]),
        symbol=str(mapping["symbol"]),
        name=str(mapping["name"]),
        price_current=_float_or_none(mapping.get("price_current")),
        price_change_1h=_float_or_none(mapping.get("price_change_1h")),
        price_change_24h=_float_or_none(mapping.get("price_change_24h")),
        price_change_7d=_float_or_none(mapping.get("price_change_7d")),
        ema_20=_float_or_none(mapping.get("ema_20")),
        ema_50=_float_or_none(mapping.get("ema_50")),
        sma_50=_float_or_none(mapping.get("sma_50")),
        sma_200=_float_or_none(mapping.get("sma_200")),
        rsi_14=_float_or_none(mapping.get("rsi_14")),
        macd=_float_or_none(mapping.get("macd")),
        macd_signal=_float_or_none(mapping.get("macd_signal")),
        macd_histogram=_float_or_none(mapping.get("macd_histogram")),
        atr_14=_float_or_none(mapping.get("atr_14")),
        bb_upper=_float_or_none(mapping.get("bb_upper")),
        bb_middle=_float_or_none(mapping.get("bb_middle")),
        bb_lower=_float_or_none(mapping.get("bb_lower")),
        bb_width=_float_or_none(mapping.get("bb_width")),
        adx_14=_float_or_none(mapping.get("adx_14")),
        volume_24h=_float_or_none(mapping.get("volume_24h")),
        volume_change_24h=_float_or_none(mapping.get("volume_change_24h")),
        volatility=_float_or_none(mapping.get("volatility")),
        market_cap=_float_or_none(mapping.get("market_cap")),
        trend=_str_or_none(mapping.get("trend")),
        trend_score=_int_or_none(mapping.get("trend_score")),
        activity_score=_float_or_none(mapping.get("activity_score")),
        activity_bucket=_str_or_none(mapping.get("activity_bucket")),
        analysis_priority=_int_or_none(mapping.get("analysis_priority")),
        last_analysis_at=mapping.get("last_analysis_at"),
        market_regime=_str_or_none(mapping.get("market_regime")),
        market_regime_details=freeze_json_value(dict(details)) if isinstance(details, dict) else freeze_json_value(details),
        indicator_version=int(mapping["indicator_version"]),
        updated_at=mapping["updated_at"],
    )


def signal_summary_read_model_from_mapping(mapping: Mapping[str, object]) -> SignalSummaryReadModel:
    return SignalSummaryReadModel(
        coin_id=int(mapping["coin_id"]),
        symbol=str(mapping["symbol"]),
        name=str(mapping["name"]),
        timeframe=int(mapping["timeframe"]),
        signal_type=str(mapping["signal_type"]),
        confidence=float(mapping["confidence"]),
        candle_timestamp=mapping["candle_timestamp"],
        created_at=mapping["created_at"],
    )


def market_radar_coin_read_model_from_mapping(mapping: Mapping[str, object]) -> MarketRadarCoinReadModel:
    return MarketRadarCoinReadModel(
        coin_id=int(mapping["coin_id"]),
        symbol=str(mapping["symbol"]),
        name=str(mapping["name"]),
        activity_score=_float_or_none(mapping.get("activity_score")),
        activity_bucket=_str_or_none(mapping.get("activity_bucket")),
        analysis_priority=_int_or_none(mapping.get("analysis_priority")),
        price_change_24h=_float_or_none(mapping.get("price_change_24h")),
        price_change_7d=_float_or_none(mapping.get("price_change_7d")),
        volatility=_float_or_none(mapping.get("volatility")),
        market_regime=_str_or_none(mapping.get("market_regime")),
        updated_at=mapping.get("updated_at"),
        last_analysis_at=mapping.get("last_analysis_at"),
    )


def coin_relation_read_model_from_mapping(mapping: Mapping[str, object]) -> CoinRelationReadModel:
    return CoinRelationReadModel(
        leader_coin_id=int(mapping["leader_coin_id"]),
        leader_symbol=str(mapping["leader_symbol"]),
        follower_coin_id=int(mapping["follower_coin_id"]),
        follower_symbol=str(mapping["follower_symbol"]),
        correlation=float(mapping["correlation"]),
        lag_hours=int(mapping["lag_hours"]),
        confidence=float(mapping["confidence"]),
        updated_at=mapping["updated_at"],
    )


def sector_momentum_read_model_from_mapping(mapping: Mapping[str, object]) -> SectorMomentumReadModel:
    return SectorMomentumReadModel(
        sector_id=int(mapping["sector_id"]),
        sector=str(mapping["sector"]),
        timeframe=int(mapping["timeframe"]),
        avg_price_change_24h=float(mapping["avg_price_change_24h"]),
        avg_volume_change_24h=float(mapping["avg_volume_change_24h"]),
        volatility=float(mapping["volatility"]),
        trend=_str_or_none(mapping.get("trend")),
        relative_strength=float(mapping["relative_strength"]),
        capital_flow=float(mapping["capital_flow"]),
        updated_at=mapping["updated_at"],
    )


__all__ = [
    "CoinMetricsReadModel",
    "CoinRelationReadModel",
    "MarketFlowReadModel",
    "MarketLeaderReadModel",
    "MarketRadarCoinReadModel",
    "MarketRadarReadModel",
    "MarketRegimeChangeReadModel",
    "SectorMomentumReadModel",
    "SectorRotationReadModel",
    "SignalSummaryReadModel",
    "coin_metrics_read_model_from_mapping",
    "coin_relation_read_model_from_mapping",
    "market_radar_coin_read_model_from_mapping",
    "sector_momentum_read_model_from_mapping",
    "signal_summary_read_model_from_mapping",
]
