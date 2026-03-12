from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.cross_market.models import CoinRelation
from src.apps.market_data.domain import ensure_utc, utc_now
from src.apps.market_data.repositories import CandleRepository
from src.apps.predictions.cache import (
    PredictionCacheEntry,
    cache_prediction_snapshot,
    cache_prediction_snapshot_async,
    read_cached_prediction,
    read_cached_prediction_async,
)
from src.apps.predictions.engine import (
    PREDICTION_MAX_FOLLOWERS,
    PredictionOutcome,
    _clamp,
    create_market_predictions,
    evaluate_pending_predictions,
)
from src.apps.predictions.models import MarketPrediction, PredictionResult
from src.apps.predictions.query_services import PredictionQueryService
from src.apps.predictions.repositories import PredictionRelationRepository, PredictionRepository
from src.core.db.persistence import PersistenceComponent, freeze_json_value
from src.core.db.uow import BaseAsyncUnitOfWork, SessionUnitOfWork
from src.runtime.streams.publisher import publish_event

_PREDICTION_MOVE_THRESHOLD = 0.015


@dataclass(slots=True, frozen=True)
class PredictionCacheSnapshot:
    prediction_id: int
    prediction_type: str
    leader_coin_id: int
    target_coin_id: int
    prediction_event: str
    expected_move: str
    lag_hours: int
    confidence: float
    created_at: datetime | None
    evaluation_time: datetime | None
    status: str

    @classmethod
    def from_prediction(cls, prediction: MarketPrediction) -> PredictionCacheSnapshot:
        return cls(
            prediction_id=int(prediction.id),
            prediction_type=prediction.prediction_type,
            leader_coin_id=int(prediction.leader_coin_id),
            target_coin_id=int(prediction.target_coin_id),
            prediction_event=prediction.prediction_event,
            expected_move=prediction.expected_move,
            lag_hours=int(prediction.lag_hours),
            confidence=float(prediction.confidence),
            created_at=prediction.created_at,
            evaluation_time=prediction.evaluation_time,
            status=prediction.status,
        )

    @classmethod
    def from_cache_entry(cls, entry: PredictionCacheEntry) -> PredictionCacheSnapshot:
        return cls(
            prediction_id=int(entry.id),
            prediction_type=entry.prediction_type,
            leader_coin_id=int(entry.leader_coin_id),
            target_coin_id=int(entry.target_coin_id),
            prediction_event=entry.prediction_event,
            expected_move=entry.expected_move,
            lag_hours=int(entry.lag_hours),
            confidence=float(entry.confidence),
            created_at=entry.created_at,
            evaluation_time=entry.evaluation_time,
            status=entry.status,
        )

    def as_cache_kwargs(self) -> dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "prediction_type": self.prediction_type,
            "leader_coin_id": self.leader_coin_id,
            "target_coin_id": self.target_coin_id,
            "prediction_event": self.prediction_event,
            "expected_move": self.expected_move,
            "lag_hours": self.lag_hours,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "evaluation_time": self.evaluation_time,
            "status": self.status,
        }


@dataclass(slots=True, frozen=True)
class PredictionPublishedEvent:
    event_type: str
    payload: Mapping[str, Any]


