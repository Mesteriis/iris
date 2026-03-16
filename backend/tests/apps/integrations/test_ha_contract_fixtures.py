import json
from copy import deepcopy
from pathlib import Path

import pytest
from src.apps.integrations.ha.application.services import HABridgeService, RuntimeSnapshot
from src.apps.integrations.ha.schemas import HAEntityStateRead

_FIXTURES_ROOT = (
    Path(__file__).resolve().parents[4] / "ha" / "integration" / "tests" / "fixtures" / "contract"
)


def test_backend_bootstrap_catalog_and_dashboard_match_shared_contract_fixtures() -> None:
    service = HABridgeService()

    assert service.bootstrap().model_dump(mode="json") == _load_fixture("bootstrap.json")
    assert service.catalog().model_dump(mode="json") == _load_fixture("catalog.json")
    assert service.dashboard().model_dump(mode="json") == _load_fixture("dashboard.json")


@pytest.mark.asyncio
async def test_backend_state_snapshot_matches_shared_contract_fixture_sample() -> None:
    service = HABridgeService()
    fixture = _load_fixture("state.json")
    service._projected_runtime = RuntimeSnapshot(
        entities={
            entity_key: HAEntityStateRead.model_validate(payload)
            for entity_key, payload in fixture["entities"].items()
        },
        collections=deepcopy(fixture["collections"]),
    )
    service.projection_clock._epoch = fixture["projection_epoch"]
    service.projection_clock._sequence = fixture["sequence"]

    assert (await service.state_snapshot()).model_dump(mode="json") == fixture


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES_ROOT / name).read_text(encoding="utf-8"))
