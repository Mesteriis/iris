from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.explanations.contracts import ExplainKind
from src.apps.explanations.models import AIExplanation
from src.apps.explanations.read_models import (
    ExplanationContextBundle,
    ExplanationReadModel,
    explanation_read_model_from_orm,
)
from src.apps.signals.query_services import SignalQueryService
from src.apps.signals.read_models import investment_decision_payload, signal_payload
from src.core.db.persistence import AsyncQueryService


class ExplanationQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="explanations", service_name="ExplanationQueryService")
        self._signals = SignalQueryService(session)

    async def get_explanation(
        self,
        *,
        explain_kind: ExplainKind,
        subject_id: int,
    ) -> ExplanationReadModel | None:
        self._log_debug(
            "query.get_explanation",
            mode="read",
            explain_kind=explain_kind.value,
            subject_id=subject_id,
        )
        row = await self.session.scalar(
            select(AIExplanation)
            .where(
                AIExplanation.explain_kind == explain_kind.value,
                AIExplanation.subject_id == int(subject_id),
            )
            .order_by(AIExplanation.updated_at.desc())
            .limit(1)
        )
        if row is None:
            self._log_debug("query.get_explanation.result", mode="read", found=False)
            return None
        item = explanation_read_model_from_orm(row)
        self._log_debug("query.get_explanation.result", mode="read", found=True)
        return item

    async def build_signal_context(self, signal_id: int) -> ExplanationContextBundle | None:
        self._log_debug("query.build_signal_explanation_context", mode="read", signal_id=signal_id)
        item = await self._signals.get_signal_by_id(signal_id)
        if item is None:
            self._log_debug("query.build_signal_explanation_context.result", mode="read", found=False)
            return None
        payload = signal_payload(item)
        bundle = ExplanationContextBundle(
            explain_kind=ExplainKind.SIGNAL,
            subject_id=int(signal_id),
            coin_id=int(payload["coin_id"]),
            symbol=str(payload["symbol"]),
            timeframe=int(payload["timeframe"]),
            subject_updated_at=payload["created_at"],
            context={
                "explain_kind": ExplainKind.SIGNAL.value,
                "subject_id": int(signal_id),
                **payload,
            },
            refs_json={
                "explain_kind": ExplainKind.SIGNAL.value,
                "subject_id": int(signal_id),
                "coin_id": int(payload["coin_id"]),
                "symbol": str(payload["symbol"]),
                "timeframe": int(payload["timeframe"]),
                "signal_type": str(payload["signal_type"]),
            },
        )
        self._log_debug("query.build_signal_explanation_context.result", mode="read", found=True)
        return bundle

    async def build_decision_context(self, decision_id: int) -> ExplanationContextBundle | None:
        self._log_debug("query.build_decision_explanation_context", mode="read", decision_id=decision_id)
        item = await self._signals.get_decision_by_id(decision_id)
        if item is None:
            self._log_debug("query.build_decision_explanation_context.result", mode="read", found=False)
            return None
        payload = investment_decision_payload(item)
        bundle = ExplanationContextBundle(
            explain_kind=ExplainKind.DECISION,
            subject_id=int(decision_id),
            coin_id=int(payload["coin_id"]),
            symbol=str(payload["symbol"]),
            timeframe=int(payload["timeframe"]),
            subject_updated_at=payload["created_at"],
            context={
                "explain_kind": ExplainKind.DECISION.value,
                "subject_id": int(decision_id),
                **payload,
            },
            refs_json={
                "explain_kind": ExplainKind.DECISION.value,
                "subject_id": int(decision_id),
                "coin_id": int(payload["coin_id"]),
                "symbol": str(payload["symbol"]),
                "timeframe": int(payload["timeframe"]),
                "decision": str(payload["decision"]),
            },
        )
        self._log_debug("query.build_decision_explanation_context.result", mode="read", found=True)
        return bundle

    async def signal_exists(self, signal_id: int) -> bool:
        return await self._signals.get_signal_by_id(signal_id) is not None

    async def decision_exists(self, decision_id: int) -> bool:
        return await self._signals.get_decision_by_id(decision_id) is not None


__all__ = ["ExplanationQueryService"]
