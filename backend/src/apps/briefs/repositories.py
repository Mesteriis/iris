from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.briefs.contracts import BriefKind
from src.apps.briefs.models import AIBrief
from src.core.db.persistence import AsyncRepository


class BriefRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="briefs", repository_name="BriefRepository")

    async def get_by_scope(
        self,
        *,
        brief_kind: BriefKind,
        scope_key: str,
        language: str,
    ) -> AIBrief | None:
        self._log_debug(
            "repo.get_brief_by_scope",
            mode="write",
            brief_kind=brief_kind.value,
            scope_key=scope_key,
            language=language,
        )
        row = await self.session.scalar(
            select(AIBrief)
            .where(
                AIBrief.brief_kind == brief_kind.value,
                AIBrief.scope_key == scope_key,
                AIBrief.language == language,
            )
            .limit(1)
        )
        self._log_debug("repo.get_brief_by_scope.result", mode="write", found=row is not None)
        return row

    async def upsert_brief(
        self,
        *,
        existing: AIBrief | None,
        payload: Mapping[str, Any],
    ) -> AIBrief:
        if existing is None:
            item = AIBrief(**dict(payload))
            self._log_info(
                "repo.add_brief",
                mode="write",
                brief_kind=item.brief_kind,
                scope_key=item.scope_key,
                language=item.language,
            )
            self.session.add(item)
        else:
            item = existing
            self._log_info(
                "repo.update_brief",
                mode="write",
                brief_id=int(item.id),
                brief_kind=item.brief_kind,
                scope_key=item.scope_key,
                language=item.language,
            )
            for key, value in payload.items():
                setattr(item, key, value)
        await self.session.flush()
        await self.session.refresh(item)
        return item


__all__ = ["BriefRepository"]
