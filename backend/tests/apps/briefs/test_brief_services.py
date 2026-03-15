from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from src.apps.briefs.contracts import BriefArtifactResult, BriefGenerationStatus, BriefKind
from src.apps.briefs.models import AIBrief
from src.apps.briefs.services import BriefService
from src.core.ai.contracts import AICapability, AIContextFormat, AIValidationStatus
from src.core.ai.telemetry import AIExecutionMetadata
from src.core.db.uow import SessionUnitOfWork


@pytest.mark.asyncio
async def test_brief_service_persists_symbol_artifact(async_db_session, seeded_api_state, monkeypatch) -> None:
    generate = AsyncMock(
        return_value=BriefArtifactResult(
            title="BTCUSD_EVT snapshot",
            summary="BTCUSD_EVT keeps a buy-biased snapshot across tracked timeframes.",
            bullets=(
                "Higher-priority timeframe stays constructive.",
                "Confidence remains strongest on the shortest tracked frame.",
            ),
            metadata=AIExecutionMetadata(
                capability=AICapability.BRIEF_GENERATE,
                task="brief_generate",
                requested_provider=None,
                actual_provider="local_test",
                model="llama-test",
                requested_language="ru",
                effective_language="ru",
                context_format=AIContextFormat.COMPACT_JSON,
                context_record_count=4,
                context_bytes=512,
                context_token_estimate=128,
                fallback_used=False,
                degraded_strategy=None,
                latency_ms=18,
                validation_status=AIValidationStatus.VALID,
                prompt_name="brief.symbol",
                prompt_version=1,
            ),
        )
    )
    monkeypatch.setattr("src.apps.briefs.services.brief_service.BriefGenerationService.generate", generate)

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await BriefService(uow).generate_and_store(
            brief_kind=BriefKind.SYMBOL,
            symbol="BTCUSD_EVT",
            language="ru",
        )
        await uow.commit()

    stored = await async_db_session.scalar(select(AIBrief).where(AIBrief.id == int(result.brief_id)))
    assert stored is not None
    assert stored.brief_kind == "symbol"
    assert stored.scope_key == "symbol:BTCUSD_EVT"
    assert stored.language == "ru"
    assert stored.title == "BTCUSD_EVT snapshot"
    assert stored.context_json["ai_execution"]["context_format"] == "compact_json"
    assert stored.refs_json["symbol"] == "BTCUSD_EVT"
    assert result.status is BriefGenerationStatus.OK


@pytest.mark.asyncio
async def test_brief_service_skips_when_snapshot_is_current(async_db_session, seeded_api_state, monkeypatch) -> None:
    generate = AsyncMock(
        return_value=BriefArtifactResult(
            title="Portfolio posture",
            summary="The portfolio remains lightly allocated with one active position.",
            bullets=(
                "Capital stays mostly unallocated.",
                "Open exposure is concentrated in a single BTC position.",
            ),
            metadata=AIExecutionMetadata(
                capability=AICapability.BRIEF_GENERATE,
                task="brief_generate",
                requested_provider=None,
                actual_provider="local_test",
                model="llama-test",
                requested_language=None,
                effective_language="en",
                context_format=AIContextFormat.TOON,
                context_record_count=1,
                context_bytes=320,
                context_token_estimate=80,
                fallback_used=False,
                degraded_strategy=None,
                latency_ms=12,
                validation_status=AIValidationStatus.VALID,
                prompt_name="brief.portfolio",
                prompt_version=1,
            ),
        )
    )
    monkeypatch.setattr("src.apps.briefs.services.brief_service.BriefGenerationService.generate", generate)

    async with SessionUnitOfWork(async_db_session) as uow:
        first = await BriefService(uow).generate_and_store(brief_kind=BriefKind.PORTFOLIO)
        await uow.commit()

    async with SessionUnitOfWork(async_db_session) as uow:
        second = await BriefService(uow).generate_and_store(brief_kind=BriefKind.PORTFOLIO)
        await uow.commit()

    rows = (
        await async_db_session.execute(
            select(AIBrief).where(
                AIBrief.brief_kind == "portfolio",
                AIBrief.scope_key == "portfolio",
                AIBrief.language == "en",
            )
        )
    ).scalars().all()
    assert first.status is BriefGenerationStatus.OK
    assert second.status is BriefGenerationStatus.SKIPPED
    assert second.reason == "brief_already_current"
    assert second.brief_id == first.brief_id
    assert len(rows) == 1
    assert generate.await_count == 1
