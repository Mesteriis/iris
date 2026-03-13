from __future__ import annotations

import src.core.bootstrap.app as bootstrap_app_module
import src.core.http.matrix as matrix_module


def test_http_mode_matrix_tracks_mode_limited_categories() -> None:
    settings = bootstrap_app_module.settings.model_copy(update={"enable_hypothesis_engine": True})

    matrix = matrix_module.build_http_mode_matrix(settings=settings)

    assert set(matrix["control-plane"][matrix_module.LaunchMode.FULL]) == {"commands", "read"}
    assert set(matrix["control-plane"][matrix_module.LaunchMode.HA_ADDON]) == {"read"}
    assert set(matrix["news"][matrix_module.LaunchMode.HA_ADDON]) == {"read"}
    assert set(matrix["hypothesis"][matrix_module.LaunchMode.FULL]) == {"commands", "jobs", "read", "streams"}
    assert set(matrix["hypothesis"][matrix_module.LaunchMode.HA_ADDON]) == {"commands", "read"}
    assert set(matrix["system"][matrix_module.LaunchMode.FULL]) == {"operations", "read"}


def test_http_availability_matrix_render_includes_route_counts() -> None:
    settings = bootstrap_app_module.settings.model_copy(update={"enable_hypothesis_engine": True})

    rendered = matrix_module.render_http_availability_matrix(settings=settings)

    assert "# HTTP Availability Matrix" in rendered
    assert "| `control-plane` | `read`, `commands` | `read`, `commands` | `read` |" in rendered
    assert "| `hypothesis` | `read`, `commands`, `jobs`, `streams` | `read`, `commands`, `jobs`, `streams` | `read`, `commands` |" in rendered
    assert "| `news` | `onboarding` |" in rendered
    assert "| `system` | `read`, `operations` | `read`, `operations` | `read`, `operations` |" in rendered


def test_http_availability_matrix_check_matches_generated_snapshot(tmp_path) -> None:
    settings = bootstrap_app_module.settings.model_copy(update={"enable_hypothesis_engine": True})
    snapshot_path = matrix_module.write_http_availability_matrix(
        settings=settings,
        output=tmp_path / "http-availability-matrix.md",
    )

    matches, diff = matrix_module.check_http_availability_matrix(settings=settings, snapshot=snapshot_path)

    assert matches is True
    assert diff == ""


def test_http_availability_matrix_check_reports_diff(tmp_path) -> None:
    settings = bootstrap_app_module.settings.model_copy(update={"enable_hypothesis_engine": True})
    snapshot_path = tmp_path / "http-availability-matrix.md"
    snapshot_path.write_text("# broken matrix\n", encoding="utf-8")

    matches, diff = matrix_module.check_http_availability_matrix(settings=settings, snapshot=snapshot_path)

    assert matches is False
    assert str(snapshot_path) in diff
    assert f"{snapshot_path}.generated" in diff
