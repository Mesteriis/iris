from datetime import datetime, timedelta

from src.apps.cross_market.models import CoinRelation
from src.apps.market_data.domain import ensure_utc, utc_now
from src.apps.predictions.engines import PredictionWindowInput, evaluate_prediction_window
from src.apps.predictions.integrations.market_data import PredictionMarketDataAdapter
from src.apps.predictions.models import MarketPrediction, PredictionResult
from src.apps.predictions.repositories import PredictionRelationRepository, PredictionRepository
from src.apps.predictions.services.results import (
    PredictionCacheSnapshot,
    PredictionCreationBatch,
    PredictionEvaluationBatch,
    PredictionPublishedEvent,
)
from src.apps.predictions.support import PREDICTION_MAX_FOLLOWERS, PredictionOutcome
from src.apps.predictions.support import clamp_prediction_value as _clamp
from src.core.db.persistence import PersistenceComponent, freeze_json_value
from src.core.db.uow import BaseAsyncUnitOfWork


class PredictionService(PersistenceComponent):
    def __init__(
        self,
        uow: BaseAsyncUnitOfWork,
        *,
        predictions: PredictionRepository | None = None,
        relations: PredictionRelationRepository | None = None,
        market_data: PredictionMarketDataAdapter | None = None,
    ) -> None:
        super().__init__(
            uow.session,
            component_type="service",
            domain="predictions",
            component_name="PredictionService",
        )
        self._predictions = predictions or PredictionRepository(uow.session)
        self._relations = relations or PredictionRelationRepository(uow.session)
        self._market_data = market_data or PredictionMarketDataAdapter(uow)

    async def create_market_predictions(
        self,
        *,
        leader_coin_id: int,
        prediction_event: str,
        expected_move: str,
        base_confidence: float,
        emit_events: bool = True,
    ) -> PredictionCreationBatch:
        del emit_events
        self._log_debug(
            "service.create_market_predictions",
            mode="write",
            leader_coin_id=leader_coin_id,
            prediction_event=prediction_event,
            expected_move=expected_move,
        )
        now = utc_now()
        candidates = await self._predictions.list_creation_candidates(
            leader_coin_id=leader_coin_id,
            minimum_confidence=0.5,
            limit=PREDICTION_MAX_FOLLOWERS,
        )
        if not candidates:
            self._log_debug(
                "service.create_market_predictions.result",
                mode="write",
                leader_coin_id=leader_coin_id,
                status="skipped",
                reason="relations_not_found",
            )
            return PredictionCreationBatch(
                status="skipped",
                reason="relations_not_found",
                leader_coin_id=int(leader_coin_id),
            )

        pending_windows = await self._predictions.list_active_pending_evaluation_times(
            leader_coin_id=leader_coin_id,
            target_coin_ids=[candidate.target_coin_id for candidate in candidates],
            prediction_event=prediction_event,
            expected_move=expected_move,
        )

        created = 0
        cache_snapshots: list[PredictionCacheSnapshot] = []
        for candidate in candidates:
            existing_evaluation = pending_windows.get(candidate.target_coin_id)
            if existing_evaluation is not None and ensure_utc(existing_evaluation) >= now:
                continue
            confidence = _clamp(base_confidence * max(candidate.relation_confidence, 0.55), 0.35, 0.98)
            prediction = await self._predictions.add(
                MarketPrediction(
                    prediction_type="cross_market_follow_through",
                    leader_coin_id=leader_coin_id,
                    target_coin_id=candidate.target_coin_id,
                    prediction_event=prediction_event,
                    expected_move=expected_move,
                    lag_hours=candidate.lag_hours,
                    confidence=confidence,
                    evaluation_time=now + timedelta(hours=candidate.lag_hours),
                    status="pending",
                )
            )
            cache_snapshots.append(PredictionCacheSnapshot.from_prediction(prediction))
            created += 1

        result = PredictionCreationBatch(
            status="ok",
            created=created,
            leader_coin_id=int(leader_coin_id),
            cache_snapshots=tuple(cache_snapshots),
        )
        self._log_info(
            "service.create_market_predictions.result",
            mode="write",
            leader_coin_id=leader_coin_id,
            created=created,
        )
        return result

    async def evaluate_pending_predictions(
        self,
        *,
        limit: int = 200,
        emit_events: bool = True,
    ) -> PredictionEvaluationBatch:
        self._log_debug("service.evaluate_pending_predictions", mode="write", limit=limit, emit_events=emit_events)
        now = utc_now()
        rows = await self._predictions.list_pending_for_update(limit=limit)
        confirmed = 0
        failed = 0
        expired = 0
        cache_snapshots: list[PredictionCacheSnapshot] = []
        published_events: list[PredictionPublishedEvent] = []
        for prediction in rows:
            outcome = await self._evaluate_prediction_window(prediction, now=now)
            if outcome is None:
                continue
            prediction.status = outcome.status
            prediction_result = prediction.result
            if prediction_result is None:
                prediction.result = PredictionResult(
                    prediction_id=int(prediction.id),
                    actual_move=outcome.actual_move,
                    success=outcome.success,
                    profit=outcome.profit,
                    evaluated_at=now,
                )
            else:
                prediction_result.actual_move = outcome.actual_move
                prediction_result.success = outcome.success
                prediction_result.profit = outcome.profit
                prediction_result.evaluated_at = now
            relation = await self._apply_relation_feedback(prediction, success=outcome.success)
            cache_snapshots.append(PredictionCacheSnapshot.from_prediction(prediction))
            if outcome.status == "confirmed":
                confirmed += 1
            elif outcome.status == "expired":
                expired += 1
            else:
                failed += 1
            if emit_events:
                event_type = "prediction_confirmed" if outcome.status == "confirmed" else "prediction_failed"
                published_events.append(
                    PredictionPublishedEvent(
                        event_type=event_type,
                        payload=freeze_json_value(
                            {
                                "coin_id": int(prediction.target_coin_id),
                                "timeframe": 15,
                                "timestamp": now,
                                "prediction_id": int(prediction.id),
                                "leader_coin_id": int(prediction.leader_coin_id),
                                "target_coin_id": int(prediction.target_coin_id),
                                "prediction_event": prediction.prediction_event,
                                "expected_move": prediction.expected_move,
                                "actual_move": outcome.actual_move,
                                "profit": outcome.profit,
                                "status": outcome.status,
                                "relation_confidence": float(relation.confidence) if relation is not None else None,
                            }
                        ),
                    )
                )

        batch = PredictionEvaluationBatch(
            status="ok",
            evaluated=len(rows),
            confirmed=confirmed,
            failed=failed,
            expired=expired,
            cache_snapshots=tuple(cache_snapshots),
            events=tuple(published_events),
        )
        self._log_info(
            "service.evaluate_pending_predictions.result",
            mode="write",
            evaluated=len(rows),
            confirmed=confirmed,
            failed=failed,
            expired=expired,
        )
        return batch

    async def _evaluate_prediction_window(
        self,
        prediction: MarketPrediction,
        *,
        now: datetime,
    ) -> PredictionOutcome | None:
        start = ensure_utc(prediction.created_at)
        deadline = ensure_utc(prediction.evaluation_time)
        candles = await self._market_data.fetch_prediction_window(
            coin_id=int(prediction.target_coin_id),
            window_start=start,
            window_end=min(now, deadline),
        )
        return evaluate_prediction_window(
            PredictionWindowInput(
                expected_move=prediction.expected_move,
                deadline=deadline,
                now=now,
                candles=candles,
            )
        )

    async def _apply_relation_feedback(
        self,
        prediction: MarketPrediction,
        *,
        success: bool,
    ) -> CoinRelation | None:
        relation = await self._relations.get_for_update(
            leader_coin_id=int(prediction.leader_coin_id),
            target_coin_id=int(prediction.target_coin_id),
        )
        if relation is None:
            self._log_warning(
                "service.apply_prediction_relation_feedback.missing_relation",
                mode="write",
                leader_coin_id=int(prediction.leader_coin_id),
                target_coin_id=int(prediction.target_coin_id),
            )
            return None
        delta = 0.04 if success else -0.05
        relation.confidence = _clamp(float(relation.confidence) + delta, 0.05, 0.99)
        relation.updated_at = utc_now()
        return relation


__all__ = ["PredictionService"]
