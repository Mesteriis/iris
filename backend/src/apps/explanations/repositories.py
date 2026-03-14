from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.explanations.contracts import ExplainKind
from src.apps.explanations.models import AIExplanation
from src.core.db.persistence import AsyncRepository


class ExplanationRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="explanations", repository_name="ExplanationRepository")

    async def get_by_subject(
        self,
        *,
        explain_kind: ExplainKind,
        subject_id: int,
        language: str,
    ) -> AIExplanation | None:
        self._log_debug(
            "repo.get_explanation_by_subject",
            mode="write",
            explain_kind=explain_kind.value,
            subject_id=subject_id,
            language=language,
        )
        row = await self.session.scalar(
            select(AIExplanation)
            .where(
                AIExplanation.explain_kind == explain_kind.value,
                AIExplanation.subject_id == int(subject_id),
                AIExplanation.language == language,
            )
            .limit(1)
        )
        self._log_debug("repo.get_explanation_by_subject.result", mode="write", found=row is not None)
        return row

    async def upsert_explanation(
        self,
        *,
        existing: AIExplanation | None,
        payload: Mapping[str, Any],
    ) -> AIExplanation:
        if existing is None:
            item = AIExplanation(**dict(payload))
            self._log_info(
                "repo.add_explanation",
                mode="write",
                explain_kind=item.explain_kind,
                subject_id=int(item.subject_id),
                language=item.language,
            )
            self.session.add(item)
        else:
            item = existing
            self._log_info(
                "repo.update_explanation",
                mode="write",
                explanation_id=int(item.id),
                explain_kind=item.explain_kind,
                subject_id=int(item.subject_id),
                language=item.language,
            )
            for key, value in payload.items():
                setattr(item, key, value)
        await self.session.flush()
        await self.session.refresh(item)
        return item


__all__ = ["ExplanationRepository"]
