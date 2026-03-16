from datetime import UTC, datetime

from src.core.http.operation_localization import dispatch_result_message_fields, localize_operation_status
from src.core.http.operation_store import OperationDispatchResult
from src.core.http.operations import OperationStatus, OperationStatusResponse


def test_dispatch_result_message_fields_localize_structured_message() -> None:
    dispatch_result = OperationDispatchResult(
        operation=OperationStatusResponse(
            operation_id="op-1",
            operation_type="market_data.coin_history.sync",
            status=OperationStatus.QUEUED,
            accepted_at=datetime.now(UTC),
        ),
        deduplicated=True,
        message_key="system.operation.already_active",
    )

    payload = dispatch_result_message_fields(dispatch_result, locale="ru")

    assert payload == {
        "message": "Эквивалентная операция уже выполняется.",
        "message_key": "system.operation.already_active",
        "message_params": {},
        "locale": "ru",
    }


def test_localize_operation_status_renders_structured_error_on_read() -> None:
    status = OperationStatusResponse(
        operation_id="op-2",
        operation_type="portfolio.sync",
        status=OperationStatus.FAILED,
        accepted_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        error_code="command_not_available",
        error_message_key="error.ha.command_not_available",
        error_message_params={"command": "portfolio.sync"},
    )

    localized = localize_operation_status(status, locale="ru")

    assert localized.error_message == "Команда 'portfolio.sync' недоступна на текущей стадии HA bridge."
    assert localized.error_message_key == "error.ha.command_not_available"
    assert localized.error_message_params == {"command": "portfolio.sync"}
    assert localized.error_locale == "ru"


def test_localize_operation_status_preserves_legacy_text_without_message_key() -> None:
    status = OperationStatusResponse(
        operation_id="op-3",
        operation_type="portfolio.sync",
        status=OperationStatus.FAILED,
        accepted_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        error_code="legacy_error",
        error_message="Legacy operation failure",
    )

    localized = localize_operation_status(status, locale="ru")

    assert localized.error_message == "Legacy operation failure"
    assert localized.error_message_key is None
    assert localized.error_locale is None
