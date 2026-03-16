from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from src.core.db.persistence import freeze_json_value


@runtime_checkable
class _SupportsInt(Protocol):
    def __int__(self) -> int: ...


@runtime_checkable
class _SupportsFloat(Protocol):
    def __float__(self) -> float: ...


def _float_or_none(value: object) -> float | None:
    return _required_float(value, field_name="value") if value is not None else None


def _int_or_none(value: object) -> int | None:
    return _required_int(value, field_name="value") if value is not None else None


def _str_or_none(value: object) -> str | None:
    return str(value) if value is not None else None


def _required_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool | int | str | bytes | bytearray):
        return int(value)
    if isinstance(value, _SupportsInt):
        return int(value)
    raise TypeError(f"{field_name} must be int-compatible, got {type(value).__name__}")


def _required_float(value: object, *, field_name: str) -> float:
    if isinstance(value, bool | int | float | str | bytes | bytearray):
        return float(value)
    if isinstance(value, _SupportsFloat):
        return float(value)
    if isinstance(value, _SupportsInt):
        return float(int(value))
    raise TypeError(f"{field_name} must be float-compatible, got {type(value).__name__}")


def _datetime_or_none(value: object, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _required_datetime(value, field_name=field_name)


def _required_datetime(value: object, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    raise TypeError(f"{field_name} must be datetime, got {type(value).__name__}")


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
        coin_id=_required_int(mapping["coin_id"], field_name="coin_id"),
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
        last_analysis_at=_datetime_or_none(mapping.get("last_analysis_at"), field_name="last_analysis_at"),
        market_regime=_str_or_none(mapping.get("market_regime")),
        market_regime_details=freeze_json_value({str(key): value for key, value in details.items()})
        if isinstance(details, Mapping)
        else freeze_json_value(details),
        indicator_version=_required_int(mapping["indicator_version"], field_name="indicator_version"),
        updated_at=_required_datetime(mapping["updated_at"], field_name="updated_at"),
    )


def signal_summary_read_model_from_mapping(mapping: Mapping[str, object]) -> SignalSummaryReadModel:
    return SignalSummaryReadModel(
        coin_id=_required_int(mapping["coin_id"], field_name="coin_id"),
        symbol=str(mapping["symbol"]),
        name=str(mapping["name"]),
        timeframe=_required_int(mapping["timeframe"], field_name="timeframe"),
        signal_type=str(mapping["signal_type"]),
        confidence=_required_float(mapping["confidence"], field_name="confidence"),
        candle_timestamp=_required_datetime(mapping["candle_timestamp"], field_name="candle_timestamp"),
        created_at=_required_datetime(mapping["created_at"], field_name="created_at"),
    )


def market_radar_coin_read_model_from_mapping(mapping: Mapping[str, object]) -> MarketRadarCoinReadModel:
    return MarketRadarCoinReadModel(
        coin_id=_required_int(mapping["coin_id"], field_name="coin_id"),
        symbol=str(mapping["symbol"]),
        name=str(mapping["name"]),
        activity_score=_float_or_none(mapping.get("activity_score")),
        activity_bucket=_str_or_none(mapping.get("activity_bucket")),
        analysis_priority=_int_or_none(mapping.get("analysis_priority")),
        price_change_24h=_float_or_none(mapping.get("price_change_24h")),
        price_change_7d=_float_or_none(mapping.get("price_change_7d")),
        volatility=_float_or_none(mapping.get("volatility")),
        market_regime=_str_or_none(mapping.get("market_regime")),
        updated_at=_datetime_or_none(mapping.get("updated_at"), field_name="updated_at"),
        last_analysis_at=_datetime_or_none(mapping.get("last_analysis_at"), field_name="last_analysis_at"),
    )


def coin_relation_read_model_from_mapping(mapping: Mapping[str, object]) -> CoinRelationReadModel:
    return CoinRelationReadModel(
        leader_coin_id=_required_int(mapping["leader_coin_id"], field_name="leader_coin_id"),
        leader_symbol=str(mapping["leader_symbol"]),
        follower_coin_id=_required_int(mapping["follower_coin_id"], field_name="follower_coin_id"),
        follower_symbol=str(mapping["follower_symbol"]),
        correlation=_required_float(mapping["correlation"], field_name="correlation"),
        lag_hours=_required_int(mapping["lag_hours"], field_name="lag_hours"),
        confidence=_required_float(mapping["confidence"], field_name="confidence"),
        updated_at=_required_datetime(mapping["updated_at"], field_name="updated_at"),
    )


def sector_momentum_read_model_from_mapping(mapping: Mapping[str, object]) -> SectorMomentumReadModel:
    return SectorMomentumReadModel(
        sector_id=_required_int(mapping["sector_id"], field_name="sector_id"),
        sector=str(mapping["sector"]),
        timeframe=_required_int(mapping["timeframe"], field_name="timeframe"),
        avg_price_change_24h=_required_float(mapping["avg_price_change_24h"], field_name="avg_price_change_24h"),
        avg_volume_change_24h=_required_float(mapping["avg_volume_change_24h"], field_name="avg_volume_change_24h"),
        volatility=_required_float(mapping["volatility"], field_name="volatility"),
        trend=_str_or_none(mapping.get("trend")),
        relative_strength=_required_float(mapping["relative_strength"], field_name="relative_strength"),
        capital_flow=_required_float(mapping["capital_flow"], field_name="capital_flow"),
        updated_at=_required_datetime(mapping["updated_at"], field_name="updated_at"),
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
