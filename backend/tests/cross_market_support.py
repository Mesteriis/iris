from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy.orm import Session
from src.apps.cross_market.cache import cache_correlation_snapshot_async
from src.apps.cross_market.query_services import CrossMarketQueryService
from src.apps.cross_market.services import CrossMarketService
from src.apps.cross_market.support import relation_timeframe
from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.domain import utc_now
from src.apps.market_data.models import Coin
from src.apps.market_data.sources.base import MarketBar
from src.apps.predictions.models import MarketPrediction
from src.apps.predictions.services import (
    PredictionCreationBatch,
    PredictionEvaluationBatch,
    PredictionService,
    PredictionSideEffectDispatcher,
)
from src.apps.signals.services import SignalFusionService
from src.core.db.uow import SessionUnitOfWork
from src.runtime.streams.publisher import publish_event

from tests.fusion_support import create_test_coin, upsert_coin_metrics
from tests.market_data_support import upsert_base_candles
from tests.portfolio_support import create_sector


def _signal_fusion_payload(result) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": result.status,
        "coin_id": result.coin_id,
        "timeframe": result.timeframe,
        "signal_count": result.signal_count,
        "news_item_count": result.news_item_count,
        "news_bullish_score": round(float(result.news_bullish_score), 4),
        "news_bearish_score": round(float(result.news_bearish_score), 4),
    }
    if result.reason is not None:
        payload["reason"] = result.reason
    if result.decision_id is not None:
        payload["id"] = result.decision_id
    if result.decision is not None:
        payload["decision"] = result.decision
    if result.confidence is not None:
        payload["confidence"] = float(result.confidence)
    if result.regime is not None:
        payload["regime"] = result.regime
    return payload


def _prediction_batch_payload(result: PredictionCreationBatch | None) -> dict[str, object] | None:
    if result is None:
        return None
    payload: dict[str, object] = {
        "status": result.status,
        "created": int(result.created),
        "leader_coin_id": int(result.leader_coin_id),
    }
    if result.reason is not None:
        payload["reason"] = result.reason
    return payload


def _cross_market_relation_payload(result) -> dict[str, object]:
    payload: dict[str, object] = {"status": result.status}
    if result.follower_coin_id is not None:
        payload["follower_coin_id"] = int(result.follower_coin_id)
    if result.updated or result.status == "ok":
        payload["updated"] = int(result.updated)
    if result.published or result.status == "ok":
        payload["published"] = int(result.published)
    if result.leader_coin_id is not None:
        payload["leader_coin_id"] = int(result.leader_coin_id)
    if result.confidence is not None:
        payload["confidence"] = float(result.confidence)
    if result.reason is not None:
        payload["reason"] = result.reason
    return payload


def _cross_market_sector_payload(result) -> dict[str, object]:
    payload: dict[str, object] = {"status": result.status}
    if result.updated or result.status == "ok":
        payload["updated"] = int(result.updated)
    if result.timeframe is not None:
        payload["timeframe"] = int(result.timeframe)
    if result.reason is not None:
        payload["reason"] = result.reason
    return payload


def _cross_market_leader_payload(result) -> dict[str, object]:
    payload: dict[str, object] = {"status": result.status}
    if result.coin_id is not None:
        payload["coin_id"] = int(result.coin_id)
    if result.leader_coin_id is not None:
        payload["leader_coin_id"] = int(result.leader_coin_id)
    if result.direction is not None:
        payload["direction"] = result.direction
    if result.confidence is not None:
        payload["confidence"] = float(result.confidence)
    if result.predictions is not None:
        predictions = _prediction_batch_payload(result.predictions)
        if predictions is not None:
            payload["predictions"] = predictions
    if result.reason is not None:
        payload["reason"] = result.reason
    return payload


def _cross_market_process_payload(result) -> dict[str, object]:
    return {
        "status": result.status,
        "relations": _cross_market_relation_payload(result.relations),
        "sectors": _cross_market_sector_payload(result.sectors),
        "leader": _cross_market_leader_payload(result.leader),
    }


def generate_close_series(*, start_price: float, returns: list[float]) -> list[float]:
    closes = [start_price]
    for value in returns:
        closes.append(closes[-1] * (1 + value))
    return closes


