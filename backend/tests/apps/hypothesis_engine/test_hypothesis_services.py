from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select
from src.apps.hypothesis_engine.models import AIHypothesis, AIHypothesisEval, AIPrompt, AIWeight
from src.apps.hypothesis_engine.prompts import PromptLoader
from src.apps.hypothesis_engine.providers import LocalHTTPProvider, OpenAILikeProvider
from src.apps.hypothesis_engine.query_services import HypothesisQueryService
from src.apps.hypothesis_engine.services.weight_update_service import WeightUpdateService, posterior_mean
from src.apps.market_data.domain import utc_now
from src.core.db.uow import SessionUnitOfWork


@pytest.mark.asyncio
async def test_prompt_loader_uses_db_cache_and_invalidation(async_db_session, redis_client) -> None:
    prompt = AIPrompt(
        name="hypothesis.signal_created",
        task="hypothesis_generation",
        version=3,
        is_active=True,
        template="signal prompt v3",
        vars_json={"horizon_min": 180, "style_profile": "concise"},
    )
    async_db_session.add(prompt)
    await async_db_session.commit()

    loader = PromptLoader(HypothesisQueryService(async_db_session))
    loaded = await loader.load("hypothesis.signal_created")
    assert loaded.template == "signal prompt v3"
    assert redis_client.get("iris:ai:prompt:hypothesis.signal_created:active") is not None

    prompt.template = "signal prompt v4"
    await async_db_session.commit()

    cached = await loader.load("hypothesis.signal_created")
    assert cached.template == "signal prompt v3"

    await loader.invalidate("hypothesis.signal_created")
    refreshed = await loader.load("hypothesis.signal_created")
    assert refreshed.template == "signal prompt v4"


@pytest.mark.asyncio
async def test_openai_like_provider_parses_json(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"type":"sector_outperf","confidence":0.72,"horizon_min":180,"direction":"up","target_move":0.02,"summary":"AI sector strength","assets":["RNDR"]}'
                        }
                    }
                ]
            }

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def post(self, url: str, *, json: dict[str, object], headers: dict[str, str]):
            assert url.endswith("/chat/completions")
            assert json["model"] == "gpt-test"
            assert "Authorization" in headers
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    provider = OpenAILikeProvider(model="gpt-test", base_url="https://llm.example/v1", api_key="token")

    payload = await provider.json_chat("prompt", vars={"symbol": "RNDR"}, schema={"type": "object"})

    assert payload["type"] == "sector_outperf"
    assert payload["assets"] == ["RNDR"]


@pytest.mark.asyncio
async def test_local_http_provider_parses_json(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "response": '{"type":"mean_reversion","confidence":0.61,"horizon_min":60,"direction":"down","target_move":0.01,"summary":"Exhaustion","assets":["ETH"]}'
            }

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def post(self, url: str, *, json: dict[str, object], headers: dict[str, str]):
            assert url.endswith("/api/generate")
            assert json["model"] == "local-model"
            assert headers["Content-Type"] == "application/json"
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    provider = LocalHTTPProvider(model="local-model", base_url="http://localhost:11434")

    payload = await provider.json_chat("prompt", vars={"symbol": "ETH"}, schema={"type": "object"})

    assert payload["type"] == "mean_reversion"
    assert payload["assets"] == ["ETH"]


@pytest.mark.asyncio
async def test_weight_update_service_applies_decayed_bayes(async_db_session, seeded_market, monkeypatch) -> None:
    coin_id = int(seeded_market["ETHUSD_EVT"]["coin_id"])
    now = utc_now()
    hypothesis = AIHypothesis(
        coin_id=coin_id,
        timeframe=15,
        status="active",
        hypothesis_type="signal_follow_through",
        statement_json={"direction": "up", "target_move": 0.01},
        confidence=0.7,
        horizon_min=60,
        eval_due_at=now + timedelta(minutes=60),
        context_json={"trigger_timestamp": now.isoformat()},
        provider="heuristic",
        model="rule-based",
        prompt_name="hypothesis.signal_created",
        prompt_version=1,
        source_event_type="signal_created",
        source_stream_id="1-0",
    )
    async_db_session.add(hypothesis)
    await async_db_session.flush()
    evaluation = AIHypothesisEval(
        hypothesis_id=int(hypothesis.id),
        success=True,
        score=0.88,
        details_json={"realized_return": 0.021},
        evaluated_at=now,
    )
    async_db_session.add(evaluation)
    await async_db_session.commit()

    published: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr("src.apps.hypothesis_engine.services.weight_update_service.publish_event", lambda event_type, payload: published.append((event_type, payload)))

    async with SessionUnitOfWork(async_db_session) as uow:
        await WeightUpdateService(uow).apply(int(evaluation.id))
        await uow.commit()

    weight = await async_db_session.scalar(
        select(AIWeight).where(AIWeight.scope == "hypothesis_type", AIWeight.weight_key == "signal_follow_through")
    )
    assert weight is not None
    assert round(float(weight.alpha), 2) == 1.98
    assert round(float(weight.beta), 2) == 0.98
    assert posterior_mean(float(weight.alpha), float(weight.beta)) > 0.66
    assert published[-1][0] == "ai_weights_updated"
