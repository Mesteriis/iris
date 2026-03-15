from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from src.apps.explanations.contracts import ExplainKind, ExplanationGenerationStatus
from src.apps.explanations.models import AIExplanation
from src.apps.explanations.services import ExplanationService
from src.apps.signals.models import InvestmentDecision, Signal
from src.core.db.uow import SessionUnitOfWork


@pytest.mark.asyncio
async def test_explanation_service_persists_signal_artifact(async_db_session, seeded_api_state, monkeypatch) -> None:
    signal = await async_db_session.scalar(select(Signal).order_by(Signal.id.asc()).limit(1))
    assert signal is not None

    generate = AsyncMock(
        return_value={
            "title": "BTCUSD_EVT signal explanation",
            "explanation": "The signal remains a canonical observation with elevated contextual confidence.",
            "bullets": [
                "Priority remains above the baseline threshold.",
                "Cluster context confirms related structural patterns.",
            ],
            "provider": "local_test",
            "requested_provider": None,
            "model": "llama-test",
            "requested_language": "en",
            "effective_language": "en",
            "context_format": "compact_json",
            "context_record_count": 10,
            "context_bytes": 540,
            "context_token_estimate": 135,
            "fallback_used": False,
            "degraded_strategy": None,
            "latency_ms": 15,
            "validation_status": "valid",
            "prompt_name": "explain.signal",
            "prompt_version": 1,
        }
    )
    monkeypatch.setattr(
        "src.apps.explanations.services.explanation_service.ExplanationGenerationService.generate",
        generate,
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await ExplanationService(uow).generate_and_store(
            explain_kind=ExplainKind.SIGNAL,
            subject_id=int(signal.id),
            language="en",
        )
        await uow.commit()

    stored = await async_db_session.scalar(select(AIExplanation).where(AIExplanation.id == int(result.explanation_id)))
    assert stored is not None
    assert stored.explain_kind == "signal"
    assert stored.subject_id == int(signal.id)
    assert stored.language == "en"
    assert stored.context_json["ai_execution"]["context_format"] == "compact_json"
    assert stored.refs_json["subject_id"] == int(signal.id)
    assert result.status is ExplanationGenerationStatus.OK


@pytest.mark.asyncio
async def test_explanation_service_skips_when_decision_snapshot_is_current(async_db_session, seeded_api_state, monkeypatch) -> None:
    decision = await async_db_session.scalar(select(InvestmentDecision).order_by(InvestmentDecision.id.asc()).limit(1))
    assert decision is not None

    generate = AsyncMock(
        return_value={
            "title": "BTCUSD_EVT decision explanation",
            "explanation": "The decision snapshot stays aligned with the stored machine reason.",
            "bullets": [
                "Confidence remains stable relative to the stored score.",
                "The reason field still drives the canonical explanation.",
            ],
            "provider": "local_test",
            "requested_provider": None,
            "model": "llama-test",
            "requested_language": None,
            "effective_language": "en",
            "context_format": "compact_json",
            "context_record_count": 8,
            "context_bytes": 420,
            "context_token_estimate": 105,
            "fallback_used": False,
            "degraded_strategy": None,
            "latency_ms": 11,
            "validation_status": "valid",
            "prompt_name": "explain.decision",
            "prompt_version": 1,
        }
    )
    monkeypatch.setattr(
        "src.apps.explanations.services.explanation_service.ExplanationGenerationService.generate",
        generate,
    )

    async with SessionUnitOfWork(async_db_session) as uow:
        first = await ExplanationService(uow).generate_and_store(
            explain_kind=ExplainKind.DECISION,
            subject_id=int(decision.id),
        )
        await uow.commit()

    async with SessionUnitOfWork(async_db_session) as uow:
        second = await ExplanationService(uow).generate_and_store(
            explain_kind=ExplainKind.DECISION,
            subject_id=int(decision.id),
        )
        await uow.commit()

    rows = (
        await async_db_session.execute(
            select(AIExplanation).where(
                AIExplanation.explain_kind == "decision",
                AIExplanation.subject_id == int(decision.id),
                AIExplanation.language == "en",
            )
        )
    ).scalars().all()
    assert first.status is ExplanationGenerationStatus.OK
    assert second.status is ExplanationGenerationStatus.SKIPPED
    assert second.reason == "explanation_already_current"
    assert len(rows) == 1
    assert generate.await_count == 1
