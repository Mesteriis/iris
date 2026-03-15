from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.core.http.operation_store import OperationDispatchResult
from src.core.http.operations import OperationEventResponse, OperationResultResponse, OperationStatusResponse
from src.core.i18n import get_translation_service


def dispatch_result_message_fields(
    dispatch_result: OperationDispatchResult,
    *,
    locale: str | None = None,
) -> dict[str, object]:
    message, localized_locale = _localize_message(
        message_key=dispatch_result.message_key,
        message_params=dispatch_result.message_params,
        locale=locale,
    )
    return {
        "message": message,
        "message_key": dispatch_result.message_key,
        "message_params": dict(dispatch_result.message_params or {}),
        "locale": localized_locale,
    }


def localize_operation_status(
    item: OperationStatusResponse | Mapping[str, Any],
    *,
    locale: str | None = None,
) -> OperationStatusResponse:
    payload = _to_payload(item)
    message, localized_locale = _localize_message(
        message_key=payload.get("error_message_key"),
        message_params=payload.get("error_message_params"),
        locale=locale,
    )
    if message is not None:
        payload["error_message"] = message
        payload["error_locale"] = localized_locale
    return OperationStatusResponse.model_validate(payload)


def localize_operation_result(
    item: OperationResultResponse | Mapping[str, Any],
    *,
    locale: str | None = None,
) -> OperationResultResponse:
    payload = localize_operation_status(item, locale=locale).model_dump(mode="python")
    return OperationResultResponse.model_validate(payload)


def localize_operation_event(
    item: OperationEventResponse | Mapping[str, Any],
    *,
    locale: str | None = None,
) -> OperationEventResponse:
    payload = _to_payload(item)
    message, localized_locale = _localize_message(
        message_key=payload.get("message_key"),
        message_params=payload.get("message_params"),
        locale=locale,
    )
    if message is not None:
        payload["message"] = message
        payload["locale"] = localized_locale
    return OperationEventResponse.model_validate(payload)


def _localize_message(
    *,
    message_key: str | None,
    message_params: Mapping[str, object] | None,
    locale: str | None,
) -> tuple[str | None, str | None]:
    if message_key is None:
        return None, None
    localized = get_translation_service().translate(
        message_key,
        locale=locale,
        params=dict(message_params or {}),
    )
    return localized.text, localized.locale


def _to_payload(item: OperationStatusResponse | OperationResultResponse | OperationEventResponse | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(item, Mapping):
        return dict(item)
    return item.model_dump(mode="python")
