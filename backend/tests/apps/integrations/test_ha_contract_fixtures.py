import json
from copy import deepcopy
from pathlib import Path

import pytest
from iris.apps.integrations.ha.application.services import HABridgeFacade, RuntimeSnapshot
from iris.apps.integrations.ha.schemas import HAEntityStateRead

_FIXTURES_ROOT = (
    Path(__file__).resolve().parents[4] / "ha" / "integration" / "tests" / "fixtures" / "contract"
)


def test_backend_bootstrap_catalog_and_dashboard_match_shared_contract_fixtures() -> None:
    facade = HABridgeFacade()

    assert facade.bootstrap().model_dump(mode="json") == _load_fixture("bootstrap.json")
    assert facade.catalog().model_dump(mode="json") == _load_fixture("catalog.json")
    assert facade.dashboard().model_dump(mode="json") == _load_fixture("dashboard.json")


@pytest.mark.asyncio
async def test_backend_state_snapshot_matches_shared_contract_fixture_sample() -> None:
    facade = HABridgeFacade()
    fixture = _load_fixture("state.json")
    facade._projected_runtime = RuntimeSnapshot(
        entities={
            entity_key: HAEntityStateRead.model_validate(payload)
            for entity_key, payload in fixture["entities"].items()
        },
        collections=deepcopy(fixture["collections"]),
    )
    facade.projection_clock._epoch = fixture["projection_epoch"]
    facade.projection_clock._sequence = fixture["sequence"]

    assert (await facade.state_snapshot()).model_dump(mode="json") == fixture


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES_ROOT / name).read_text(encoding="utf-8"))
