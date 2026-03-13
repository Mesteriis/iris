from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder

from src.apps.indicators.api.contracts import CoinMetricsRead, MarketCycleRead, MarketFlowRead, MarketRadarRead
from src.core.http.analytics import analytical_metadata, latest_timestamp


def coin_metrics_read(item: Any) -> CoinMetricsRead:
    return CoinMetricsRead.model_validate(item)


def market_cycle_read(item: Any) -> MarketCycleRead:
    return MarketCycleRead.model_validate(item)


def market_radar_read(item: Any) -> MarketRadarRead:
    payload = jsonable_encoder(item)
    latest_source_timestamp = latest_timestamp(
        [
            *(row.get("updated_at") for row in payload.get("hot_coins", ())),
            *(row.get("updated_at") for row in payload.get("emerging_coins", ())),
            *(row.get("timestamp") for row in payload.get("regime_changes", ())),
            *(row.get("updated_at") for row in payload.get("volatility_spikes", ())),
        ]
    )
    return MarketRadarRead.model_validate(
        {
            **payload,
            **analytical_metadata(
                source_updated_at=latest_source_timestamp,
                consistency="derived",
                freshness_class="near_real_time",
            ),
        }
    )


def market_flow_read(item: Any) -> MarketFlowRead:
    payload = jsonable_encoder(item)
    latest_source_timestamp = latest_timestamp(
        [
            *(row.get("timestamp") for row in payload.get("leaders", ())),
            *(row.get("updated_at") for row in payload.get("relations", ())),
            *(row.get("updated_at") for row in payload.get("sectors", ())),
            *(row.get("timestamp") for row in payload.get("rotations", ())),
        ]
    )
    return MarketFlowRead.model_validate(
        {
            **payload,
            **analytical_metadata(
                source_updated_at=latest_source_timestamp,
                consistency="derived",
                freshness_class="near_real_time",
            ),
        }
    )


__all__ = ["coin_metrics_read", "market_cycle_read", "market_flow_read", "market_radar_read"]
