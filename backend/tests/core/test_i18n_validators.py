import pytest
from iris.core.i18n import TranslationCatalogError, load_catalog, render_translation_coverage, validate_catalogs


def test_load_catalog_rejects_duplicate_message_keys(tmp_path) -> None:
    (tmp_path / "en.yaml").write_text(
        """
version: 1
messages:
  error.test:
    description: first
    message: First.
  error.test:
    description: second
    message: Second.
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(TranslationCatalogError, match="duplicate key"):
        load_catalog("en", directory=tmp_path)


def test_validate_catalogs_reports_missing_keys_and_param_mismatches(tmp_path) -> None:
    (tmp_path / "en.yaml").write_text(
        """
version: 1
messages:
  error.test:
    description: english
    message: Hello {name}.
  ha.dashboard.view.overview.title:
    description: overview
    message: Overview
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "ru.yaml").write_text(
        """
version: 1
messages:
  error.test:
    description: russian
    message: Привет {username}.
""".strip()
        + "\n",
        encoding="utf-8",
    )

    report = validate_catalogs(directory=tmp_path)

    assert report.is_valid is False
    assert report.missing_keys["ru"] == ("ha.dashboard.view.overview.title",)
    assert report.parameter_mismatches["ru"] == ("error.test",)


def test_render_translation_coverage_reports_current_catalog_status() -> None:
    report = validate_catalogs()
    rendered = render_translation_coverage(report)

    assert report.is_valid is True
    assert "| en | 100.00% |" in rendered
    assert "| ru | 100.00% |" in rendered
    assert "Validation: `ok`" in rendered
