from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from src.apps.hypothesis_engine.models import AIPrompt
from src.apps.hypothesis_engine.query_services import HypothesisQueryService
from src.apps.hypothesis_engine.services.prompt_service import PromptService
from src.core.db.persistence import PERSISTENCE_LOGGER
from src.core.db.uow import SessionUnitOfWork


@pytest.mark.asyncio
async def test_hypothesis_query_service_returns_immutable_read_models(async_db_session) -> None:
    async_db_session.add(
        AIPrompt(
            name="hypothesis.persistence_contract",
            task="hypothesis_generation",
            version=1,
            is_active=True,
            template="Return JSON only.",
            vars_json={"provider": "heuristic"},
        )
    )
    await async_db_session.commit()

    items = await HypothesisQueryService(async_db_session).list_prompts(name="hypothesis.persistence_contract")

    assert len(items) == 1
    with pytest.raises(FrozenInstanceError):
        items[0].name = "changed"
    with pytest.raises(TypeError):
        items[0].vars_json["provider"] = "other"


@pytest.mark.asyncio
async def test_persistence_logs_cover_hypothesis_query_and_uow(async_db_session, monkeypatch) -> None:
    async_db_session.add(
        AIPrompt(
            name="hypothesis.persistence_logging",
            task="hypothesis_generation",
            version=2,
            is_active=False,
            template="Return strict JSON only.",
            vars_json={"provider": "heuristic"},
        )
    )
    await async_db_session.commit()

    events: list[str] = []

    def _debug(message: str, *args, **kwargs) -> None:
        del args, kwargs
        events.append(message)

    def _log(level: int, message: str, *args, **kwargs) -> None:
        del level, args, kwargs
        events.append(message)

    monkeypatch.setattr(PERSISTENCE_LOGGER, "debug", _debug)
    monkeypatch.setattr(PERSISTENCE_LOGGER, "log", _log)

    async with SessionUnitOfWork(async_db_session) as uow:
        prompts = await PromptService(uow).list_prompts(name="hypothesis.persistence_logging")

    assert len(prompts) == 1
    assert "uow.begin" in events
    assert "query.list_prompts" in events
    assert "uow.rollback_uncommitted" in events
