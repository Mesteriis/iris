from dataclasses import dataclass
from datetime import datetime

from src.apps.cross_market.support import relation_timeframe
from src.apps.market_data.domain import utc_now
from src.apps.predictions.services import PredictionSideEffectDispatcher


@dataclass(slots=True, frozen=True)
class CrossMarketRelationSideEffect:
    leader_coin_id: int
    follower_coin_id: int
    correlation: float
    lag_hours: int
    confidence: float
    updated_at: datetime
    publish_event: bool


@dataclass(slots=True, frozen=True)
class CrossMarketSectorRotationSideEffect:
    timeframe: int
    source_sector: str
    target_sector: str
    source_strength: float
    target_strength: float
    timestamp: datetime


@dataclass(slots=True, frozen=True)
class CrossMarketLeaderSideEffect:
    timeframe: int
    leader_coin_id: int
    leader_symbol: str
    direction: str
    confidence: float
    market_regime: str
    emit_event: bool
    prediction_batch: object


class CrossMarketSideEffectDispatcher:
    async def apply(
        self,
        *,
        relation_effects: tuple[CrossMarketRelationSideEffect, ...],
        sector_effect: CrossMarketSectorRotationSideEffect | None,
        leader_effect: CrossMarketLeaderSideEffect | None,
        timeframe: int,
    ) -> None:
        from src.apps.cross_market import services as services_module

        for effect in relation_effects:
            await services_module.cache_correlation_snapshot_async(
                leader_coin_id=effect.leader_coin_id,
                follower_coin_id=effect.follower_coin_id,
                correlation=effect.correlation,
                lag_hours=effect.lag_hours,
                confidence=effect.confidence,
                updated_at=effect.updated_at,
            )
            if effect.publish_event:
                services_module.publish_event(
                    "correlation_updated",
                    {
                        "coin_id": effect.follower_coin_id,
                        "timeframe": relation_timeframe(timeframe),
                        "timestamp": effect.updated_at,
                        "leader_coin_id": effect.leader_coin_id,
                        "follower_coin_id": effect.follower_coin_id,
                        "correlation": effect.correlation,
                        "lag_hours": effect.lag_hours,
                        "confidence": effect.confidence,
                    },
                )

        if sector_effect is not None:
            services_module.publish_event(
                "sector_rotation_detected",
                {
                    "coin_id": 0,
                    "timeframe": sector_effect.timeframe,
                    "timestamp": sector_effect.timestamp,
                    "source_sector": sector_effect.source_sector,
                    "target_sector": sector_effect.target_sector,
                    "source_strength": sector_effect.source_strength,
                    "target_strength": sector_effect.target_strength,
                },
            )

        if leader_effect is not None:
            await PredictionSideEffectDispatcher().apply_creation(leader_effect.prediction_batch)
            if leader_effect.emit_event:
                services_module.publish_event(
                    "market_leader_detected",
                    {
                        "coin_id": leader_effect.leader_coin_id,
                        "timeframe": leader_effect.timeframe,
                        "timestamp": utc_now(),
                        "leader_coin_id": leader_effect.leader_coin_id,
                        "leader_symbol": leader_effect.leader_symbol,
                        "direction": leader_effect.direction,
                        "confidence": leader_effect.confidence,
                        "market_regime": leader_effect.market_regime,
                    },
                )


__all__ = [
    "CrossMarketLeaderSideEffect",
    "CrossMarketRelationSideEffect",
    "CrossMarketSectorRotationSideEffect",
    "CrossMarketSideEffectDispatcher",
]
