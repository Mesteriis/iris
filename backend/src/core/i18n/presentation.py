from collections.abc import Mapping, Sequence
from typing import Any, TypeGuard

from src.core.i18n.contracts import MessageDescriptor
from src.core.i18n.descriptors import (
    dump_message_descriptor,
    dump_message_descriptors,
    load_message_descriptor,
    load_message_descriptors,
)

CONTENT_VERSION = 1
CONTENT_KIND_DESCRIPTOR_BUNDLE = "descriptor_bundle"
CONTENT_KIND_GENERATED_TEXT = "generated_text"


class ContentPayloadValidationError(ValueError):
    """Raised when a persisted presentation payload does not match the canonical envelope."""


def build_descriptor_bundle_content(
    *,
    fields: Mapping[str, MessageDescriptor | Sequence[MessageDescriptor] | None],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "version": CONTENT_VERSION,
        "kind": CONTENT_KIND_DESCRIPTOR_BUNDLE,
    }
    for name, value in fields.items():
        if value is None or isinstance(value, MessageDescriptor):
            payload[str(name)] = dump_message_descriptor(value)
        elif _is_descriptor_sequence(value):
            payload[str(name)] = dump_message_descriptors(value)
        else:
            raise ContentPayloadValidationError(
                f"Descriptor bundle field '{name}' must contain a message descriptor or list of descriptors."
            )
    return validate_content_payload(payload)


def build_generated_text_content(
    *,
    rendered_locale: str | None,
    fields: Mapping[str, object],
) -> dict[str, object]:
    payload: dict[str, object] = {
        "version": CONTENT_VERSION,
        "kind": CONTENT_KIND_GENERATED_TEXT,
    }
    if rendered_locale is not None and str(rendered_locale).strip():
        payload["rendered_locale"] = str(rendered_locale).strip()
    for name, value in fields.items():
        payload[str(name)] = _normalize_generated_value(value)
    return validate_content_payload(payload)


def validate_content_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise ContentPayloadValidationError("Presentation content payload must be a mapping.")
    version = payload.get("version")
    if version != CONTENT_VERSION:
        raise ContentPayloadValidationError(
            f"Unsupported presentation content payload version: {version!r}."
        )
    kind = payload.get("kind")
    if kind == CONTENT_KIND_DESCRIPTOR_BUNDLE:
        return _validate_descriptor_bundle_payload(payload)
    if kind == CONTENT_KIND_GENERATED_TEXT:
        return _validate_generated_text_payload(payload)
    raise ContentPayloadValidationError(f"Unsupported presentation content payload kind: {kind!r}.")


def content_kind(payload: object) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    kind = payload.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        return None
    return kind


def content_rendered_locale(payload: object) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    rendered_locale = payload.get("rendered_locale")
    if not isinstance(rendered_locale, str) or not rendered_locale.strip():
        return None
    return rendered_locale


def content_descriptor(payload: object, field: str) -> MessageDescriptor | None:
    if not isinstance(payload, Mapping):
        return None
    return load_message_descriptor(payload.get(field))


def content_descriptors(payload: object, field: str) -> tuple[MessageDescriptor, ...]:
    if not isinstance(payload, Mapping):
        return ()
    descriptors: tuple[MessageDescriptor, ...] = load_message_descriptors(payload.get(field))
    return descriptors


def content_text(payload: object, field: str) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    value = payload.get(field)
    if not isinstance(value, str):
        return None
    return value


def content_text_list(payload: object, field: str) -> list[str]:
    if not isinstance(payload, Mapping):
        return []
    value = payload.get(field)
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    return [item for item in value if isinstance(item, str)]


def is_descriptor_bundle_content(payload: object) -> bool:
    return content_kind(payload) == CONTENT_KIND_DESCRIPTOR_BUNDLE


def is_generated_text_content(payload: object) -> bool:
    return content_kind(payload) == CONTENT_KIND_GENERATED_TEXT


def _validate_descriptor_bundle_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {
        "version": CONTENT_VERSION,
        "kind": CONTENT_KIND_DESCRIPTOR_BUNDLE,
    }
    for key, value in payload.items():
        normalized_key = str(key)
        if normalized_key in {"version", "kind"}:
            continue
        if value is None:
            normalized[normalized_key] = None
            continue
        if _is_descriptor_sequence(value):
            normalized[normalized_key] = dump_message_descriptors(load_message_descriptors(value))
            continue
        if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
            descriptors = load_message_descriptors(value)
            if descriptors or len(value) == 0:
                normalized[normalized_key] = dump_message_descriptors(descriptors)
                continue
        descriptor = load_message_descriptor(value)
        if descriptor is None:
            raise ContentPayloadValidationError(
                f"Descriptor bundle field '{normalized_key}' must contain a message descriptor or list of descriptors."
            )
        normalized[normalized_key] = dump_message_descriptor(descriptor)
    return normalized


def _validate_generated_text_payload(payload: Mapping[str, object]) -> dict[str, object]:
    rendered_locale = payload.get("rendered_locale")
    if not isinstance(rendered_locale, str) or not rendered_locale.strip():
        raise ContentPayloadValidationError("Generated text content must define a non-empty rendered_locale.")
    normalized: dict[str, object] = {
        "version": CONTENT_VERSION,
        "kind": CONTENT_KIND_GENERATED_TEXT,
        "rendered_locale": rendered_locale.strip(),
    }
    for key, value in payload.items():
        normalized_key = str(key)
        if normalized_key in {"version", "kind", "rendered_locale"}:
            continue
        normalized[normalized_key] = _normalize_generated_value(value)
    return normalized


def _is_descriptor_sequence(value: object) -> TypeGuard[Sequence[MessageDescriptor]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return False
    return all(isinstance(item, MessageDescriptor) for item in value)


def _normalize_generated_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [str(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return str(value) if not isinstance(value, bool | int | float) else value


__all__ = [
    "CONTENT_KIND_DESCRIPTOR_BUNDLE",
    "CONTENT_KIND_GENERATED_TEXT",
    "CONTENT_VERSION",
    "ContentPayloadValidationError",
    "build_descriptor_bundle_content",
    "build_generated_text_content",
    "content_descriptor",
    "content_descriptors",
    "content_kind",
    "content_rendered_locale",
    "content_text",
    "content_text_list",
    "is_descriptor_bundle_content",
    "is_generated_text_content",
    "validate_content_payload",
]
