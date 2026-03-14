from __future__ import annotations

AI_EVENT_NOTIFICATION_CREATED = "notification_created"

PROMPT_TASK_NOTIFICATION_HUMANIZE = "notification_humanize"
DEFAULT_NOTIFICATION_PROMPT_NAME = "notification.default"
DEFAULT_NOTIFICATION_PROMPT_VERSION = 1
DEFAULT_NOTIFICATION_TIMEFRAME = 15

TEMPLATE_DEGRADED_STRATEGY = "template_humanize"

NOTIFICATION_SEVERITY_VALUES = ("info", "warning", "critical")
NOTIFICATION_URGENCY_VALUES = ("low", "medium", "high")

SUPPORTED_NOTIFICATION_SOURCE_EVENTS = frozenset(
    {
        "signal_created",
        "anomaly_detected",
        "decision_generated",
        "market_regime_changed",
        "portfolio_position_changed",
        "portfolio_balance_updated",
    }
)

EVENT_PROMPT_NAMES: dict[str, str] = {
    "signal_created": "notification.signal_created",
    "anomaly_detected": "notification.anomaly_detected",
    "decision_generated": "notification.decision_generated",
    "market_regime_changed": "notification.market_regime_changed",
    "portfolio_position_changed": "notification.portfolio_position_changed",
    "portfolio_balance_updated": "notification.portfolio_balance_updated",
}

CANONICAL_REF_FIELDS: dict[str, tuple[str, ...]] = {
    "signal_created": ("signal_type",),
    "anomaly_detected": ("anomaly_type", "severity", "score"),
    "decision_generated": ("decision", "score"),
    "market_regime_changed": ("regime", "confidence", "cycle_phase"),
    "portfolio_position_changed": ("exchange_name", "balance", "value_usd"),
    "portfolio_balance_updated": ("exchange_name", "balance", "value_usd"),
}

__all__ = [
    "AI_EVENT_NOTIFICATION_CREATED",
    "CANONICAL_REF_FIELDS",
    "DEFAULT_NOTIFICATION_PROMPT_NAME",
    "DEFAULT_NOTIFICATION_PROMPT_VERSION",
    "DEFAULT_NOTIFICATION_TIMEFRAME",
    "EVENT_PROMPT_NAMES",
    "NOTIFICATION_SEVERITY_VALUES",
    "NOTIFICATION_URGENCY_VALUES",
    "PROMPT_TASK_NOTIFICATION_HUMANIZE",
    "SUPPORTED_NOTIFICATION_SOURCE_EVENTS",
    "TEMPLATE_DEGRADED_STRATEGY",
]
