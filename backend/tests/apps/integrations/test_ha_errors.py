from __future__ import annotations

from src.apps.integrations.ha.errors import HACommandNotAvailableError, HAInvalidPayloadError


def test_ha_command_not_available_error_uses_registry_backed_translation() -> None:
    error = HACommandNotAvailableError(command="portfolio.sync", mode="ha_addon")

    assert error.code == "command_not_available"
    assert error.message == "Command 'portfolio.sync' is not available for the current HA bridge stage."
    assert error.details == {"command": "portfolio.sync", "mode": "ha_addon"}


def test_ha_invalid_payload_error_tracks_machine_readable_details() -> None:
    error = HAInvalidPayloadError(
        command="settings.default_timeframe.set",
        payload={"value": "2h"},
        expected="supported_timeframe",
        allowed_values=("1h", "4h"),
        locale="ru",
    )

    assert error.code == "invalid_payload"
    assert error.message == "Команда 'settings.default_timeframe.set' получила некорректный payload."
    assert error.details["expected"] == "supported_timeframe"
    assert error.details["allowed_values"] == ["1h", "4h"]
