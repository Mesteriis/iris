from __future__ import annotations

import asyncio
import importlib.util
import json
from contextlib import asynccontextmanager

import pytest
import src.core.bootstrap.app as bootstrap_app_module
from httpx import ASGITransport, AsyncClient
from src.apps.hypothesis_engine.api.router import build_router as build_hypothesis_router
from src.core.http.launch_modes import DeploymentProfile, LaunchMode
from src.runtime.streams.publisher import flush_publisher, publish_event

from tests.apps.conftest import PrefixedAsyncClient


@pytest.fixture
async def hypothesis_api_client(monkeypatch):
    monkeypatch.setattr(
        bootstrap_app_module.settings,
        "ai_providers",
        [
            {
                "name": "local_test",
                "kind": "local_http",
                "enabled": True,
                "base_url": "http://127.0.0.1:9",
                "endpoint": "/api/generate",
                "model": "llama-test",
                "timeout_seconds": 0.05,
                "priority": 100,
                "capabilities": ["hypothesis_generate"],
            }
        ],
        raising=False,
    )
    app = bootstrap_app_module.create_app()

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    app.router.lifespan_context = _noop_lifespan
    app.state.taskiq_backfill_event = asyncio.Event()
    app.state.taskiq_worker_processes = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield app, PrefixedAsyncClient(client)


@pytest.mark.asyncio
async def test_hypothesis_prompt_endpoints(hypothesis_api_client, monkeypatch) -> None:
    _, client = hypothesis_api_client
    control_headers = {
        "X-IRIS-Actor": "ops",
        "X-IRIS-Access-Mode": "control",
        "X-IRIS-Reason": "hypothesis-prompt-test",
    }

    queued: list[dict[str, object]] = []

    from src.apps.hypothesis_engine.tasks.hypothesis_tasks import evaluate_hypotheses_job

    async def fake_kiq(**kwargs) -> None:
        queued.append(dict(kwargs))

    monkeypatch.setattr(evaluate_hypotheses_job, "kiq", fake_kiq)

    prompt_catalog_response = await client.get("/control-plane/ai/prompts")
    assert prompt_catalog_response.status_code == 200
    assert any(row["name"] == "brief.market" for row in prompt_catalog_response.json())

    create_response = await client.post(
        "/control-plane/ai/prompts",
        json={
            "name": "hypothesis.signal_created",
            "task": "hypothesis_generation",
            "version": 4,
            "template": "Return JSON only.",
            "vars_json": {"horizon_min": 90, "style_profile": "concise"},
        },
        headers=control_headers,
    )
    assert create_response.status_code == 201
    assert create_response.json()["capability"] == "hypothesis_generate"
    prompt_id = create_response.json()["id"]

    patch_response = await client.patch(
        f"/control-plane/ai/prompts/{prompt_id}",
        json={"template": "Return strict JSON only.", "vars_json": {"target_move": 0.03, "style_profile": "strict"}},
        headers=control_headers,
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["template"] == "Return strict JSON only."
    assert patch_response.json()["style_profile"] == "strict"

    activate_response = await client.post(
        f"/control-plane/ai/prompts/{prompt_id}/activate",
        headers=control_headers,
    )
    assert activate_response.status_code == 200
    assert activate_response.json()["is_active"] is True

    hypotheses_response = await client.get("/hypothesis/hypotheses")
    assert hypotheses_response.status_code == 200
    assert hypotheses_response.json() == []

    evals_response = await client.get("/hypothesis/evals")
    assert evals_response.status_code == 200
    assert evals_response.json() == []

    job_response = await client.post("/hypothesis/jobs/evaluate")
    assert job_response.status_code == 202
    payload = job_response.json()
    assert payload["status"] == "accepted"
    assert payload["operation_type"] == "hypothesis.evaluate"
    assert payload["deduplicated"] is False
    assert isinstance(payload["operation_id"], str) and payload["operation_id"]
    assert queued == [{"operation_id": payload["operation_id"]}]

    deduplicated_job_response = await client.post("/hypothesis/jobs/evaluate")
    assert deduplicated_job_response.status_code == 202
    deduplicated_payload = deduplicated_job_response.json()
    assert deduplicated_payload["operation_id"] == payload["operation_id"]
    assert deduplicated_payload["deduplicated"] is True
    assert deduplicated_payload["message"] == "An equivalent operation is already active."
    assert queued == [{"operation_id": payload["operation_id"]}]


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


def test_hypothesis_api_router_is_mode_aware_and_legacy_views_removed() -> None:
    provider_settings = bootstrap_app_module.settings.model_copy(
        update={
            "ai_providers": [
                {
                    "name": "local_test",
                    "kind": "local_http",
                    "enabled": True,
                    "base_url": "http://127.0.0.1:9",
                    "endpoint": "/api/generate",
                    "model": "llama-test",
                    "timeout_seconds": 0.05,
                    "priority": 100,
                    "capabilities": ["hypothesis_generate"],
                }
            ]
        }
    )
    full_router = build_hypothesis_router(
        mode=LaunchMode.FULL,
        profile=DeploymentProfile.PLATFORM_FULL,
        settings=provider_settings,
    )
    ha_router = build_hypothesis_router(
        mode=LaunchMode.HA_ADDON,
        profile=DeploymentProfile.HA_EMBEDDED,
        settings=provider_settings.model_copy(update={"api_launch_mode": "ha_addon", "api_deployment_profile": ""}),
    )

    full_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in full_router.routes}
    ha_paths = {(route.path, tuple(sorted(route.methods or ()))) for route in ha_router.routes}

    assert any(path == "/hypothesis/jobs/evaluate" and "POST" in methods for path, methods in full_paths)
    assert any(path == "/hypothesis/sse/ai" and "GET" in methods for path, methods in full_paths)
    assert not any(path == "/hypothesis/prompts" for path, _ in full_paths)
    assert not any(path == "/hypothesis/jobs/evaluate" for path, _ in ha_paths)
    assert not any(path == "/hypothesis/sse/ai" for path, _ in ha_paths)
    assert not any(path == "/hypothesis/prompts" for path, _ in ha_paths)
    assert importlib.util.find_spec("src.apps.hypothesis_engine.views") is None
