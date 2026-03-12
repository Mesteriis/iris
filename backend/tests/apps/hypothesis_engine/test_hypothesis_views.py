from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

import src.core.bootstrap.app as bootstrap_app_module
from src.runtime.streams.publisher import flush_publisher, publish_event


@pytest.fixture
async def hypothesis_api_client(monkeypatch):
    monkeypatch.setattr(bootstrap_app_module.settings, "enable_hypothesis_engine", True, raising=False)
    app = bootstrap_app_module.create_app()

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    app.router.lifespan_context = _noop_lifespan
    app.state.taskiq_backfill_event = asyncio.Event()
    app.state.taskiq_worker_processes = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield app, client


@pytest.mark.asyncio
async def test_hypothesis_prompt_endpoints(hypothesis_api_client) -> None:
    _, client = hypothesis_api_client

    assert (await client.get("/hypothesis/prompts")).status_code == 200

    create_response = await client.post(
        "/hypothesis/prompts",
        json={
            "name": "hypothesis.signal_created",
            "task": "hypothesis_generation",
            "version": 4,
            "template": "Return JSON only.",
            "vars_json": {"provider": "heuristic", "model": "rule-based"},
        },
    )
    assert create_response.status_code == 201
    prompt_id = create_response.json()["id"]

    patch_response = await client.patch(
        f"/hypothesis/prompts/{prompt_id}",
        json={"template": "Return strict JSON only.", "vars_json": {"provider": "heuristic", "model": "rule-based-v2"}},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["template"] == "Return strict JSON only."

    activate_response = await client.post(f"/hypothesis/prompts/{prompt_id}/activate")
    assert activate_response.status_code == 200
    assert activate_response.json()["is_active"] is True

    hypotheses_response = await client.get("/hypothesis/hypotheses")
    assert hypotheses_response.status_code == 200
    assert hypotheses_response.json() == []

    evals_response = await client.get("/hypothesis/evals")
    assert evals_response.status_code == 200
    assert evals_response.json() == []


@pytest.mark.asyncio
async def test_hypothesis_sse_endpoint_emits_ai_events(hypothesis_api_client) -> None:
    _, client = hypothesis_api_client

    publish_event(
        "ai_insight",
        {
            "coin_id": 1,
            "timeframe": 60,
            "timestamp": "2026-03-12T12:00:00+00:00",
            "kind": "explain",
            "text": "Momentum context changed.",
            "confidence": 0.7,
            "hypothesis_id": 12,
        },
    )
    assert flush_publisher(timeout=5.0)

    async with client.stream("GET", "/hypothesis/sse/ai?cursor=0-0&once=true") as response:
        assert response.status_code == 200
        lines: list[str] = []
        async for line in response.aiter_lines():
            if line:
                lines.append(line)
            if any(item.startswith("data: ") for item in lines):
                break

    data_line = next(item for item in lines if item.startswith("data: "))
    payload = json.loads(data_line.removeprefix("data: "))
    assert payload["event"] == "ai_insight"
    assert payload["payload"]["hypothesis_id"] == 12
