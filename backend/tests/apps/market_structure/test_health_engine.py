from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from src.apps.market_structure.engines.health_engine import (
    apply_market_structure_alert_transition,
    build_market_structure_source_health,
    mark_market_structure_poll_failure,
)


def _source(**overrides):
    baseline = {
        "id": 1,
        "plugin_name": "manual_push",
        "display_name": "Test Source",
        "enabled": True,
        "auth_mode": "public",
        "settings_json": {
            "coin_symbol": "ETHUSD_EVT",
            "timeframe": 15,
            "venue": "liqscope",
            "provider": "liqscope",
            "ingest_mode": "webhook",
        },
        "credentials_json": {},
        "cursor_json": {},
        "last_polled_at": datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
        "last_success_at": datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
        "last_snapshot_at": datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
        "last_error": None,
        "health_status": "healthy",
        "health_changed_at": None,
        "consecutive_failures": 0,
        "backoff_until": None,
        "quarantined_at": None,
        "quarantine_reason": None,
        "last_alerted_at": None,
        "last_alert_kind": None,
    }
    baseline.update(overrides)
    return SimpleNamespace(**baseline)


def test_build_market_structure_source_health_marks_stale_webhook() -> None:
    health = build_market_structure_source_health(
        _source(),
        now=datetime(2026, 3, 12, 12, 0, tzinfo=UTC),
    )

    assert health.status == "stale"
    assert health.severity == "warning"
    assert health.ingest_mode == "webhook"
    assert health.stale is True
    assert health.stale_after_seconds == 5400


def test_mark_market_structure_poll_failure_applies_backoff_and_quarantine(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.apps.market_structure.engines.health_engine.get_settings",
        lambda: SimpleNamespace(
            taskiq_market_structure_snapshot_poll_interval_seconds=180,
            taskiq_market_structure_failure_backoff_base_seconds=30,
            taskiq_market_structure_failure_backoff_max_seconds=120,
            taskiq_market_structure_quarantine_after_failures=3,
        ),
    )
    source = _source(
        plugin_name="binance_usdm",
        settings_json={"coin_symbol": "ETHUSD_EVT", "timeframe": 15, "market_symbol": "ETHUSDT"},
    )

    mark_market_structure_poll_failure(
        source,
        error_message="upstream unavailable",
        now=datetime(2026, 3, 12, 12, 0, tzinfo=UTC),
    )
    assert source.consecutive_failures == 1
    assert source.backoff_until == datetime(2026, 3, 12, 12, 0, 30, tzinfo=UTC)
    assert source.quarantined_at is None

    mark_market_structure_poll_failure(
        source,
        error_message="upstream unavailable",
        now=datetime(2026, 3, 12, 12, 1, tzinfo=UTC),
    )
    assert source.consecutive_failures == 2
    assert source.backoff_until == datetime(2026, 3, 12, 12, 2, tzinfo=UTC)
    assert source.quarantined_at is None

    mark_market_structure_poll_failure(
        source,
        error_message="upstream unavailable",
        now=datetime(2026, 3, 12, 12, 3, tzinfo=UTC),
    )
    assert source.consecutive_failures == 3
    assert source.enabled is False
    assert source.backoff_until is None
    assert source.quarantined_at == datetime(2026, 3, 12, 12, 3, tzinfo=UTC)
    assert "consecutive polling failures" in str(source.quarantine_reason)


def test_apply_market_structure_alert_transition_fires_only_on_new_state() -> None:
    source = _source(
        plugin_name="binance_usdm",
        settings_json={"coin_symbol": "ETHUSD_EVT", "timeframe": 15, "market_symbol": "ETHUSDT"},
        last_error="poll failed",
    )

    alert_kind = apply_market_structure_alert_transition(
        source,
        previous_health_status="healthy",
        now=datetime(2026, 3, 12, 12, 0, tzinfo=UTC),
    )
    assert alert_kind == "error"
    assert source.last_alert_kind == "error"
    assert source.last_alerted_at == datetime(2026, 3, 12, 12, 0, tzinfo=UTC)

    repeated_alert = apply_market_structure_alert_transition(
        source,
        previous_health_status="error",
        now=datetime(2026, 3, 12, 12, 1, tzinfo=UTC),
    )
    assert repeated_alert is None

