from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class LocalePolicy:
    supported_locales: tuple[str, ...] = ("en", "ru")
    default_locale: str = "en"
    fallback_locale: str = "en"


@dataclass(frozen=True, slots=True)
class LocaleResolution:
    requested_locale: str | None
    effective_locale: str
    fallback_chain: tuple[str, ...]
    source: str
    accept_language_chain: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LocalizedText:
    key: str
    locale: str
    text: str
    params: Mapping[str, object] = field(default_factory=dict)
    fallback_locale: str | None = None
