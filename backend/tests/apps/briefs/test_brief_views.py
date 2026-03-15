from __future__ import annotations

from datetime import timedelta

import pytest
from src.apps.briefs.models import AIBrief
from src.core.db.uow import SessionUnitOfWork


@pytest.mark.asyncio
async def test_read_market_brief_returns_cache_headers(
    api_app_client,
    async_db_session,
    seeded_api_state,
) -> None:
    _app, client = api_app_client
    source_updated_at = seeded_api_state["signal_timestamp"]
    generated_at = source_updated_at + timedelta(minutes=3)

    async with SessionUnitOfWork(async_db_session) as uow:
        uow.session.add(
            AIBrief(
                brief_kind="market",
                scope_key="market",
                symbol=None,
                coin_id=None,
                content_kind="generated_text",
                content_json={
                    "version": 1,
                    "kind": "generated_text",
                    "rendered_locale": "en",
                    "title": "Market brief",
                    "summary": "Leaders remain constructive while breadth stays selective.",
                    "bullets": [
                        "BTCUSD_EVT holds the strongest confidence profile.",
                        "Broader breadth remains narrower than the headline momentum.",
                    ],
                },
                refs_json={"scope": "market", "top_symbols": ["BTCUSD_EVT", "ETHUSD_EVT"]},
                context_json={"snapshot": {"rows": [{"symbol": "BTCUSD_EVT", "decision": "BUY"}]}},
                provider="local_test",
                model="llama-test",
                prompt_name="brief.market",
                prompt_version=1,
                source_updated_at=source_updated_at,
                created_at=generated_at,
                updated_at=generated_at,
            )
        )
        await uow.commit()

    response = await client.get("/briefs/market")

    assert response.status_code == 200
    assert response.headers["cache-control"].startswith("private, max-age=")
    assert "etag" in response.headers
    assert "last-modified" in response.headers
    payload = response.json()
    assert payload["brief_kind"] == "market"
    assert payload["title"] == "Market brief"
    assert payload["summary"] == "Leaders remain constructive while breadth stays selective."
    assert payload["content_kind"] == "generated_text"
    assert payload["rendered_locale"] == "en"
    assert payload["generated_at"] == generated_at.isoformat().replace("+00:00", "Z")
    assert payload["consistency"] == "derived"
    assert payload["freshness_class"] == "near_real_time"
    assert payload["staleness_ms"] == 180000

    not_modified = await client.get("/briefs/market", headers={"If-None-Match": response.headers["etag"]})
    assert not_modified.status_code == 304
