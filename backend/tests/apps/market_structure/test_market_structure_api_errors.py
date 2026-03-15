# ruff: noqa: RUF001

from __future__ import annotations

from src.apps.market_structure.api.errors import (
    market_structure_ingest_result_to_http,
    market_structure_source_not_found_error,
)
from src.apps.market_structure.services.results import MarketStructureIngestResult


def test_market_structure_api_errors_are_localized_from_registry() -> None:
    source_error = market_structure_source_not_found_error(locale="ru")
    ingest_error = market_structure_ingest_result_to_http(
        MarketStructureIngestResult(
            status="skipped",
            source_id=7,
            reason="plugin_does_not_support_manual_ingest",
        ),
        source_id=7,
        locale="en",
    )

    assert source_error.status_code == 404
    assert source_error.detail["message"] == "Запрошенный ресурс 'market structure source' не найден."

    assert ingest_error is not None
    assert ingest_error.status_code == 400
    assert ingest_error.detail["message_key"] == "errors.generic.invalid_state_transition"
    assert ingest_error.detail["message"] == "The requested operation is not allowed in the current state."
