import iris.core.bootstrap.app as bootstrap_app_module
import iris.core.http.capabilities as capabilities_module


def test_http_capability_catalog_tracks_mode_specific_operations() -> None:
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

    catalog = capabilities_module.build_http_capability_catalog(settings=settings)
    by_operation = {record.operation_id: record for record in catalog}

    assert by_operation["control_plane_create_route"].full is True
    assert by_operation["control_plane_create_route"].ha_addon is False
    assert by_operation["control_plane_read_ai_providers"].full is True
    assert by_operation["control_plane_read_ai_providers"].ha_addon is False
    assert by_operation["control_plane_create_ai_prompt"].ha_addon is False
    assert by_operation["briefs_read_market_brief"].ha_addon is True
    assert by_operation["briefs_run_market_brief_job"].ha_addon is False
    assert by_operation["explanations_read_signal_explanation"].ha_addon is True
    assert by_operation["explanations_run_signal_explanation_job"].ha_addon is False
    assert by_operation["news_read_sources"].ha_addon is True
    assert by_operation["notifications_read_notifications"].ha_addon is True
    assert by_operation["news_run_source_job"].ha_addon is False
    assert by_operation["hypothesis_stream_ai_events"].full is True
    assert by_operation["hypothesis_stream_ai_events"].ha_addon is False
    assert by_operation["control_plane_create_route"].audience is capabilities_module.ContractAudience.OPERATOR_CONTROL
    assert by_operation["control_plane_create_route"].execution_model is capabilities_module.ExecutionModel.SYNC
    assert by_operation["control_plane_create_route"].idempotency_policy is capabilities_module.IdempotencyPolicy.NON_IDEMPOTENT
    assert by_operation["control_plane_create_route"].auth_policy is capabilities_module.AuthPolicy.OPERATOR
    assert by_operation["control_plane_read_ai_providers"].audience is capabilities_module.ContractAudience.OPERATOR_CONTROL
    assert by_operation["control_plane_read_ai_providers"].auth_policy is capabilities_module.AuthPolicy.OPERATOR
    assert by_operation["control_plane_read_ai_providers"].idempotency_policy is capabilities_module.IdempotencyPolicy.STRICT
    assert by_operation["control_plane_create_ai_prompt"].audience is capabilities_module.ContractAudience.OPERATOR_CONTROL
    assert by_operation["control_plane_activate_ai_prompt"].idempotency_policy is capabilities_module.IdempotencyPolicy.CONDITIONAL
    assert by_operation["news_read_sources"].audience is capabilities_module.ContractAudience.PUBLIC_READ
    assert by_operation["notifications_read_notifications"].audience is capabilities_module.ContractAudience.PUBLIC_READ
    assert by_operation["briefs_read_market_brief"].audience is capabilities_module.ContractAudience.OPERATOR_CONTROL
    assert by_operation["briefs_read_market_brief"].auth_policy is capabilities_module.AuthPolicy.OPERATOR
    assert by_operation["briefs_run_market_brief_job"].execution_model is capabilities_module.ExecutionModel.ASYNC
    assert by_operation["briefs_run_market_brief_job"].operation_resource_required is True
    assert by_operation["explanations_read_signal_explanation"].audience is capabilities_module.ContractAudience.PUBLIC_READ
    assert by_operation["explanations_read_signal_explanation"].auth_policy is capabilities_module.AuthPolicy.PUBLIC
    assert by_operation["explanations_run_signal_explanation_job"].execution_model is capabilities_module.ExecutionModel.ASYNC
    assert by_operation["explanations_run_signal_explanation_job"].operation_resource_required is True
    assert by_operation["news_read_sources"].idempotency_policy is capabilities_module.IdempotencyPolicy.STRICT
    assert by_operation["news_read_sources"].auth_policy is capabilities_module.AuthPolicy.PUBLIC
    assert by_operation["news_run_source_job"].execution_model is capabilities_module.ExecutionModel.ASYNC
    assert by_operation["news_run_source_job"].operation_resource_required is True
    assert by_operation["market_structure_ingest_snapshots"].audience is capabilities_module.ContractAudience.EXTERNAL_INGEST
    assert by_operation["market_structure_ingest_snapshots"].auth_policy is capabilities_module.AuthPolicy.WEBHOOK_TOKEN
    assert by_operation["hypothesis_stream_ai_events"].execution_model is capabilities_module.ExecutionModel.STREAM
    assert by_operation["system_handle_status"].audience is capabilities_module.ContractAudience.INTERNAL_PLATFORM
    assert by_operation["system_handle_status"].auth_policy is capabilities_module.AuthPolicy.PUBLIC
    assert by_operation["system_read_operation_status"].audience is capabilities_module.ContractAudience.INTERNAL_PLATFORM
    assert by_operation["system_read_operation_status"].operation_resource_required is False
    assert by_operation["system_read_operation_status"].auth_policy is capabilities_module.AuthPolicy.PUBLIC


def test_http_capability_catalog_render_includes_expected_columns() -> None:
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

    rendered = capabilities_module.render_http_capability_catalog(settings=settings)

    assert "# HTTP Capability Catalog" in rendered
    assert (
        "| Operation ID | Method | Path | Domain | Category | Audience | Execution | Idempotency | Operation Resource | Auth | `full` | `local` | `ha_addon` |"
        in rendered
    )
    assert "`briefs_read_market_brief`" in rendered
    assert "`/api/v1/briefs/market`" in rendered
    assert "`explanations_read_signal_explanation`" in rendered
    assert "`/api/v1/explanations/signals/{signal_id}`" in rendered
    assert "`control_plane_create_route`" in rendered
    assert "`/api/v1/control-plane/routes`" in rendered
    assert "`control_plane_read_ai_providers`" in rendered
    assert "`/api/v1/control-plane/ai/providers`" in rendered
    assert "`system_read_operation_status`" in rendered
    assert "`/api/v1/operations/{operation_id}`" in rendered
    assert "`operator_control`" in rendered
    assert "`non_idempotent`" in rendered


def test_http_capability_catalog_check_matches_generated_snapshot(tmp_path) -> None:
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
    snapshot_path = capabilities_module.write_http_capability_catalog(
        settings=settings,
        output=tmp_path / "http-capability-catalog.md",
    )

    matches, diff = capabilities_module.check_http_capability_catalog(settings=settings, snapshot=snapshot_path)

    assert matches is True
    assert diff == ""


def test_http_capability_catalog_check_reports_diff(tmp_path) -> None:
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
    snapshot_path = tmp_path / "http-capability-catalog.md"
    snapshot_path.write_text("# broken catalog\n", encoding="utf-8")

    matches, diff = capabilities_module.check_http_capability_catalog(settings=settings, snapshot=snapshot_path)

    assert matches is False
    assert str(snapshot_path) in diff
    assert f"{snapshot_path}.generated" in diff
