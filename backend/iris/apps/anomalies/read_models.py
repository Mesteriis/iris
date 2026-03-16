from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from iris.apps.anomalies.models import MarketAnomaly
from iris.core.db.persistence import freeze_json_value, thaw_json_value


@runtime_checkable
class _SupportsInt(Protocol):
    def __int__(self) -> int: ...


@runtime_checkable
class _SupportsFloat(Protocol):
    def __float__(self) -> float: ...


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


@dataclass(slots=True, frozen=True)
class AnomalyReadModel:
    id: int
    coin_id: int
    symbol: str
    timeframe: int
    anomaly_type: str
    severity: str
    confidence: float
    score: float
    status: str
    detected_at: datetime
    window_start: datetime | None
    window_end: datetime
    market_regime: str | None
    sector: str | None
    summary: str
    payload_json: Any
    cooldown_until: datetime | None
    last_confirmed_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


def anomaly_read_model_from_orm(anomaly: MarketAnomaly) -> AnomalyReadModel:
    return AnomalyReadModel(
        id=_required_int(anomaly.id, field_name="id"),
        coin_id=_required_int(anomaly.coin_id, field_name="coin_id"),
        symbol=str(anomaly.symbol),
        timeframe=_required_int(anomaly.timeframe, field_name="timeframe"),
        anomaly_type=str(anomaly.anomaly_type),
        severity=str(anomaly.severity),
        confidence=_required_float(anomaly.confidence, field_name="confidence"),
        score=_required_float(anomaly.score, field_name="score"),
        status=str(anomaly.status),
        detected_at=anomaly.detected_at,
        window_start=anomaly.window_start,
        window_end=anomaly.window_end,
        market_regime=str(anomaly.market_regime) if anomaly.market_regime is not None else None,
        sector=str(anomaly.sector) if anomaly.sector is not None else None,
        summary=str(anomaly.summary),
        payload_json=freeze_json_value(dict(anomaly.payload_json or {})),
        cooldown_until=anomaly.cooldown_until,
        last_confirmed_at=anomaly.last_confirmed_at,
        resolved_at=anomaly.resolved_at,
        created_at=anomaly.created_at,
        updated_at=anomaly.updated_at,
    )


def anomaly_read_model_to_legacy_dict(item: AnomalyReadModel) -> dict[str, object]:
    return {
        "id": int(item.id),
        "coin_id": int(item.coin_id),
        "symbol": item.symbol,
        "timeframe": int(item.timeframe),
        "anomaly_type": item.anomaly_type,
        "severity": item.severity,
        "confidence": float(item.confidence),
        "score": float(item.score),
        "status": item.status,
        "detected_at": item.detected_at,
        "window_start": item.window_start,
        "window_end": item.window_end,
        "market_regime": item.market_regime,
        "sector": item.sector,
        "summary": item.summary,
        "payload_json": thaw_json_value(item.payload_json),
        "cooldown_until": item.cooldown_until,
        "last_confirmed_at": item.last_confirmed_at,
        "resolved_at": item.resolved_at,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


__all__ = [
    "AnomalyReadModel",
    "anomaly_read_model_from_orm",
    "anomaly_read_model_to_legacy_dict",
]
