from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from src.apps.explanations.models import AIExplanation
from src.apps.signals.models import InvestmentDecision
from src.core.db.uow import SessionUnitOfWork


@pytest.mark.asyncio
async def test_read_decision_explanation_returns_cache_headers(
    api_app_client,
    async_db_session,
    seeded_api_state,
) -> None:
    _app, client = api_app_client
    decision = await async_db_session.scalar(select(InvestmentDecision).order_by(InvestmentDecision.id.asc()).limit(1))
    assert decision is not None
    generated_at = decision.created_at + timedelta(minutes=2)

    async with SessionUnitOfWork(async_db_session) as uow:
        uow.session.add(
            AIExplanation(
                explain_kind="decision",
                subject_id=int(decision.id),
                coin_id=int(decision.coin_id),
                symbol="BTCUSD_EVT",
                timeframe=int(decision.timeframe),
                language="en",
                title="Decision explanation",
                explanation="The stored decision stays aligned with its canonical reason and score.",
                bullets_json=[
                    "Reason text remains the primary machine explanation.",
                    "Confidence and score remain inside the stored snapshot.",
                ],
                refs_json={"subject_id": int(decision.id), "symbol": "BTCUSD_EVT"},
                context_json={"snapshot": {"decision": decision.decision, "reason": decision.reason}},
                provider="local_test",
                model="llama-test",
                prompt_name="explain.decision",
                prompt_version=1,
                subject_updated_at=decision.created_at,
                created_at=generated_at,
                updated_at=generated_at,
            )
        )
        await uow.commit()

    response = await client.get(f"/explanations/decisions/{int(decision.id)}")

    assert response.status_code == 200
    assert response.headers["cache-control"].startswith("public, max-age=")
    assert "etag" in response.headers
    assert "last-modified" in response.headers
    payload = response.json()
    assert payload["explain_kind"] == "decision"
    assert payload["generated_at"] == generated_at.isoformat().replace("+00:00", "Z")
    assert payload["consistency"] == "derived"
    assert payload["freshness_class"] == "near_real_time"
    assert payload["staleness_ms"] == 120000

    not_modified = await client.get(
        f"/explanations/decisions/{int(decision.id)}",
        headers={"If-None-Match": response.headers["etag"]},
    )
    assert not_modified.status_code == 304
