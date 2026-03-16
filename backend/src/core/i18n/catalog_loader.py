from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import yaml
from yaml.nodes import MappingNode

from src.core.i18n.contracts import CatalogMessage, TranslationCatalog


class TranslationCatalogError(ValueError):
    """Raised when external translation catalogs are missing or malformed."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: MappingNode, deep: bool = False) -> dict[Any, Any]:
    yaml_loader = cast(Any, loader)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = yaml_loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise TranslationCatalogError(f"Translation catalog contains a duplicate key: {key!r}.")
        mapping[key] = yaml_loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _load_yaml_payload(raw: str) -> object:
    loader = _UniqueKeyLoader(raw)
    try:
        return loader.get_single_data()
    finally:
        cast(Any, loader).dispose()


def load_catalog(locale: str, *, directory: Path | None = None) -> TranslationCatalog:
    catalog_path = (directory or _catalog_directory()) / f"{locale}.yaml"
    try:
        payload = _load_yaml_payload(catalog_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TranslationCatalogError(f"Translation catalog '{catalog_path}' was not found.") from exc
    except yaml.YAMLError as exc:
        raise TranslationCatalogError(f"Translation catalog '{catalog_path}' is not valid YAML.") from exc

    if not isinstance(payload, dict):
        raise TranslationCatalogError(f"Translation catalog '{catalog_path}' must be a mapping.")

    version = payload.get("version")
    messages = payload.get("messages")
    if not isinstance(version, int) or version < 1:
        raise TranslationCatalogError(f"Translation catalog '{catalog_path}' must define a positive integer version.")
    if not isinstance(messages, dict):
        raise TranslationCatalogError(f"Translation catalog '{catalog_path}' must define a 'messages' mapping.")

    return TranslationCatalog(
        locale=locale,
        version=version,
        messages={
            key: _parse_message_entry(catalog_path, key, value)
            for key, value in messages.items()
        },
    )


def load_catalogs(locales: Iterable[str], *, directory: Path | None = None) -> dict[str, TranslationCatalog]:
    return {
        locale: load_catalog(locale, directory=directory)
        for locale in locales
    }


def _catalog_directory() -> Path:
    return Path(__file__).with_name("catalogs")


def _parse_message_entry(path: Path, key: Any, value: Any) -> CatalogMessage:
    if not isinstance(key, str) or not key.strip():
        raise TranslationCatalogError(f"Translation catalog '{path}' contains an invalid message key: {key!r}.")
    if not isinstance(value, dict):
        raise TranslationCatalogError(f"Translation entry '{key}' in '{path}' must be a mapping.")

    message = value.get("message")
    description = value.get("description")
    if not isinstance(message, str) or not message.strip():
        raise TranslationCatalogError(f"Translation entry '{key}' in '{path}' must define a non-empty message.")
    if not isinstance(description, str) or not description.strip():
        raise TranslationCatalogError(
            f"Translation entry '{key}' in '{path}' must define a non-empty description."
        )
    return CatalogMessage(message=message, description=description)
