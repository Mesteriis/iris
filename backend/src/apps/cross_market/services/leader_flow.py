from __future__ import annotations

from typing import TYPE_CHECKING

from src.apps.cross_market.engines import CrossMarketLeaderDetectionInput, evaluate_market_leader
from src.apps.cross_market.services.results import CrossMarketLeaderDetectionResult
from src.apps.cross_market.services.side_effects import CrossMarketLeaderSideEffect

if TYPE_CHECKING:
    from src.apps.cross_market.services.cross_market_service import CrossMarketService


async def detect_market_leader(
    *,
    service: CrossMarketService,
    coin_id: int,
    timeframe: int,
    payload: dict[str, object],
    emit_events: bool,
) -> tuple[CrossMarketLeaderDetectionResult, CrossMarketLeaderSideEffect | None, bool]:
    service._log_debug("service.detect_market_leader", mode="write", coin_id=coin_id, timeframe=timeframe)
    context = await service._queries.get_leader_detection_context(coin_id=coin_id)
    if context is None:
        return (
            CrossMarketLeaderDetectionResult(
                status="skipped",
                reason="coin_metrics_not_found",
                coin_id=int(coin_id),
            ),
            None,
            False,
        )

    engine_result = evaluate_market_leader(
        CrossMarketLeaderDetectionInput(
            activity_bucket=str(payload.get("activity_bucket") or context.activity_bucket or ""),
            price_change_24h=float(payload.get("price_change_24h") or context.price_change_24h or 0.0),
            volume_change_24h=float(context.volume_change_24h or 0.0),
            market_regime=str(payload.get("market_regime") or context.market_regime or ""),
        )
    )
    if engine_result.status != "ok" or engine_result.direction is None or engine_result.confidence is None:
        return (
            CrossMarketLeaderDetectionResult(
                status="skipped",
                reason=engine_result.reason or "leader_threshold_not_met",
                coin_id=int(coin_id),
            ),
            None,
            False,
        )

    predictions = await service._prediction_service().create_market_predictions(
        leader_coin_id=coin_id,
        prediction_event="leader_breakout" if engine_result.direction == "up" else "leader_breakdown",
        expected_move=engine_result.direction,
        base_confidence=engine_result.confidence,
    )
    effect = CrossMarketLeaderSideEffect(
        timeframe=int(timeframe),
        leader_coin_id=coin_id,
        leader_symbol=context.symbol,
        direction=engine_result.direction,
        confidence=engine_result.confidence,
        market_regime=str(payload.get("market_regime") or context.market_regime or ""),
        emit_event=emit_events,
        prediction_batch=predictions,
    )
    result = CrossMarketLeaderDetectionResult(
        status="ok",
        leader_coin_id=int(coin_id),
        direction=engine_result.direction,
        confidence=engine_result.confidence,
        predictions=predictions,
    )
    service._log_info(
        "service.detect_market_leader.result",
        mode="write",
        coin_id=coin_id,
        direction=engine_result.direction,
        created_predictions=int(predictions.created),
    )
    return result, effect, bool(predictions.created)
