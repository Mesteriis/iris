from __future__ import annotations

from dataclasses import dataclass

from src.apps.market_data.models import Coin
from src.apps.indicators.models import CoinMetrics

ROTATION_STATES = [
    "btc_dominance_rising",
    "btc_dominance_falling",
    "sector_leadership_change",
]
CAPITAL_WAVES = [
    "btc",
    "large_caps",
    "sector_leaders",
    "mid_caps",
    "micro_caps",
]


@dataclass(slots=True, frozen=True)
class SectorNarrative:
    timeframe: int
    top_sector: str | None
    rotation_state: str | None
    btc_dominance: float | None
    capital_wave: str | None


def _capital_wave_bucket(
    coin: Coin,
    metrics: CoinMetrics | None,
    *,
    top_sector_id: int | None,
) -> str:
    market_cap = float(metrics.market_cap or 0.0) if metrics is not None else 0.0
    if coin.symbol == "BTCUSD":
        return "btc"
    if market_cap >= 15_000_000_000:
        return "large_caps"
    if top_sector_id is not None and coin.sector_id == top_sector_id:
        return "sector_leaders"
    if market_cap >= 1_000_000_000:
        return "mid_caps"
    return "micro_caps"


__all__ = ["CAPITAL_WAVES", "ROTATION_STATES", "SectorNarrative", "_capital_wave_bucket"]
