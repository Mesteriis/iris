from __future__ import annotations

from typing import Any

from src.apps.indicators.api.contracts import CoinMetricsRead, MarketCycleRead, MarketFlowRead, MarketRadarRead


def coin_metrics_read(item: Any) -> CoinMetricsRead:
    return CoinMetricsRead.model_validate(item)


def market_cycle_read(item: Any) -> MarketCycleRead:
    return MarketCycleRead.model_validate(item)


def market_radar_read(item: Any) -> MarketRadarRead:
    return MarketRadarRead.model_validate(item)


def market_flow_read(item: Any) -> MarketFlowRead:
    return MarketFlowRead.model_validate(item)


__all__ = ["coin_metrics_read", "market_cycle_read", "market_flow_read", "market_radar_read"]
