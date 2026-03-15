from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from string import Formatter

from src.core.i18n.catalog_loader import load_catalog, load_catalogs


@dataclass(frozen=True, slots=True)
class TranslationCoverage:
    locale: str
    translated_keys: int
    total_keys: int

    @property
    def percent(self) -> float:
        if self.total_keys <= 0:
            return 100.0
        return round((self.translated_keys / self.total_keys) * 100.0, 2)


@dataclass(frozen=True, slots=True)
class CatalogValidationReport:
    base_locale: str
    locales: tuple[str, ...]
    total_keys: int
    coverage: tuple[TranslationCoverage, ...]
    version_mismatches: dict[str, tuple[int, int]] = field(default_factory=dict)
    missing_keys: dict[str, tuple[str, ...]] = field(default_factory=dict)
    orphan_keys: dict[str, tuple[str, ...]] = field(default_factory=dict)
    parameter_mismatches: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return not (self.version_mismatches or self.missing_keys or self.orphan_keys or self.parameter_mismatches)


def catalog_locales(*, directory: Path | None = None) -> tuple[str, ...]:
    root = directory or Path(__file__).with_name("catalogs")
    return tuple(sorted(path.stem for path in root.glob("*.yaml")))


def validate_catalogs(
    *,
    directory: Path | None = None,
    base_locale: str = "en",
    locales: tuple[str, ...] | None = None,
) -> CatalogValidationReport:
    resolved_locales = locales or catalog_locales(directory=directory)
    if base_locale not in resolved_locales:
        raise ValueError(f"Base locale '{base_locale}' is not available in the translation catalog directory.")

    catalogs = load_catalogs(resolved_locales, directory=directory)
    base_catalog = catalogs[base_locale]
    base_keys = set(base_catalog.messages)
    base_version = base_catalog.version
    total_keys = len(base_keys)

    coverage: list[TranslationCoverage] = []
    version_mismatches: dict[str, tuple[int, int]] = {}
    missing_keys: dict[str, tuple[str, ...]] = {}
    orphan_keys: dict[str, tuple[str, ...]] = {}
    parameter_mismatches: dict[str, tuple[str, ...]] = {}

    for locale in resolved_locales:
        catalog = catalogs[locale]
        locale_keys = set(catalog.messages)
        translated_keys = len(base_keys & locale_keys)
        coverage.append(
            TranslationCoverage(
                locale=locale,
                translated_keys=translated_keys,
                total_keys=total_keys,
            )
        )

        if catalog.version != base_version:
            version_mismatches[locale] = (catalog.version, base_version)

        missing = tuple(sorted(base_keys - locale_keys))
        if missing:
            missing_keys[locale] = missing

        orphans = tuple(sorted(locale_keys - base_keys))
        if orphans:
            orphan_keys[locale] = orphans

        mismatched_params = sorted(
            key
            for key in (base_keys & locale_keys)
            if _message_params(base_catalog.messages[key].message) != _message_params(catalog.messages[key].message)
        )
        if mismatched_params:
            parameter_mismatches[locale] = tuple(mismatched_params)

    return CatalogValidationReport(
        base_locale=base_locale,
        locales=resolved_locales,
        total_keys=total_keys,
        coverage=tuple(coverage),
        version_mismatches=version_mismatches,
        missing_keys=missing_keys,
        orphan_keys=orphan_keys,
        parameter_mismatches=parameter_mismatches,
    )


def render_translation_coverage(report: CatalogValidationReport) -> str:
    lines = [
        "# Translation Coverage",
        "",
        f"Base locale: `{report.base_locale}`",
        f"Total message keys: `{report.total_keys}`",
        "",
        "| language | coverage | translated | total |",
        "| --- | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| {item.locale} | {item.percent:.2f}% | {item.translated_keys} | {item.total_keys} |"
        for item in report.coverage
    )

    if report.is_valid:
        lines.extend(["", "Validation: `ok`"])
        return "\n".join(lines) + "\n"

    lines.extend(["", "Validation: `failed`", ""])
    for locale, versions in sorted(report.version_mismatches.items()):
        lines.append(f"- version mismatch for `{locale}`: `{versions[0]}` != `{versions[1]}`")
    for locale, keys in sorted(report.missing_keys.items()):
        lines.append(f"- missing keys in `{locale}`: `{', '.join(keys)}`")
    for locale, keys in sorted(report.orphan_keys.items()):
        lines.append(f"- orphan keys in `{locale}`: `{', '.join(keys)}`")
    for locale, keys in sorted(report.parameter_mismatches.items()):
        lines.append(f"- parameter mismatches in `{locale}`: `{', '.join(keys)}`")
    return "\n".join(lines) + "\n"


def write_translation_coverage(
    *,
    output: Path,
    directory: Path | None = None,
    base_locale: str = "en",
    locales: tuple[str, ...] | None = None,
) -> Path:
    report = validate_catalogs(directory=directory, base_locale=base_locale, locales=locales)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_translation_coverage(report), encoding="utf-8")
    return output


def check_translation_coverage(
    *,
    snapshot: Path,
    directory: Path | None = None,
    base_locale: str = "en",
    locales: tuple[str, ...] | None = None,
) -> tuple[bool, str]:
    report = validate_catalogs(directory=directory, base_locale=base_locale, locales=locales)
    rendered = render_translation_coverage(report)
    expected = snapshot.read_text(encoding="utf-8")
    return rendered == expected, rendered


def _message_params(template: str) -> tuple[str, ...]:
    formatter = Formatter()
    params = {
        field_name.split(".", 1)[0].split("[", 1)[0]
        for _, field_name, _, _ in formatter.parse(template)
        if field_name
    }
    return tuple(sorted(params))


__all__ = [
    "CatalogValidationReport",
    "TranslationCoverage",
    "catalog_locales",
    "check_translation_coverage",
    "render_translation_coverage",
    "validate_catalogs",
    "write_translation_coverage",
]
