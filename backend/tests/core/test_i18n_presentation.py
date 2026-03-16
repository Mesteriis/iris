import pytest
from iris.core.i18n import (
    CONTENT_KIND_DESCRIPTOR_BUNDLE,
    CONTENT_KIND_GENERATED_TEXT,
    ContentPayloadValidationError,
    build_descriptor_bundle_content,
    build_generated_text_content,
    content_descriptor,
    content_descriptors,
    content_kind,
    content_rendered_locale,
    content_text,
    content_text_list,
    validate_content_payload,
)
from iris.core.i18n.contracts import MessageDescriptor


def test_build_descriptor_bundle_content_round_trips_descriptors() -> None:
    payload = build_descriptor_bundle_content(
        fields={
            "title": MessageDescriptor(key="notification.signal.created.title", params={"symbol": "BTCUSDT"}),
            "bullets": (
                MessageDescriptor(key="brief.explanation.signal.bullet.priority", params={"priority_score": 0.91}),
            ),
        }
    )

    assert content_kind(payload) == CONTENT_KIND_DESCRIPTOR_BUNDLE
    assert content_descriptor(payload, "title") == MessageDescriptor(
        key="notification.signal.created.title",
        params={"symbol": "BTCUSDT"},
    )
    assert content_descriptors(payload, "bullets") == (
        MessageDescriptor(key="brief.explanation.signal.bullet.priority", params={"priority_score": 0.91}),
    )


def test_build_generated_text_content_round_trips_text_fields() -> None:
    payload = build_generated_text_content(
        rendered_locale="en",
        fields={
            "title": "ETHUSDT: anomaly detected",
            "message": "IRIS flagged a volatility anomaly for ETHUSDT.",
            "bullets": ("Machine reason missing.", "Confidence snapshot stored."),
        },
    )

    assert content_kind(payload) == CONTENT_KIND_GENERATED_TEXT
    assert content_rendered_locale(payload) == "en"
    assert content_text(payload, "title") == "ETHUSDT: anomaly detected"
    assert content_text(payload, "message") == "IRIS flagged a volatility anomaly for ETHUSDT."
    assert content_text_list(payload, "bullets") == [
        "Machine reason missing.",
        "Confidence snapshot stored.",
    ]


def test_validate_content_payload_rejects_generated_text_without_locale() -> None:
    with pytest.raises(ContentPayloadValidationError):
        validate_content_payload(
            {
                "version": 1,
                "kind": "generated_text",
                "title": "ETHUSDT: anomaly detected",
            }
        )


def test_validate_content_payload_rejects_invalid_descriptor_field() -> None:
    with pytest.raises(ContentPayloadValidationError):
        validate_content_payload(
            {
                "version": 1,
                "kind": "descriptor_bundle",
                "title": {"params": {"symbol": "BTCUSDT"}},
            }
        )
