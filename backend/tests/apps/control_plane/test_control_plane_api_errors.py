# ruff: noqa: RUF001

from __future__ import annotations

from src.apps.control_plane.api.errors import control_plane_error_to_http, invalid_access_mode_error
from src.apps.control_plane.exceptions import TopologyDraftConcurrencyConflict


def test_control_plane_boundary_errors_are_localized() -> None:
    access_mode_error = invalid_access_mode_error(locale="ru", value="broken")
    conflict_error = control_plane_error_to_http(
        TopologyDraftConcurrencyConflict(7, expected_version=4, current_version=5),
        locale="ru",
    )

    assert access_mode_error.status_code == 400
    assert access_mode_error.detail["message_key"] == "errors.control_plane.invalid_access_mode"
    assert access_mode_error.detail["details"][0]["message_key"] == "errors.control_plane.detail.allowed_access_modes"
    assert access_mode_error.detail["details"][0]["locale"] == "ru"

    assert conflict_error is not None
    assert conflict_error.status_code == 409
    assert conflict_error.detail["message_key"] == "errors.generic.concurrency_conflict"
    assert conflict_error.detail["details"][0]["message"] == "Идентификатор draft."
    assert conflict_error.detail["details"][1]["message_key"] == "errors.control_plane.detail.expected_version"
    assert conflict_error.detail["details"][2]["value"] == 5
