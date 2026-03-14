from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.db.uow import BaseAsyncUnitOfWork

if TYPE_CHECKING:
    from src.apps.signals.services.fusion_service import SignalFusionService
    from src.apps.signals.services.results import SignalFusionBatchResult, SignalFusionResult


async def enrich_signal_context(
    *,
    logger: SignalFusionService,
    uow: BaseAsyncUnitOfWork,
    coin_id: int,
    timeframe: int,
    candle_timestamp: object | None,
) -> None:
    from src.apps.patterns.task_services import PatternSignalContextService

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
    from src.apps.signals.services.results import SignalFusionResult

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
    from src.apps.signals.services.results import SignalFusionBatchResult

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