@dataclass(slots=True, frozen=True)
class PredictionCreationBatch:
    status: str
    leader_coin_id: int
    created: int = 0
    reason: str | None = None
    cache_snapshots: tuple[PredictionCacheSnapshot, ...] = ()

    def to_summary(self, *, include_cache_snapshots: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status,
            "created": int(self.created),
            "leader_coin_id": int(self.leader_coin_id),
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        if include_cache_snapshots:
            payload["cache_snapshots"] = tuple(snapshot.as_cache_kwargs() for snapshot in self.cache_snapshots)
        return payload


@dataclass(slots=True, frozen=True)
class PredictionEvaluationBatch:
    status: str
    evaluated: int
    confirmed: int
    failed: int
    expired: int
    cache_snapshots: tuple[PredictionCacheSnapshot, ...] = ()
    events: tuple[PredictionPublishedEvent, ...] = ()

    def to_summary(self) -> dict[str, object]:
        return {
            "status": self.status,
            "evaluated": int(self.evaluated),
            "confirmed": int(self.confirmed),
            "failed": int(self.failed),
            "expired": int(self.expired),
        }


class PredictionService(PersistenceComponent):
    def __init__(
        self,
        uow: BaseAsyncUnitOfWork,
        *,
        predictions: PredictionRepository | None = None,
        relations: PredictionRelationRepository | None = None,
        candles: CandleRepository | None = None,
    ) -> None:
        super().__init__(
            uow.session,
            component_type="service",
            domain="predictions",
            component_name="PredictionService",
        )
        self._uow = uow
        self._predictions = predictions or PredictionRepository(uow.session)
        self._relations = relations or PredictionRelationRepository(uow.session)
        self._candles = candles or CandleRepository(uow.session)

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
            result = prediction.result
            if result is None:
                prediction.result = PredictionResult(
                    prediction_id=int(prediction.id),
                    actual_move=outcome.actual_move,
                    success=outcome.success,
                    profit=outcome.profit,
                    evaluated_at=now,
                )
            else:
                result.actual_move = outcome.actual_move
                result.success = outcome.success
                result.profit = outcome.profit
                result.evaluated_at = now
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

        result = PredictionEvaluationBatch(
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
        return result

    async def _evaluate_prediction_window(
        self,
        prediction: MarketPrediction,
        *,
        now: datetime,
    ) -> PredictionOutcome | None:
        start = ensure_utc(prediction.created_at)
        deadline = ensure_utc(prediction.evaluation_time)
        end = min(now, deadline)
        candles = await self._candles.fetch_points_between(
            coin_id=int(prediction.target_coin_id),
            timeframe=15,
            window_start=start,
            window_end=end,
        )
        if len(candles) < 2:
            return None
        entry_price = float(candles[0].close)
        closes = [float(item.close) for item in candles]
        highs = [float(item.high) for item in candles]
        lows = [float(item.low) for item in candles]
        max_move = (max(highs) - entry_price) / entry_price if entry_price else 0.0
        min_move = (min(lows) - entry_price) / entry_price if entry_price else 0.0
        last_move = (closes[-1] - entry_price) / entry_price if entry_price else 0.0
        if prediction.expected_move == "up":
            if max_move >= _PREDICTION_MOVE_THRESHOLD:
                return PredictionOutcome(status="confirmed", actual_move=max_move, success=True, profit=max_move)
            if now >= deadline and last_move <= -_PREDICTION_MOVE_THRESHOLD:
                return PredictionOutcome(status="failed", actual_move=last_move, success=False, profit=last_move)
            if now >= deadline:
                return PredictionOutcome(status="expired", actual_move=last_move, success=False, profit=last_move)
        else:
            bearish_move = abs(min_move)
            if bearish_move >= _PREDICTION_MOVE_THRESHOLD:
                return PredictionOutcome(status="confirmed", actual_move=min_move, success=True, profit=bearish_move)
            if now >= deadline and last_move >= _PREDICTION_MOVE_THRESHOLD:
                return PredictionOutcome(status="failed", actual_move=last_move, success=False, profit=-last_move)
            if now >= deadline:
                return PredictionOutcome(status="expired", actual_move=last_move, success=False, profit=-max(last_move, 0.0))
        return None

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


async def apply_prediction_creation_side_effects(result: PredictionCreationBatch) -> None:
    for snapshot in result.cache_snapshots:
        await cache_prediction_snapshot_async(**snapshot.as_cache_kwargs())


async def apply_prediction_evaluation_side_effects(result: PredictionEvaluationBatch) -> None:
    for snapshot in result.cache_snapshots:
        await cache_prediction_snapshot_async(**snapshot.as_cache_kwargs())
    for event in result.events:
        publish_event(event.event_type, dict(event.payload))


async def list_predictions_async(
    db: AsyncSession,
    *,
    limit: int = 100,
    status: str | None = None,
) -> list[dict[str, object]]:
    items = await PredictionQueryService(db).list_predictions(limit=limit, status=status)
    return [asdict(item) for item in items]


async def create_market_predictions_async(
    db: AsyncSession,
    *,
    leader_coin_id: int,
    prediction_event: str,
    expected_move: str,
    base_confidence: float,
    emit_events: bool = True,
    cache_snapshots: bool = True,
) -> dict[str, object]:
    del emit_events
    async with SessionUnitOfWork(db) as uow:
        result = await PredictionService(uow).create_market_predictions(
            leader_coin_id=leader_coin_id,
            prediction_event=prediction_event,
            expected_move=expected_move,
            base_confidence=base_confidence,
        )
        await uow.commit()
    if cache_snapshots:
        await apply_prediction_creation_side_effects(result)
    return result.to_summary(include_cache_snapshots=True)


async def evaluate_pending_predictions_async(
    db: AsyncSession,
    *,
    limit: int = 200,
    emit_events: bool = True,
) -> dict[str, object]:
    async with SessionUnitOfWork(db) as uow:
        result = await PredictionService(uow).evaluate_pending_predictions(limit=limit, emit_events=emit_events)
        await uow.commit()
    await apply_prediction_evaluation_side_effects(result)
    return result.to_summary()


def prediction_cache_snapshot_from_entry(entry: PredictionCacheEntry) -> PredictionCacheSnapshot:
    return PredictionCacheSnapshot.from_cache_entry(entry)


__all__ = [
    "PredictionCacheSnapshot",
    "PredictionCreationBatch",
    "PredictionEvaluationBatch",
    "PredictionPublishedEvent",
    "PredictionQueryService",
    "PredictionService",
    "apply_prediction_creation_side_effects",
    "apply_prediction_evaluation_side_effects",
    "cache_prediction_snapshot",
    "cache_prediction_snapshot_async",
    "create_market_predictions",
    "create_market_predictions_async",
    "evaluate_pending_predictions",
    "evaluate_pending_predictions_async",
    "list_predictions_async",
    "prediction_cache_snapshot_from_entry",
    "read_cached_prediction",
    "read_cached_prediction_async",
]
