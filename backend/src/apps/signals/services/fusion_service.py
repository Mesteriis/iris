from src.apps.signals.engines import SignalFusionEngineResult, run_signal_fusion
from src.apps.signals.engines.contracts import SignalFusionInput
from src.apps.signals.fusion_support import FUSION_NEWS_TIMEFRAMES, MATERIAL_CONFIDENCE_DELTA
from src.apps.signals.models import MarketDecision
from src.apps.signals.repositories import SignalFusionRepository
from src.apps.signals.services.fusion_helpers import (
    cross_market_alignment_weight,
    enrich_signal_context,
    skipped_fusion_batch_result,
    skipped_fusion_result,
)
from src.apps.signals.services.fusion_inputs import SignalFusionInputBuilder
from src.apps.signals.services.results import (
    SignalDecisionCacheSnapshot,
    SignalFusionBatchResult,
    SignalFusionPendingEvent,
    SignalFusionResult,
)
from src.core.db.persistence import PersistenceComponent
from src.core.db.uow import BaseAsyncUnitOfWork


class SignalFusionService(PersistenceComponent):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(
            uow.session,
            component_type="service",
            domain="signals",
            component_name="SignalFusionService",
        )
        self._uow = uow
        self._signals = SignalFusionRepository(uow.session)
        self._input_builder = SignalFusionInputBuilder(uow=uow, signals=self._signals)

    async def evaluate_news_fusion_event(
        self,
        *,
        coin_id: int,
        reference_timestamp: object | None = None,
        emit_event: bool = True,
    ) -> SignalFusionBatchResult:
        self._log_debug(
            "service.evaluate_news_fusion_event",
            mode="write",
            coin_id=coin_id,
            emit_event=emit_event,
        )
        timeframes = await self._signals.list_candidate_fusion_timeframes(
            coin_id=int(coin_id),
            allowed_timeframes=FUSION_NEWS_TIMEFRAMES,
        )
        if not timeframes:
            return skipped_fusion_batch_result(
                logger=self,
                coin_id=int(coin_id),
                reason="fusion_timeframes_not_found",
            )
        items = tuple(
            [
                await self.evaluate_market_decision(
                    coin_id=int(coin_id),
                    timeframe=int(timeframe),
                    trigger_timestamp=None,
                    news_reference_timestamp=reference_timestamp,
                    emit_event=emit_event,
                )
                for timeframe in timeframes
            ]
        )
        self._log_info(
            "service.evaluate_news_fusion_event.result",
            mode="write",
            coin_id=coin_id,
            timeframes=len(timeframes),
        )
        return SignalFusionBatchResult(
            status="ok",
            coin_id=int(coin_id),
            timeframes=tuple(int(item) for item in timeframes),
            items=items,
        )

    async def evaluate_market_decision(
        self,
        *,
        coin_id: int,
        timeframe: int,
        trigger_timestamp: object | None = None,
        news_reference_timestamp: object | None = None,
        emit_event: bool = True,
    ) -> SignalFusionResult:
        self._log_debug(
            "service.evaluate_market_decision",
            mode="write",
            coin_id=coin_id,
            timeframe=timeframe,
            emit_event=emit_event,
        )
        await self._enrich_context(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            candle_timestamp=trigger_timestamp,
        )
        prepared = await self._input_builder.build(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            trigger_timestamp=trigger_timestamp,
            news_reference_timestamp=news_reference_timestamp,
        )
        if prepared is None:
            return skipped_fusion_result(
                logger=self,
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                reason="signals_not_found",
            )
        fused = self._run_fusion_engine(fusion_input=prepared.fusion_input)
        if fused is None:
            return skipped_fusion_result(
                logger=self,
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                reason="fusion_window_empty",
            )

        latest = await self._signals.get_latest_market_decision(coin_id=int(coin_id), timeframe=int(timeframe))
        if (
            latest is not None
            and latest.decision == fused.decision
            and int(latest.signal_count) == fused.signal_count
            and abs(float(latest.confidence) - fused.confidence) < MATERIAL_CONFIDENCE_DELTA
        ):
            self._log_debug(
                "service.evaluate_market_decision.result",
                mode="write",
                coin_id=coin_id,
                timeframe=timeframe,
                status="skipped",
                reason="decision_unchanged",
            )
            return SignalFusionResult(
                status="skipped",
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                reason="decision_unchanged",
                decision_id=int(latest.id),
                decision=str(latest.decision),
                confidence=float(latest.confidence),
                signal_count=int(latest.signal_count),
                regime=fused.regime,
                news_item_count=fused.news_item_count,
                news_bullish_score=fused.news_bullish_score,
                news_bearish_score=fused.news_bearish_score,
                explainability=fused.explainability,
                cache_snapshot=SignalDecisionCacheSnapshot(
                    coin_id=int(coin_id),
                    timeframe=int(timeframe),
                    decision=str(latest.decision),
                    confidence=float(latest.confidence),
                    signal_count=int(latest.signal_count),
                    regime=fused.regime,
                    created_at=latest.created_at,
                ),
            )

        row = await self._signals.add_market_decision(
            MarketDecision(
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                decision=fused.decision,
                confidence=fused.confidence,
                signal_count=fused.signal_count,
            )
        )
        pending_events: tuple[SignalFusionPendingEvent, ...] = ()
        if emit_event:
            pending_events = (
                SignalFusionPendingEvent(
                    "decision_generated",
                    {
                        "coin_id": int(coin_id),
                        "timeframe": int(timeframe),
                        "timestamp": fused.latest_timestamp,
                        "decision": row.decision,
                        "confidence": float(row.confidence),
                        "signal_count": int(row.signal_count),
                        "regime": fused.regime,
                        "news_item_count": fused.news_item_count,
                        "news_bullish_score": round(float(fused.news_bullish_score), 4),
                        "news_bearish_score": round(float(fused.news_bearish_score), 4),
                        "source": "signal_fusion",
                    },
                ),
            )
        result = SignalFusionResult(
            status="ok",
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            decision_id=int(row.id),
            decision=str(row.decision),
            confidence=float(row.confidence),
            signal_count=int(row.signal_count),
            regime=fused.regime,
            news_item_count=fused.news_item_count,
            news_bullish_score=fused.news_bullish_score,
            news_bearish_score=fused.news_bearish_score,
            explainability=fused.explainability,
            cache_snapshot=SignalDecisionCacheSnapshot(
                coin_id=int(coin_id),
                timeframe=int(timeframe),
                decision=str(row.decision),
                confidence=float(row.confidence),
                signal_count=int(row.signal_count),
                regime=fused.regime,
                created_at=row.created_at,
            ),
            pending_events=pending_events,
        )
        self._log_info(
            "service.evaluate_market_decision.result",
            mode="write",
            coin_id=coin_id,
            timeframe=timeframe,
            decision=result.decision,
            signal_count=result.signal_count,
        )
        return result

    def _run_fusion_engine(self, *, fusion_input: SignalFusionInput) -> SignalFusionEngineResult | None:
        return run_signal_fusion(fusion_input)

    async def _enrich_context(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: object | None,
    ) -> None:
        await enrich_signal_context(
            logger=self,
            uow=self._uow,
            coin_id=coin_id,
            timeframe=timeframe,
            candle_timestamp=candle_timestamp,
        )

    async def _cross_market_alignment_weight(
        self,
        *,
        coin_id: int,
        timeframe: int,
        directional_bias: float,
    ) -> float:
        return await cross_market_alignment_weight(
            signals=self._signals,
            coin_id=coin_id,
            timeframe=timeframe,
            directional_bias=directional_bias,
        )


__all__ = ["SignalFusionService"]
