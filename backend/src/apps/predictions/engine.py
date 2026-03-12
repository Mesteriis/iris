from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from src.apps.cross_market.models import CoinRelation
from src.apps.market_data.domain import ensure_utc, utc_now
from src.apps.market_data.models import Candle, Coin
from src.apps.market_data.repos import fetch_candle_points_between
from src.apps.predictions.cache import cache_prediction_snapshot, cache_prediction_snapshot_async
from src.apps.predictions.models import MarketPrediction, PredictionResult
from src.runtime.streams.publisher import publish_event

PREDICTION_MOVE_THRESHOLD = 0.015
PREDICTION_MAX_FOLLOWERS = 8


@dataclass(slots=True, frozen=True)
class PredictionOutcome:
    status: str
    actual_move: float
    success: bool
    profit: float


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def create_market_predictions(
    db: Session,
    *,
    leader_coin_id: int,
    prediction_event: str,
    expected_move: str,
    base_confidence: float,
    emit_events: bool = True,
) -> dict[str, object]:
    now = utc_now()
    relations = db.scalars(
        select(CoinRelation)
        .where(
            CoinRelation.leader_coin_id == leader_coin_id,
            CoinRelation.confidence >= 0.5,
        )
        .order_by(CoinRelation.confidence.desc(), CoinRelation.correlation.desc())
        .limit(PREDICTION_MAX_FOLLOWERS)
    ).all()
    if not relations:
        return {"status": "skipped", "reason": "relations_not_found", "leader_coin_id": leader_coin_id}

    created = 0
    for relation in relations:
        target_coin = db.get(Coin, relation.follower_coin_id)
        if target_coin is None or target_coin.deleted_at is not None or not target_coin.enabled:
            continue
        existing = db.scalar(
            select(MarketPrediction)
            .where(
                MarketPrediction.leader_coin_id == leader_coin_id,
                MarketPrediction.target_coin_id == relation.follower_coin_id,
                MarketPrediction.prediction_event == prediction_event,
                MarketPrediction.expected_move == expected_move,
                MarketPrediction.status == "pending",
            )
            .order_by(MarketPrediction.created_at.desc(), MarketPrediction.id.desc())
            .limit(1)
        )
        if existing is not None and ensure_utc(existing.evaluation_time) >= now:
            continue
        confidence = _clamp(base_confidence * max(float(relation.confidence), 0.55), 0.35, 0.98)
        prediction = MarketPrediction(
            prediction_type="cross_market_follow_through",
            leader_coin_id=leader_coin_id,
            target_coin_id=relation.follower_coin_id,
            prediction_event=prediction_event,
            expected_move=expected_move,
            lag_hours=max(int(relation.lag_hours), 1),
            confidence=confidence,
            evaluation_time=now + timedelta(hours=max(int(relation.lag_hours), 1)),
            status="pending",
        )
        db.add(prediction)
        db.flush()
        cache_prediction_snapshot(
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
        created += 1
    db.commit()
    return {"status": "ok", "created": created, "leader_coin_id": leader_coin_id}


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
    now = utc_now()
    relations = (
        await db.execute(
            select(CoinRelation)
            .where(
                CoinRelation.leader_coin_id == leader_coin_id,
                CoinRelation.confidence >= 0.5,
            )
            .order_by(CoinRelation.confidence.desc(), CoinRelation.correlation.desc())
            .limit(PREDICTION_MAX_FOLLOWERS)
        )
    ).scalars().all()
    if not relations:
        return {"status": "skipped", "reason": "relations_not_found", "leader_coin_id": leader_coin_id}

    created = 0
    snapshots: list[dict[str, object]] = []
    for relation in relations:
        target_coin = await db.get(Coin, relation.follower_coin_id)
        if target_coin is None or target_coin.deleted_at is not None or not target_coin.enabled:
            continue
        existing = await db.scalar(
            select(MarketPrediction)
            .where(
                MarketPrediction.leader_coin_id == leader_coin_id,
                MarketPrediction.target_coin_id == relation.follower_coin_id,
                MarketPrediction.prediction_event == prediction_event,
                MarketPrediction.expected_move == expected_move,
                MarketPrediction.status == "pending",
            )
            .order_by(MarketPrediction.created_at.desc(), MarketPrediction.id.desc())
            .limit(1)
        )
        if existing is not None and ensure_utc(existing.evaluation_time) >= now:
            continue
        confidence = _clamp(base_confidence * max(float(relation.confidence), 0.55), 0.35, 0.98)
        prediction = MarketPrediction(
            prediction_type="cross_market_follow_through",
            leader_coin_id=leader_coin_id,
            target_coin_id=relation.follower_coin_id,
            prediction_event=prediction_event,
            expected_move=expected_move,
            lag_hours=max(int(relation.lag_hours), 1),
            confidence=confidence,
            evaluation_time=now + timedelta(hours=max(int(relation.lag_hours), 1)),
            status="pending",
        )
        db.add(prediction)
        await db.flush()
        snapshot = {
            "prediction_id": int(prediction.id),
            "prediction_type": prediction.prediction_type,
            "leader_coin_id": int(prediction.leader_coin_id),
            "target_coin_id": int(prediction.target_coin_id),
            "prediction_event": prediction.prediction_event,
            "expected_move": prediction.expected_move,
            "lag_hours": int(prediction.lag_hours),
            "confidence": float(prediction.confidence),
            "created_at": prediction.created_at,
            "evaluation_time": prediction.evaluation_time,
            "status": prediction.status,
        }
        if cache_snapshots:
            await cache_prediction_snapshot_async(**snapshot)
        snapshots.append(snapshot)
        created += 1
    return {
        "status": "ok",
        "created": created,
        "leader_coin_id": leader_coin_id,
        "cache_snapshots": tuple(snapshots),
    }


def _evaluate_prediction_window(
    db: Session,
    prediction: MarketPrediction,
    *,
    now,
) -> PredictionOutcome | None:
    start = ensure_utc(prediction.created_at)
    deadline = ensure_utc(prediction.evaluation_time)
    end = min(now, deadline)
    candles = fetch_candle_points_between(db, prediction.target_coin_id, 15, start, end)
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
        if max_move >= PREDICTION_MOVE_THRESHOLD:
            return PredictionOutcome(status="confirmed", actual_move=max_move, success=True, profit=max_move)
        if now >= deadline and last_move <= -PREDICTION_MOVE_THRESHOLD:
            return PredictionOutcome(status="failed", actual_move=last_move, success=False, profit=last_move)
        if now >= deadline:
            return PredictionOutcome(status="expired", actual_move=last_move, success=False, profit=last_move)
    else:
        bearish_move = abs(min_move)
        if bearish_move >= PREDICTION_MOVE_THRESHOLD:
            return PredictionOutcome(status="confirmed", actual_move=min_move, success=True, profit=bearish_move)
        if now >= deadline and last_move >= PREDICTION_MOVE_THRESHOLD:
            return PredictionOutcome(status="failed", actual_move=last_move, success=False, profit=-last_move)
        if now >= deadline:
            return PredictionOutcome(status="expired", actual_move=last_move, success=False, profit=-max(last_move, 0.0))
    return None


def _apply_relation_feedback(db: Session, prediction: MarketPrediction, *, success: bool) -> CoinRelation | None:
    relation = db.scalar(
        select(CoinRelation)
        .where(
            CoinRelation.leader_coin_id == prediction.leader_coin_id,
            CoinRelation.follower_coin_id == prediction.target_coin_id,
        )
        .limit(1)
    )
    if relation is None:
        return None
    delta = 0.04 if success else -0.05
    relation.confidence = _clamp(float(relation.confidence) + delta, 0.05, 0.99)
    relation.updated_at = utc_now()
    return relation


async def _evaluate_prediction_window_async(
    db: AsyncSession,
    prediction: MarketPrediction,
    *,
    now,
) -> PredictionOutcome | None:
    start = ensure_utc(prediction.created_at)
    deadline = ensure_utc(prediction.evaluation_time)
    end = min(now, deadline)
    candles = (
        await db.execute(
            select(Candle.open, Candle.high, Candle.low, Candle.close, Candle.timestamp)
            .where(
                Candle.coin_id == int(prediction.target_coin_id),
                Candle.timeframe == 15,
                Candle.timestamp >= start,
                Candle.timestamp <= end,
            )
            .order_by(Candle.timestamp.asc())
        )
    ).all()
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
        if max_move >= PREDICTION_MOVE_THRESHOLD:
            return PredictionOutcome(status="confirmed", actual_move=max_move, success=True, profit=max_move)
        if now >= deadline and last_move <= -PREDICTION_MOVE_THRESHOLD:
            return PredictionOutcome(status="failed", actual_move=last_move, success=False, profit=last_move)
        if now >= deadline:
            return PredictionOutcome(status="expired", actual_move=last_move, success=False, profit=last_move)
    else:
        bearish_move = abs(min_move)
        if bearish_move >= PREDICTION_MOVE_THRESHOLD:
            return PredictionOutcome(status="confirmed", actual_move=min_move, success=True, profit=bearish_move)
        if now >= deadline and last_move >= PREDICTION_MOVE_THRESHOLD:
            return PredictionOutcome(status="failed", actual_move=last_move, success=False, profit=-last_move)
        if now >= deadline:
            return PredictionOutcome(status="expired", actual_move=last_move, success=False, profit=-max(last_move, 0.0))
    return None


async def _apply_relation_feedback_async(
    db: AsyncSession,
    prediction: MarketPrediction,
    *,
    success: bool,
) -> CoinRelation | None:
    relation = await db.scalar(
        select(CoinRelation)
        .where(
            CoinRelation.leader_coin_id == prediction.leader_coin_id,
            CoinRelation.follower_coin_id == prediction.target_coin_id,
        )
        .limit(1)
    )
    if relation is None:
        return None
    delta = 0.04 if success else -0.05
    relation.confidence = _clamp(float(relation.confidence) + delta, 0.05, 0.99)
    relation.updated_at = utc_now()
    return relation


def evaluate_pending_predictions(
    db: Session,
    *,
    limit: int = 200,
    emit_events: bool = True,
) -> dict[str, object]:
    now = utc_now()
    rows = db.scalars(
        select(MarketPrediction)
        .where(MarketPrediction.status == "pending")
        .order_by(MarketPrediction.created_at.asc(), MarketPrediction.id.asc())
        .limit(max(limit, 1))
    ).all()
    confirmed = 0
    failed = 0
    expired = 0
    for prediction in rows:
        outcome = _evaluate_prediction_window(db, prediction, now=now)
        if outcome is None:
            continue
        prediction.status = outcome.status
        result = prediction.result
        if result is None:
            result = PredictionResult(
                prediction_id=int(prediction.id),
                actual_move=outcome.actual_move,
                success=outcome.success,
                profit=outcome.profit,
                evaluated_at=now,
            )
            db.add(result)
        else:
            result.actual_move = outcome.actual_move
            result.success = outcome.success
            result.profit = outcome.profit
            result.evaluated_at = now
        relation = _apply_relation_feedback(db, prediction, success=outcome.success)
        cache_prediction_snapshot(
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
        if outcome.status == "confirmed":
            confirmed += 1
        elif outcome.status == "expired":
            expired += 1
        else:
            failed += 1
        if emit_events:
            event_type = "prediction_confirmed" if outcome.status == "confirmed" else "prediction_failed"
            publish_event(
                event_type,
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
                },
            )
    db.commit()
    return {
        "status": "ok",
        "evaluated": len(rows),
        "confirmed": confirmed,
        "failed": failed,
        "expired": expired,
    }


async def evaluate_pending_predictions_async(
    db: AsyncSession,
    *,
    limit: int = 200,
    emit_events: bool = True,
) -> dict[str, object]:
    now = utc_now()
    rows = (
        await db.execute(
            select(MarketPrediction)
            .options(selectinload(MarketPrediction.result))
            .where(MarketPrediction.status == "pending")
            .order_by(MarketPrediction.created_at.asc(), MarketPrediction.id.asc())
            .limit(max(limit, 1))
        )
    ).scalars().all()
    confirmed = 0
    failed = 0
    expired = 0
    for prediction in rows:
        outcome = await _evaluate_prediction_window_async(db, prediction, now=now)
        if outcome is None:
            continue
        prediction.status = outcome.status
        result = prediction.result
        if result is None:
            result = PredictionResult(
                prediction_id=int(prediction.id),
                actual_move=outcome.actual_move,
                success=outcome.success,
                profit=outcome.profit,
                evaluated_at=now,
            )
            db.add(result)
        else:
            result.actual_move = outcome.actual_move
            result.success = outcome.success
            result.profit = outcome.profit
            result.evaluated_at = now
        relation = await _apply_relation_feedback_async(db, prediction, success=outcome.success)
        await cache_prediction_snapshot_async(
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
        if outcome.status == "confirmed":
            confirmed += 1
        elif outcome.status == "expired":
            expired += 1
        else:
            failed += 1
        if emit_events:
            event_type = "prediction_confirmed" if outcome.status == "confirmed" else "prediction_failed"
            publish_event(
                event_type,
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
                },
            )
    await db.commit()
    return {
        "status": "ok",
        "evaluated": len(rows),
        "confirmed": confirmed,
        "failed": failed,
        "expired": expired,
    }
