from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.apps.anomalies.constants import ANOMALY_SCOPE_ASSET
from app.apps.market_data.repos import CandlePoint


@dataclass(slots=True, frozen=True)
class BenchmarkSeries:
    symbol: str
    candles: list[CandlePoint]


@dataclass(slots=True, frozen=True)
class MarketStructurePoint:
    venue: str
    timestamp: datetime
    last_price: float | None = None
    mark_price: float | None = None
    index_price: float | None = None
    funding_rate: float | None = None
    open_interest: float | None = None
    basis: float | None = None
    liquidations_long: float | None = None
    liquidations_short: float | None = None
    volume: float | None = None
    payload_json: dict[str, Any] = field(default_factory=dict)

    @property
    def reference_price(self) -> float | None:
        return self.last_price if self.last_price is not None else self.mark_price

    @property
    def basis_value(self) -> float | None:
        if self.basis is not None:
            return self.basis
        if self.mark_price is not None and self.index_price not in (None, 0.0):
            return (self.mark_price - self.index_price) / self.index_price
        return None

    @property
    def total_liquidations(self) -> float:
        return float((self.liquidations_long or 0.0) + (self.liquidations_short or 0.0))


@dataclass(slots=True)
class AnomalyDetectionContext:
    coin_id: int
    symbol: str
    timeframe: int
    timestamp: datetime
    candles: list[CandlePoint]
    market_regime: str | None = None
    sector: str | None = None
    portfolio_relevant: bool = False
    benchmark: BenchmarkSeries | None = None
    sector_peer_candles: dict[str, list[CandlePoint]] = field(default_factory=dict)
    related_peer_candles: dict[str, list[CandlePoint]] = field(default_factory=dict)
    venue_snapshots: dict[str, list[MarketStructurePoint]] = field(default_factory=dict)

    @property
    def latest_candle(self) -> CandlePoint | None:
        return self.candles[-1] if self.candles else None

    @property
    def previous_candle(self) -> CandlePoint | None:
        return self.candles[-2] if len(self.candles) >= 2 else None

    @property
    def window_start(self) -> datetime | None:
        return self.candles[0].timestamp if self.candles else None

    @property
    def window_end(self) -> datetime:
        return self.timestamp


@dataclass(slots=True)
class DetectorFinding:
    anomaly_type: str
    summary: str
    component_scores: dict[str, float]
    metrics: dict[str, float]
    confidence: float
    explainability: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation_hits: int = 1
    confirmation_target: int = 1
    scope: str = ANOMALY_SCOPE_ASSET
    isolated: bool = True
    related_to: str | None = None
    affected_symbols: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AnomalyDraft:
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
    payload_json: dict[str, Any]
    cooldown_until: datetime | None = None

    def to_event_payload(self, anomaly_id: int) -> dict[str, Any]:
        payload = dict(self.payload_json)
        payload.update(
            {
                "anomaly_id": int(anomaly_id),
                "coin_id": int(self.coin_id),
                "symbol": self.symbol,
                "timeframe": int(self.timeframe),
                "timestamp": self.window_end,
                "type": self.anomaly_type,
                "severity": self.severity,
                "confidence": float(self.confidence),
                "score": float(self.score),
                "status": self.status,
                "summary": self.summary,
                "detected_at_unix": int(self.detected_at.timestamp()),
            }
        )
        return payload
