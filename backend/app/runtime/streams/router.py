from app.runtime.streams.types import (
    ANALYSIS_SCHEDULER_WORKER_GROUP,
    ANOMALY_SECTOR_WORKER_GROUP,
    ANOMALY_WORKER_GROUP,
    CROSS_MARKET_WORKER_GROUP,
    DECISION_WORKER_GROUP,
    FUSION_WORKER_GROUP,
    INDICATOR_WORKER_GROUP,
    NEWS_CORRELATION_WORKER_GROUP,
    NEWS_NORMALIZATION_WORKER_GROUP,
    PATTERN_WORKER_GROUP,
    PORTFOLIO_WORKER_GROUP,
    REGIME_WORKER_GROUP,
)

WORKER_EVENT_TYPES: dict[str, set[str]] = {
    INDICATOR_WORKER_GROUP: {"candle_closed"},
    ANALYSIS_SCHEDULER_WORKER_GROUP: {"indicator_updated"},
    PATTERN_WORKER_GROUP: {"analysis_requested"},
    REGIME_WORKER_GROUP: {"indicator_updated"},
    DECISION_WORKER_GROUP: {
        "pattern_detected",
        "pattern_cluster_detected",
        "market_regime_changed",
        "market_cycle_changed",
        "signal_created",
    },
    FUSION_WORKER_GROUP: {
        "pattern_detected",
        "signal_created",
        "market_regime_changed",
        "correlation_updated",
        "news_symbol_correlation_updated",
    },
    CROSS_MARKET_WORKER_GROUP: {"candle_closed", "indicator_updated"},
    ANOMALY_WORKER_GROUP: {"candle_closed"},
    ANOMALY_SECTOR_WORKER_GROUP: {"anomaly_detected"},
    NEWS_NORMALIZATION_WORKER_GROUP: {"news_item_ingested"},
    NEWS_CORRELATION_WORKER_GROUP: {"news_item_normalized"},
    PORTFOLIO_WORKER_GROUP: {
        "decision_generated",
        "market_regime_changed",
        "portfolio_balance_updated",
        "portfolio_position_changed",
    },
}


def subscribed_event_types(group_name: str) -> set[str]:
    try:
        return WORKER_EVENT_TYPES[group_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported event worker group '{group_name}'.") from exc
