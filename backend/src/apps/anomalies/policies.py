from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.apps.anomalies.constants import (
    ANOMALY_STATUS_COOLING,
    ANOMALY_STATUS_NEW,
    ANOMALY_STATUS_RESOLVED,
    ENTRY_THRESHOLDS,
    EXIT_THRESHOLDS,
    REGIME_ENTRY_MULTIPLIER,
)


@dataclass(slots=True)
class AnomalyPolicyDecision:
    action: str
    status: str | None = None
    cooldown_until: datetime | None = None
    reason: str | None = None


class AnomalyPolicyEngine:
    def __init__(self, *, cooldown_minutes: dict[str, int]) -> None:
        self._cooldown_minutes = cooldown_minutes

    def entry_threshold(self, anomaly_type: str, market_regime: str | None) -> float:
        base_threshold = ENTRY_THRESHOLDS[anomaly_type]
        return base_threshold * REGIME_ENTRY_MULTIPLIER.get(market_regime, 1.0)

    def exit_threshold(self, anomaly_type: str, market_regime: str | None) -> float:
        base_threshold = EXIT_THRESHOLDS[anomaly_type]
        return base_threshold * REGIME_ENTRY_MULTIPLIER.get(market_regime, 1.0)

    def cooldown_until(self, anomaly_type: str, detected_at: datetime) -> datetime:
        return detected_at + timedelta(minutes=self._cooldown_minutes[anomaly_type])

    def evaluate(
        self,
        *,
        anomaly_type: str,
        score: float,
        detected_at: datetime,
        market_regime: str | None,
        latest_anomaly,
        confirmation_hits: int,
        confirmation_target: int,
    ) -> AnomalyPolicyDecision:
        entry = self.entry_threshold(anomaly_type, market_regime)
        exit_threshold = self.exit_threshold(anomaly_type, market_regime)

        if confirmation_hits < confirmation_target:
            return AnomalyPolicyDecision(action="skip", reason="awaiting_confirmation")

        if latest_anomaly is not None:
            if score < exit_threshold:
                next_status = (
                    ANOMALY_STATUS_RESOLVED
                    if latest_anomaly.status == ANOMALY_STATUS_COOLING
                    else ANOMALY_STATUS_COOLING
                )
                return AnomalyPolicyDecision(action="transition", status=next_status)

            if score >= entry:
                if latest_anomaly.cooldown_until is not None and detected_at < latest_anomaly.cooldown_until:
                    return AnomalyPolicyDecision(action="refresh", status=latest_anomaly.status)
                return AnomalyPolicyDecision(
                    action="create",
                    status=ANOMALY_STATUS_NEW,
                    cooldown_until=self.cooldown_until(anomaly_type, detected_at),
                )

            return AnomalyPolicyDecision(action="keep", status=latest_anomaly.status)

        if score < entry:
            return AnomalyPolicyDecision(action="skip", reason="below_entry_threshold")

        return AnomalyPolicyDecision(
            action="create",
            status=ANOMALY_STATUS_NEW,
            cooldown_until=self.cooldown_until(anomaly_type, detected_at),
        )
