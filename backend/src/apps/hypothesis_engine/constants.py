from __future__ import annotations

AI_EVENT_HYPOTHESIS_CREATED = "hypothesis_created"
AI_EVENT_HYPOTHESIS_EVALUATED = "hypothesis_evaluated"
AI_EVENT_INSIGHT = "ai_insight"
AI_EVENT_WEIGHTS_UPDATED = "ai_weights_updated"

HYPOTHESIS_STATUS_ACTIVE = "active"
HYPOTHESIS_STATUS_EVALUATED = "evaluated"

PROMPT_TASK_HYPOTHESIS_GENERATION = "hypothesis_generation"
PROMPT_CACHE_TTL_SECONDS = 3600
PROMPT_CACHE_PREFIX = "iris:ai:prompt"
DEFAULT_PROMPT_NAME = "hypothesis.default"
DEFAULT_PROMPT_VERSION = 1

PROVIDER_HEURISTIC = "heuristic"

FORBIDDEN_PROMPT_INFRA_KEYS = frozenset(
    {
        "provider",
        "providers",
        "provider_name",
        "provider_enablement",
        "base_url",
        "endpoint",
        "auth_token",
        "auth_header",
        "auth_scheme",
        "api_key",
        "network_routing",
    }
)

FRONTEND_AI_SSE_GROUP = "frontend_ai_sse"
AI_STREAM_PREFIXES = ("hypothesis_", "ai_")

WEIGHT_SCOPE_HYPOTHESIS_TYPE = "hypothesis_type"
WEIGHT_POSTERIOR_BASELINE = 1.0
WEIGHT_DECAY = 0.98

DEFAULT_HYPOTHESIS_HORIZON_MIN = 240
DEFAULT_TARGET_MOVE = 0.015

SUPPORTED_HYPOTHESIS_SOURCE_EVENTS = frozenset(
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
    "signal_created": "hypothesis.signal_created",
    "anomaly_detected": "hypothesis.anomaly_detected",
    "decision_generated": "hypothesis.decision_generated",
    "market_regime_changed": "hypothesis.market_regime_changed",
    "portfolio_position_changed": "hypothesis.portfolio_position_changed",
    "portfolio_balance_updated": "hypothesis.portfolio_balance_updated",
}
