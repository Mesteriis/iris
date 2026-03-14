from __future__ import annotations

from src.apps.cross_market.integrations.market_data import CrossMarketMarketDataAdapter
from src.apps.cross_market.query_services import CrossMarketQueryService
from src.apps.cross_market.repositories import CoinRelationRepository, SectorMetricRepository
from src.apps.cross_market.services.leader_flow import detect_market_leader
from src.apps.cross_market.services.relation_flow import update_coin_relations
from src.apps.cross_market.services.results import (
    CrossMarketLeaderDetectionResult,
    CrossMarketProcessResult,
    CrossMarketRelationUpdateResult,
    CrossMarketSectorMomentumResult,
)
from src.apps.cross_market.services.sector_flow import refresh_sector_momentum
from src.apps.cross_market.services.side_effects import CrossMarketSideEffectDispatcher
from src.apps.predictions.services import PredictionService
from src.core.db.persistence import PersistenceComponent
from src.core.db.uow import BaseAsyncUnitOfWork


class CrossMarketService(PersistenceComponent):
    def __init__(
        self,
        uow: BaseAsyncUnitOfWork,
        *,
        queries: CrossMarketQueryService | None = None,
        relation_repo: CoinRelationRepository | None = None,
        sector_repo: SectorMetricRepository | None = None,
        candle_repo: CrossMarketMarketDataAdapter | None = None,
    ) -> None:
        super().__init__(
            uow.session,
            component_type="service",
            domain="cross_market",
            component_name="CrossMarketService",
        )
        self._uow = uow
        self._queries = queries or CrossMarketQueryService(uow.session)
        self._relations = relation_repo or CoinRelationRepository(uow.session)
        self._sectors = sector_repo or SectorMetricRepository(uow.session)
        self._candles = candle_repo or CrossMarketMarketDataAdapter(uow)

    def _prediction_service(self) -> PredictionService:
        return PredictionService(self._uow)

    def _queue_after_commit_side_effects(
        self,
        *,
        relation_effects,
        sector_effect,
        leader_effect,
        timeframe: int,
    ) -> None:
        async def _dispatch() -> None:
            await CrossMarketSideEffectDispatcher().apply(
                relation_effects=tuple(relation_effects),
                sector_effect=sector_effect,
                leader_effect=leader_effect,
                timeframe=timeframe,
            )

        self._uow.add_after_commit_action(_dispatch)

    async def process_event(
        self,
        *,
        coin_id: int,
        timeframe: int,
        event_type: str,
        payload: dict[str, object],
        emit_events: bool = True,
    ) -> CrossMarketProcessResult:
        self._log_debug(
            "service.process_cross_market_event",
            mode="write",
            coin_id=coin_id,
            timeframe=timeframe,
            event_type=event_type,
            emit_events=emit_events,
        )
        try:
            relation_result, relation_effects = await self._update_coin_relations(
                follower_coin_id=coin_id,
                timeframe=timeframe,
                emit_events=emit_events and event_type == "candle_closed",
            )
            sector_result, sector_effect = await self._refresh_sector_momentum(
                timeframe=timeframe,
                emit_events=emit_events and event_type == "indicator_updated",
            )
            if event_type == "indicator_updated":
                leader_result, leader_effect, leader_requires_commit = await self._detect_market_leader(
                    coin_id=coin_id,
                    timeframe=timeframe,
                    payload=payload,
                    emit_events=emit_events,
                )
            else:
                leader_result = CrossMarketLeaderDetectionResult(
                    status="skipped",
                    reason="leader_detection_not_requested",
                )
                leader_effect = None
                leader_requires_commit = False

            requires_commit = bool(relation_effects) or sector_result.status == "ok" or leader_requires_commit
            if requires_commit:
                self._queue_after_commit_side_effects(
                    relation_effects=relation_effects,
                    sector_effect=sector_effect,
                    leader_effect=leader_effect,
                    timeframe=timeframe,
                )

            result = CrossMarketProcessResult(
                status="ok",
                relations=relation_result,
                sectors=sector_result,
                leader=_coerce_leader_result(leader_result),
            )
            self._log_debug(
                "service.process_cross_market_event.result",
                mode="write",
                coin_id=coin_id,
                timeframe=timeframe,
                relation_status=result.relations.status,
                sector_status=result.sectors.status,
                leader_status=result.leader.status,
                requires_commit=requires_commit,
            )
            return result
        except Exception:
            self._log_exception(
                "service.process_cross_market_event.error",
                mode="write",
                coin_id=coin_id,
                timeframe=timeframe,
                event_type=event_type,
            )
            raise

    async def _update_coin_relations(
        self,
        *,
        follower_coin_id: int,
        timeframe: int,
        emit_events: bool,
    ) -> tuple[CrossMarketRelationUpdateResult, tuple]:
        return await update_coin_relations(
            service=self,
            follower_coin_id=follower_coin_id,
            timeframe=timeframe,
            emit_events=emit_events,
        )

    async def _refresh_sector_momentum(
        self,
        *,
        timeframe: int,
        emit_events: bool,
    ) -> tuple[CrossMarketSectorMomentumResult, object | None]:
        return await refresh_sector_momentum(
            service=self,
            timeframe=timeframe,
            emit_events=emit_events,
        )

    async def _detect_market_leader(
        self,
        *,
        coin_id: int,
        timeframe: int,
        payload: dict[str, object],
        emit_events: bool,
    ) -> tuple[CrossMarketLeaderDetectionResult | dict[str, object], object | None, bool]:
        return await detect_market_leader(
            service=self,
            coin_id=coin_id,
            timeframe=timeframe,
            payload=payload,
            emit_events=emit_events,
        )


def _coerce_leader_result(
    value: CrossMarketLeaderDetectionResult | dict[str, object],
) -> CrossMarketLeaderDetectionResult:
    if isinstance(value, CrossMarketLeaderDetectionResult):
        return value
    return CrossMarketLeaderDetectionResult(
        status=str(value.get("status") or "unknown"),
        coin_id=int(value["coin_id"]) if value.get("coin_id") is not None else None,
        leader_coin_id=int(value["leader_coin_id"]) if value.get("leader_coin_id") is not None else None,
        direction=str(value["direction"]) if value.get("direction") is not None else None,
        confidence=float(value["confidence"]) if value.get("confidence") is not None else None,
        reason=str(value["reason"]) if value.get("reason") is not None else None,
    )


__all__ = ["CrossMarketService"]
