from datetime import UTC, datetime

import pytest
from iris.apps.integrations.ha.application.services import HABridgeFacade
from iris.apps.integrations.ha.errors import HACommandNotAvailableError, HAInvalidPayloadError
from iris.core.http.operations import OperationEventResponse, OperationStatus, OperationStatusResponse
from iris.core.settings import Settings


def test_ha_command_not_available_error_keeps_structured_error_metadata() -> None:
    error = HACommandNotAvailableError(command="portfolio.sync", mode="ha_addon")

    assert error.code == "command_not_available"
    assert error.message_key == "error.ha.command_not_available"
    assert error.message == "command_not_available (command='portfolio.sync')"
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
    assert error.message_key == "error.ha.invalid_payload"
    assert error.details["expected"] == "supported_timeframe"
    assert error.details["allowed_values"] == ["1h", "4h"]


def test_ha_command_not_available_ack_localizes_from_global_settings() -> None:
    facade = HABridgeFacade(settings=Settings(IRIS_LANGUAGE="ru"))

    payload = facade.command_not_available_ack(request_id="req-1", command="portfolio.sync")

    assert payload["error"]["code"] == "command_not_available"
    assert payload["error"]["message_key"] == "error.ha.command_not_available"
    assert payload["error"]["locale"] == "ru"
    assert payload["error"]["message"] == "Команда 'portfolio.sync' недоступна на текущей стадии HA bridge."


@pytest.mark.asyncio
async def test_ha_operation_update_message_localizes_structured_status_and_event() -> None:
    class FakeOperationStore:
        async def get_status(self, operation_id: str) -> OperationStatusResponse | None:
            assert operation_id == "op-1"
            return OperationStatusResponse(
                operation_id=operation_id,
                operation_type="portfolio.sync",
                status=OperationStatus.FAILED,
                accepted_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),
                error_code="command_not_available",
                error_message_key="error.ha.command_not_available",
                error_message_params={"command": "portfolio.sync"},
            )

        async def get_result(self, operation_id: str):
            assert operation_id == "op-1"
            return

        async def list_events(self, operation_id: str) -> tuple[OperationEventResponse, ...]:
            assert operation_id == "op-1"
            return (
                OperationEventResponse(
                    operation_id=operation_id,
                    operation_type="portfolio.sync",
                    event="running",
                    status=OperationStatus.RUNNING,
                    recorded_at=datetime.now(UTC),
                    message_key="ha.command.executing",
                    message_params={"command": "portfolio.sync"},
                ),
            )

    facade = HABridgeFacade(
        settings=Settings(IRIS_LANGUAGE="ru"),
        operation_store_factory=FakeOperationStore,
    )

    payload = await facade.operation_update_message(operation_id="op-1", command="portfolio.sync")

    assert payload is not None
    assert payload["message"] == "Выполняется команда 'portfolio.sync'."
    assert payload["message_key"] == "ha.command.executing"
    assert payload["message_params"] == {"command": "portfolio.sync"}
    assert payload["locale"] == "ru"
    assert payload["error"]["code"] == "command_not_available"
    assert payload["error"]["message_key"] == "error.ha.command_not_available"
    assert payload["error"]["message"] == "Команда 'portfolio.sync' недоступна на текущей стадии HA bridge."
    assert payload["error"]["locale"] == "ru"
