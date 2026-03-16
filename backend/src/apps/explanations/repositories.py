from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.explanations.contracts import ExplainKind
from src.apps.explanations.models import AIExplanation
from src.core.db.persistence import AsyncRepository
from src.core.i18n import content_rendered_locale


class ExplanationRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="explanations", repository_name="ExplanationRepository")

    async def get_by_subject(
        self,
        *,
        explain_kind: ExplainKind,
        subject_id: int,
    ) -> AIExplanation | None:
        self._log_debug(
            "repo.get_explanation_by_subject",
            mode="write",
            explain_kind=explain_kind.value,
            subject_id=subject_id,
        )
        row = await self.session.scalar(
            select(AIExplanation)
            .where(
                AIExplanation.explain_kind == explain_kind.value,
                AIExplanation.subject_id == int(subject_id),
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
                content_kind=item.content_kind,
                rendered_locale=content_rendered_locale(item.content_json),
            )
            self.session.add(item)
        else:
            item = existing
            for key, value in payload.items():
                setattr(item, key, value)
            self._log_info(
                "repo.update_explanation",
                mode="write",
                explanation_id=int(item.id),
                explain_kind=item.explain_kind,
                subject_id=int(item.subject_id),
                content_kind=item.content_kind,
                rendered_locale=content_rendered_locale(item.content_json),
            )
        await self.session.flush()
        await self.session.refresh(item)
        return item


__all__ = ["ExplanationRepository"]