def correlated_close_series(*, leader_returns: list[float], lag_bars: int, start_price: float) -> list[float]:
    follower_returns: list[float] = []
    for index in range(len(leader_returns)):
        if index < lag_bars:
            follower_returns.append(0.0015 if index % 2 == 0 else 0.0008)
            continue
        follower_returns.append((leader_returns[index - lag_bars] * 0.9) + 0.0004)
    return generate_close_series(start_price=start_price, returns=follower_returns)


def seed_candles(
    db: Session,
    *,
    coin: Coin,
    interval: str,
    closes: list[float],
    start: datetime,
    base_volume: float = 1_000.0,
) -> None:
    delta = timedelta(hours=1) if interval == "1h" else timedelta(minutes=15)
    bars: list[MarketBar] = []
    previous_close = closes[0]
    for index, close in enumerate(closes):
        timestamp = start + (delta * index)
        open_value = previous_close
        high_value = max(open_value, close) * 1.01
        low_value = min(open_value, close) * 0.99
        bars.append(
            MarketBar(
                timestamp=timestamp,
                open=open_value,
                high=high_value,
                low=low_value,
                close=close,
                volume=base_volume + (index * 10),
                source="fixture",
            )
        )
        previous_close = close
    upsert_base_candles(db, coin, interval, bars)


def create_cross_market_coin(
    db: Session,
    *,
    symbol: str,
    name: str,
    sector_name: str,
) -> Coin:
    coin = create_test_coin(db, symbol=symbol, name=name)
    sector = create_sector(db, name=sector_name)
    coin.sector_id = int(sector.id)
    coin.sector_code = sector_name
    db.commit()
    return coin


def set_market_metrics(
    db: Session,
    *,
    coin_id: int,
    regime: str,
    price_change_24h: float,
    volume_change_24h: float,
    volatility: float = 0.04,
    market_cap: float = 5_000_000_000.0,
) -> CoinMetrics:
    row = upsert_coin_metrics(db, coin_id=coin_id, regime=regime, timeframe=60)
    row.price_change_24h = price_change_24h
    row.volume_change_24h = volume_change_24h
    row.volatility = volatility
    row.market_cap = market_cap
    db.commit()
    db.refresh(row)
    return row


