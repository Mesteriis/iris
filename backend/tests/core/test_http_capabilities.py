from __future__ import annotations

import src.core.bootstrap.app as bootstrap_app_module
import src.core.http.capabilities as capabilities_module


def test_http_capability_catalog_tracks_mode_specific_operations() -> None:
    settings = bootstrap_app_module.settings.model_copy(update={"enable_hypothesis_engine": True})

    catalog = capabilities_module.build_http_capability_catalog(settings=settings)
    by_operation = {record.operation_id: record for record in catalog}

    assert by_operation["control_plane_create_route"].full is True
    assert by_operation["control_plane_create_route"].ha_addon is False
    assert by_operation["news_read_sources"].ha_addon is True
    assert by_operation["news_run_source_job"].ha_addon is False
    assert by_operation["hypothesis_stream_ai_events"].full is True
    assert by_operation["hypothesis_stream_ai_events"].ha_addon is False


def test_http_capability_catalog_render_includes_expected_columns() -> None:
    settings = bootstrap_app_module.settings.model_copy(update={"enable_hypothesis_engine": True})

    rendered = capabilities_module.render_http_capability_catalog(settings=settings)

    assert "# HTTP Capability Catalog" in rendered
    assert "| Operation ID | Method | Path | Domain | Category | `full` | `local` | `ha_addon` |" in rendered
    assert "`control_plane_create_route`" in rendered
    assert "`/api/v1/control-plane/routes`" in rendered


def test_http_capability_catalog_check_matches_generated_snapshot(tmp_path) -> None:
    settings = bootstrap_app_module.settings.model_copy(update={"enable_hypothesis_engine": True})
    snapshot_path = capabilities_module.write_http_capability_catalog(
        settings=settings,
        output=tmp_path / "http-capability-catalog.md",
    )

    matches, diff = capabilities_module.check_http_capability_catalog(settings=settings, snapshot=snapshot_path)

    assert matches is True
    assert diff == ""


def test_http_capability_catalog_check_reports_diff(tmp_path) -> None:
    settings = bootstrap_app_module.settings.model_copy(update={"enable_hypothesis_engine": True})
    snapshot_path = tmp_path / "http-capability-catalog.md"
    snapshot_path.write_text("# broken catalog\n", encoding="utf-8")

    matches, diff = capabilities_module.check_http_capability_catalog(settings=settings, snapshot=snapshot_path)

    assert matches is False
    assert str(snapshot_path) in diff
    assert f"{snapshot_path}.generated" in diff
