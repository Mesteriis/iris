from __future__ import annotations

import src.core.bootstrap.app as bootstrap_app_module
import src.core.http.matrix as matrix_module


def test_http_mode_matrix_tracks_mode_limited_categories() -> None:
    settings = bootstrap_app_module.settings.model_copy(
        update={
            "ai_providers": [
                {
                    "name": "local_test",
                    "kind": "local_http",
                    "enabled": True,
                    "base_url": "http://127.0.0.1:9",
                    "endpoint": "/api/generate",
                    "model": "llama-test",
                    "timeout_seconds": 0.05,
                    "priority": 100,
                    "capabilities": ["hypothesis_generate", "brief_generate", "explain_generate"],
                }
            ]
        }
    )

    matrix = matrix_module.build_http_mode_matrix(settings=settings)

    assert set(matrix["control-plane"][matrix_module.LaunchMode.FULL]) == {"admin", "commands", "read"}
    assert set(matrix["control-plane"][matrix_module.LaunchMode.HA_ADDON]) == {"read"}
    assert set(matrix["briefs"][matrix_module.LaunchMode.FULL]) == {"jobs", "read"}
    assert set(matrix["briefs"][matrix_module.LaunchMode.HA_ADDON]) == {"read"}
    assert set(matrix["explanations"][matrix_module.LaunchMode.FULL]) == {"jobs", "read"}
    assert set(matrix["explanations"][matrix_module.LaunchMode.HA_ADDON]) == {"read"}
    assert set(matrix["news"][matrix_module.LaunchMode.HA_ADDON]) == {"read"}
    assert set(matrix["hypothesis"][matrix_module.LaunchMode.FULL]) == {"jobs", "read", "streams"}
    assert set(matrix["hypothesis"][matrix_module.LaunchMode.HA_ADDON]) == {"read"}
    assert set(matrix["notifications"][matrix_module.LaunchMode.HA_ADDON]) == {"read"}
    assert set(matrix["system"][matrix_module.LaunchMode.FULL]) == {"operations", "read"}


def test_http_availability_matrix_render_includes_route_counts() -> None:
    settings = bootstrap_app_module.settings.model_copy(
        update={
            "ai_providers": [
                {
                    "name": "local_test",
                    "kind": "local_http",
                    "enabled": True,
                    "base_url": "http://127.0.0.1:9",
                    "endpoint": "/api/generate",
                    "model": "llama-test",
                    "timeout_seconds": 0.05,
                    "priority": 100,
                    "capabilities": ["hypothesis_generate", "brief_generate", "explain_generate"],
                }
            ]
        }
    )

    rendered = matrix_module.render_http_availability_matrix(settings=settings)

    assert "# HTTP Availability Matrix" in rendered
    assert "| `briefs` | `read`, `jobs` | `read`, `jobs` | `read` |" in rendered
    assert "| `control-plane` | `read`, `commands`, `admin` | `read`, `commands`, `admin` | `read` |" in rendered
    assert "| `explanations` | `read`, `jobs` | `read`, `jobs` | `read` |" in rendered
    assert "| `hypothesis` | `read`, `jobs`, `streams` | `read`, `jobs`, `streams` | `read` |" in rendered
    assert "| `news` | `onboarding` |" in rendered
    assert "| `system` | `read`, `operations` | `read`, `operations` | `read`, `operations` |" in rendered


def test_http_availability_matrix_check_matches_generated_snapshot(tmp_path) -> None:
    settings = bootstrap_app_module.settings.model_copy(
        update={
            "ai_providers": [
                {
                    "name": "local_test",
                    "kind": "local_http",
                    "enabled": True,
                    "base_url": "http://127.0.0.1:9",
                    "endpoint": "/api/generate",
                    "model": "llama-test",
                    "timeout_seconds": 0.05,
                    "priority": 100,
                    "capabilities": ["hypothesis_generate", "brief_generate", "explain_generate"],
                }
            ]
        }
    )
    snapshot_path = matrix_module.write_http_availability_matrix(
        settings=settings,
        output=tmp_path / "http-availability-matrix.md",
    )

    matches, diff = matrix_module.check_http_availability_matrix(settings=settings, snapshot=snapshot_path)

    assert matches is True
    assert diff == ""


def test_http_availability_matrix_check_reports_diff(tmp_path) -> None:
    settings = bootstrap_app_module.settings.model_copy(
        update={
            "ai_providers": [
                {
                    "name": "local_test",
                    "kind": "local_http",
                    "enabled": True,
                    "base_url": "http://127.0.0.1:9",
                    "endpoint": "/api/generate",
                    "model": "llama-test",
                    "timeout_seconds": 0.05,
                    "priority": 100,
                    "capabilities": ["hypothesis_generate", "brief_generate", "explain_generate"],
                }
            ]
        }
    )
    snapshot_path = tmp_path / "http-availability-matrix.md"
    snapshot_path.write_text("# broken matrix\n", encoding="utf-8")

    matches, diff = matrix_module.check_http_availability_matrix(settings=settings, snapshot=snapshot_path)

    assert matches is False
    assert str(snapshot_path) in diff
    assert f"{snapshot_path}.generated" in diff
