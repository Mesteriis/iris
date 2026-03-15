from __future__ import annotations

from src.apps.notifications.contracts import NotificationHumanizationResult
from src.apps.notifications.services.humanization_service import TEMPLATE_DEGRADED_STRATEGY
from src.apps.notifications.services.notification_service import _notification_storage_fields
from src.core.ai.contracts import AICapability, AIContextFormat, AIValidationStatus
from src.core.ai.telemetry import AIExecutionMetadata
from src.core.i18n import MessageDescriptor


def test_notification_storage_fields_drop_rendered_text_for_descriptor_backed_result() -> None:
    fields = _notification_storage_fields(
        NotificationHumanizationResult(
            title="BTCUSDT: new signal",
            message="IRIS detected the breakout signal for BTCUSDT on 15m.",
            severity="info",
            urgency="medium",
            metadata=_metadata(fallback_used=True, degraded_strategy=TEMPLATE_DEGRADED_STRATEGY),
            title_descriptor=MessageDescriptor(
                key="notification.signal.created.title",
                params={"symbol": "BTCUSDT"},
            ),
            message_descriptor=MessageDescriptor(
                key="notification.signal.created.message",
                params={"symbol": "BTCUSDT", "signal_type": "breakout", "timeframe": 15},
            ),
        ),
        rendered_locale="en",
    )

    assert fields["content_kind"] == "descriptor_bundle"
    assert fields["content_json"] == {
        "version": 1,
        "kind": "descriptor_bundle",
        "title": {"key": "notification.signal.created.title", "params": {"symbol": "BTCUSDT"}},
        "message": {
            "key": "notification.signal.created.message",
            "params": {"symbol": "BTCUSDT", "signal_type": "breakout", "timeframe": 15},
        },
    }


def test_notification_storage_fields_keep_text_for_non_descriptor_result() -> None:
    fields = _notification_storage_fields(
        NotificationHumanizationResult(
            title="ETHUSDT: anomaly detected",
            message="IRIS flagged a volatility anomaly for ETHUSDT.",
            severity="warning",
            urgency="high",
            metadata=_metadata(fallback_used=False, degraded_strategy=None),
        ),
        rendered_locale="en",
    )

    assert fields == {
        "content_kind": "generated_text",
        "content_json": {
            "version": 1,
            "kind": "generated_text",
            "rendered_locale": "en",
            "title": "ETHUSDT: anomaly detected",
            "message": "IRIS flagged a volatility anomaly for ETHUSDT.",
        },
    }


def _metadata(*, fallback_used: bool, degraded_strategy: str | None) -> AIExecutionMetadata:
    return AIExecutionMetadata(
        capability=AICapability.NOTIFICATION_HUMANIZE,
        task="notification_humanize",
        requested_provider=None,
        actual_provider="local_test",
        model="llama-test",
        requested_language=None,
        effective_language="en",
        context_format=AIContextFormat.JSON,
        context_record_count=8,
        context_bytes=256,
        context_token_estimate=64,
        fallback_used=fallback_used,
        degraded_strategy=degraded_strategy,
        latency_ms=21,
        validation_status=AIValidationStatus.VALID,
        prompt_name="notification.signal_created",
        prompt_version=1,
    )
