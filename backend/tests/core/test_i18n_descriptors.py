from __future__ import annotations

from src.core.i18n import (
    MessageDescriptor,
    dump_message_descriptor,
    dump_message_descriptors,
    load_message_descriptor,
    load_message_descriptors,
    localize_message_descriptor,
)


def test_message_descriptor_roundtrip_preserves_key_and_params() -> None:
    descriptor = MessageDescriptor(
        key="notification.signal.created.message",
        params={"symbol": "BTCUSDT", "signal_type": "breakout", "timeframe": 15},
    )

    payload = dump_message_descriptor(descriptor)
    loaded = load_message_descriptor(payload)

    assert loaded == descriptor


def test_message_descriptor_collection_roundtrip_preserves_order() -> None:
    descriptors = (
        MessageDescriptor(key="brief.explanation.signal.bullet.priority", params={"priority_score": 0.91}),
        MessageDescriptor(key="brief.explanation.signal.bullet.context", params={"context_score": 0.74, "regime_alignment": 0.63}),
    )

    payload = dump_message_descriptors(descriptors)
    loaded = load_message_descriptors(payload)

    assert loaded == descriptors


def test_localize_message_descriptor_uses_requested_locale() -> None:
    descriptor = MessageDescriptor(
        key="notification.signal.created.title",
        params={"symbol": "BTCUSDT"},
    )

    text, locale = localize_message_descriptor(descriptor, locale="ru")

    assert text == "BTCUSDT: новый сигнал"
    assert locale == "ru"
