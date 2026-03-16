from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

from src.apps.anomalies.constants import (
    ANOMALY_STATUS_ACTIVE,
    ANOMALY_STATUS_COOLING,
    ANOMALY_STATUS_RESOLVED,
    ANOMALY_TYPE_COMPRESSION_EXPANSION,
    ANOMALY_TYPE_CORRELATION_BREAKDOWN,
    ANOMALY_TYPE_PRICE_SPIKE,
)
from src.apps.anomalies.policies import AnomalyPolicyEngine


def _policy_engine() -> AnomalyPolicyEngine:
    return AnomalyPolicyEngine(
        cooldown_minutes={
            ANOMALY_TYPE_PRICE_SPIKE: 45,
            ANOMALY_TYPE_COMPRESSION_EXPANSION: 60,
            ANOMALY_TYPE_CORRELATION_BREAKDOWN: 75,
        }
    )


def test_policy_engine_requires_confirmation_before_create() -> None:
    now = datetime(2026, 3, 12, 12, 0, tzinfo=UTC)

    decision = _policy_engine().evaluate(
        anomaly_type=ANOMALY_TYPE_CORRELATION_BREAKDOWN,
        score=0.92,
        detected_at=now,
        market_regime="bull_trend",
        latest_anomaly=None,
        confirmation_hits=1,
        confirmation_target=2,
    )

    assert decision.action == "skip"
    assert decision.reason == "awaiting_confirmation"


def test_policy_engine_transitions_from_active_to_cooling_and_resolved() -> None:
    now = datetime(2026, 3, 12, 12, 0, tzinfo=UTC)
    engine = _policy_engine()

    cooling = engine.evaluate(
        anomaly_type=ANOMALY_TYPE_PRICE_SPIKE,
        score=0.10,
        detected_at=now,
        market_regime="bull_trend",
        latest_anomaly=SimpleNamespace(status=ANOMALY_STATUS_ACTIVE, cooldown_until=now - timedelta(minutes=1)),
        confirmation_hits=1,
        confirmation_target=1,
    )
    resolved = engine.evaluate(
        anomaly_type=ANOMALY_TYPE_PRICE_SPIKE,
        score=0.10,
        detected_at=now,
        market_regime="bull_trend",
        latest_anomaly=SimpleNamespace(status=ANOMALY_STATUS_COOLING, cooldown_until=now - timedelta(minutes=1)),
        confirmation_hits=1,
        confirmation_target=1,
    )

    assert cooling.action == "transition"
    assert cooling.status == ANOMALY_STATUS_COOLING
    assert resolved.action == "transition"
    assert resolved.status == ANOMALY_STATUS_RESOLVED


def test_policy_engine_respects_cooldown_and_recreates_after_expiry() -> None:
    now = datetime(2026, 3, 12, 12, 0, tzinfo=UTC)
    engine = _policy_engine()

    refresh = engine.evaluate(
        anomaly_type=ANOMALY_TYPE_COMPRESSION_EXPANSION,
        score=0.82,
        detected_at=now,
        market_regime="bull_trend",
        latest_anomaly=SimpleNamespace(status=ANOMALY_STATUS_ACTIVE, cooldown_until=now + timedelta(minutes=5)),
        confirmation_hits=1,
        confirmation_target=1,
    )
    recreate = engine.evaluate(
        anomaly_type=ANOMALY_TYPE_COMPRESSION_EXPANSION,
        score=0.82,
        detected_at=now,
        market_regime="bull_trend",
        latest_anomaly=SimpleNamespace(status=ANOMALY_STATUS_ACTIVE, cooldown_until=now - timedelta(minutes=1)),
        confirmation_hits=1,
        confirmation_target=1,
    )

    assert refresh.action == "refresh"
    assert recreate.action == "create"
    assert recreate.status == "new"
