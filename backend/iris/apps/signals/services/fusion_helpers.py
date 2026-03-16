from typing import TYPE_CHECKING

from iris.apps.signals.fusion_support import _clamp
from iris.core.db.uow import BaseAsyncUnitOfWork

if TYPE_CHECKING:
    from iris.apps.signals.repositories import SignalFusionRepository
    from iris.apps.signals.services.fusion_service import SignalFusionService
    from iris.apps.signals.services.results import SignalFusionBatchResult, SignalFusionResult


async def enrich_signal_context(
    *,
    logger: SignalFusionService,
    uow: BaseAsyncUnitOfWork,
    coin_id: int,
    timeframe: int,
    candle_timestamp: object | None,
) -> None:
    from iris.apps.patterns.task_services import PatternSignalContextService

    logger._log_debug(
        "service.evaluate_market_decision.context_adapter",
        mode="write",
        coin_id=coin_id,
        timeframe=timeframe,
    )
    await PatternSignalContextService(uow).enrich_context_only(
        coin_id=int(coin_id),
        timeframe=int(timeframe),
        candle_timestamp=candle_timestamp,
    )


def skipped_fusion_result(
    *,
    logger: SignalFusionService,
    coin_id: int,
    timeframe: int,
    reason: str,
) -> SignalFusionResult:
    from iris.apps.signals.services.results import SignalFusionResult

    logger._log_debug(
        "service.evaluate_market_decision.result",
        mode="write",
        coin_id=coin_id,
        timeframe=timeframe,
        status="skipped",
        reason=reason,
    )
    return SignalFusionResult(
        status="skipped",
        coin_id=coin_id,
        timeframe=timeframe,
        reason=reason,
    )


def skipped_fusion_batch_result(
    *,
    logger: SignalFusionService,
    coin_id: int,
    reason: str,
) -> SignalFusionBatchResult:
    from iris.apps.signals.services.results import SignalFusionBatchResult

    logger._log_debug(
        "service.evaluate_news_fusion_event.result",
        mode="write",
        coin_id=coin_id,
        status="skipped",
        reason=reason,
    )
    return SignalFusionBatchResult(
        status="skipped",
        coin_id=coin_id,
        timeframes=(),
        items=(),
        reason=reason,
    )


async def cross_market_alignment_weight(
    *,
    signals: SignalFusionRepository,
    coin_id: int,
    timeframe: int,
    directional_bias: float,
) -> float:
    if directional_bias == 0:
        return 1.0

    from iris.apps.signals import services as signals_services_module

    relations = await signals.list_alignment_relations(follower_coin_id=int(coin_id), limit=3)
    if not relations:
        return 1.0
    leader_decisions = await signals.list_latest_leader_decisions(
        leader_coin_ids=[int(item.leader_coin_id) for item in relations],
        timeframe=int(timeframe),
    )
    weight = 1.0
    for relation in relations:
        cached = await signals_services_module.read_cached_correlation_async(
            leader_coin_id=int(relation.leader_coin_id),
            follower_coin_id=int(relation.follower_coin_id),
        )
        decision, decision_confidence = leader_decisions.get(int(relation.leader_coin_id), (None, 0.0))
        if decision is None:
            continue
        relation_strength = float(cached.confidence if cached is not None else relation.confidence) * float(
            cached.correlation if cached is not None else relation.correlation
        )
        delta = min(relation_strength * max(float(decision_confidence), 0.3), 0.22)
        if (directional_bias > 0 and decision == "BUY") or (directional_bias < 0 and decision == "SELL"):
            weight += delta
        elif decision in {"BUY", "SELL"}:
            weight -= delta * 0.8
    sector_trend = await signals.get_sector_trend(coin_id=int(coin_id), timeframe=int(timeframe))
    if sector_trend is not None:
        if (directional_bias > 0 and sector_trend == "bullish") or (directional_bias < 0 and sector_trend == "bearish"):
            weight += 0.05
        elif sector_trend in {"bullish", "bearish"}:
            weight -= 0.04
    return float(_clamp(weight, 0.75, 1.35))