def create_pending_prediction(
    db: Session,
    *,
    leader_coin_id: int,
    target_coin_id: int,
    created_at: datetime,
    lag_hours: int,
    expected_move: str = "up",
    confidence: float = 0.75,
) -> MarketPrediction:
    row = MarketPrediction(
        prediction_type="cross_market_follow_through",
        leader_coin_id=leader_coin_id,
        target_coin_id=target_coin_id,
        prediction_event="leader_breakout" if expected_move == "up" else "leader_breakdown",
        expected_move=expected_move,
        lag_hours=lag_hours,
        confidence=confidence,
        created_at=created_at,
        evaluation_time=created_at + timedelta(hours=lag_hours),
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


DEFAULT_START = datetime(2026, 3, 1, 0, 0, tzinfo=UTC)


async def get_cross_market_leader_decision(
    async_db_session,
    *,
    leader_coin_id: int,
    timeframe: int,
):
    return await CrossMarketQueryService(async_db_session).get_latest_leader_decision(
        leader_coin_id=leader_coin_id,
        timeframe=timeframe,
    )


async def compute_cross_market_alignment_weight(
    async_db_session,
    *,
    coin_id: int,
    timeframe: int,
    directional_bias: float,
) -> float:
    async with SessionUnitOfWork(async_db_session) as uow:
        return await SignalFusionService(uow)._cross_market_alignment_weight(
            coin_id=coin_id,
            timeframe=timeframe,
            directional_bias=directional_bias,
        )


async def run_cross_market_relation_update(
    async_db_session,
    *,
    follower_coin_id: int,
    timeframe: int,
    emit_events: bool = True,
    apply_side_effects: bool = True,
) -> dict[str, object]:
    async with SessionUnitOfWork(async_db_session) as uow:
        service = CrossMarketService(uow)
        result, side_effects = await service._update_coin_relations(
            follower_coin_id=follower_coin_id,
            timeframe=timeframe,
            emit_events=emit_events,
        )
        if result.status == "ok":
            await uow.commit()
    if apply_side_effects:
        for effect in side_effects:
            await cache_correlation_snapshot_async(
                leader_coin_id=effect.leader_coin_id,
                follower_coin_id=effect.follower_coin_id,
                correlation=effect.correlation,
                lag_hours=effect.lag_hours,
                confidence=effect.confidence,
                updated_at=effect.updated_at,
            )
            if effect.publish_event:
                publish_event(
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
    return _cross_market_relation_payload(result)


async def run_cross_market_sector_refresh(
    async_db_session,
    *,
    timeframe: int,
    emit_events: bool = True,
    apply_side_effects: bool = True,
) -> dict[str, object]:
    async with SessionUnitOfWork(async_db_session) as uow:
        service = CrossMarketService(uow)
        result, effect = await service._refresh_sector_momentum(
            timeframe=timeframe,
            emit_events=emit_events,
        )
        if result.status == "ok":
            await uow.commit()
    if apply_side_effects and effect is not None:
        publish_event(
            "sector_rotation_detected",
            {
                "coin_id": 0,
                "timeframe": effect.timeframe,
                "timestamp": effect.timestamp,
                "source_sector": effect.source_sector,
                "target_sector": effect.target_sector,
                "source_strength": effect.source_strength,
                "target_strength": effect.target_strength,
            },
        )
    return _cross_market_sector_payload(result)


async def run_cross_market_leader_detection(
    async_db_session,
    *,
    coin_id: int,
    timeframe: int,
    payload: dict[str, object],
    emit_events: bool = True,
    apply_side_effects: bool = True,
) -> dict[str, object]:
    async with SessionUnitOfWork(async_db_session) as uow:
        service = CrossMarketService(uow)
        result, effect, requires_commit = await service._detect_market_leader(
            coin_id=coin_id,
            timeframe=timeframe,
            payload=payload,
            emit_events=emit_events,
        )
        if requires_commit:
            await uow.commit()
    if apply_side_effects and effect is not None:
        await PredictionSideEffectDispatcher().apply_creation(effect.prediction_batch)
        if effect.emit_event:
            publish_event(
                "market_leader_detected",
                {
                    "coin_id": effect.leader_coin_id,
                    "timeframe": effect.timeframe,
                    "timestamp": utc_now(),
                    "leader_coin_id": effect.leader_coin_id,
                    "leader_symbol": effect.leader_symbol,
                    "direction": effect.direction,
                    "confidence": effect.confidence,
                    "market_regime": effect.market_regime,
                },
            )
    return _cross_market_leader_payload(result)


async def run_cross_market_process_event(
    async_db_session,
    *,
    coin_id: int,
    timeframe: int,
    event_type: str,
    payload: dict[str, object],
    emit_events: bool = True,
) -> dict[str, object]:
    async with SessionUnitOfWork(async_db_session) as uow:
        result = await CrossMarketService(uow).process_event(
            coin_id=coin_id,
            timeframe=timeframe,
            event_type=event_type,
            payload=payload,
            emit_events=emit_events,
        )
        if result.status == "ok":
            await uow.commit()
    return _cross_market_process_payload(result)


async def run_prediction_creation(
    async_db_session,
    *,
    leader_coin_id: int,
    prediction_event: str,
    expected_move: str,
    base_confidence: float,
    emit_events: bool = False,
    apply_side_effects: bool = True,
) -> PredictionCreationBatch:
    async with SessionUnitOfWork(async_db_session) as uow:
        result = await PredictionService(uow).create_market_predictions(
            leader_coin_id=leader_coin_id,
            prediction_event=prediction_event,
            expected_move=expected_move,
            base_confidence=base_confidence,
            emit_events=emit_events,
        )
        if result.status == "ok":
            await uow.commit()
    if apply_side_effects:
        await PredictionSideEffectDispatcher().apply_creation(result)
    return result


async def run_prediction_evaluation(
    async_db_session,
    *,
    limit: int = 200,
    emit_events: bool = True,
    apply_side_effects: bool = True,
) -> PredictionEvaluationBatch:
    async with SessionUnitOfWork(async_db_session) as uow:
        result = await PredictionService(uow).evaluate_pending_predictions(
            limit=limit,
            emit_events=emit_events,
        )
        if result.status == "ok":
            await uow.commit()
    if apply_side_effects:
        await PredictionSideEffectDispatcher().apply_evaluation(result)
    return result
