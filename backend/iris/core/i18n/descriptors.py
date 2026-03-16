from collections.abc import Mapping, Sequence
from typing import Any

from iris.core.i18n.contracts import MessageDescriptor
from iris.core.i18n.translator import get_translation_service


def dump_message_descriptor(descriptor: MessageDescriptor | None) -> dict[str, object] | None:
    if descriptor is None:
        return None
    return {
        "key": descriptor.key,
        "params": {str(key): value for key, value in descriptor.params.items()},
    }


def load_message_descriptor(payload: object) -> MessageDescriptor | None:
    if not isinstance(payload, Mapping):
        return None
    key = payload.get("key")
    params = payload.get("params")
    if not isinstance(key, str) or not key.strip():
        return None
    return MessageDescriptor(
        key=key,
        params=_normalize_params(params),
    )


def dump_message_descriptors(items: Sequence[MessageDescriptor]) -> list[dict[str, object]]:
    descriptors: list[dict[str, object]] = []
    for item in items:
        payload = dump_message_descriptor(item)
        if payload is not None:
            descriptors.append(payload)
    return descriptors


def load_message_descriptors(payload: object) -> tuple[MessageDescriptor, ...]:
    if not isinstance(payload, Sequence) or isinstance(payload, str | bytes | bytearray):
        return ()
    descriptors: list[MessageDescriptor] = []
    for item in payload:
        descriptor = load_message_descriptor(item)
        if descriptor is not None:
            descriptors.append(descriptor)
    return tuple(descriptors)


def localize_message_descriptor(descriptor: MessageDescriptor | None, *, locale: str | None) -> tuple[str | None, str | None]:
    if descriptor is None:
        return None, None
    localized = get_translation_service().translate(
        descriptor.key,
        locale=locale,
        params=dict(descriptor.params),
    )
    return localized.text, localized.locale


def _normalize_params(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): item
        for key, item in value.items()
    }


__all__ = [
    "dump_message_descriptor",
    "dump_message_descriptors",
    "load_message_descriptor",
    "load_message_descriptors",
    "localize_message_descriptor",
]
