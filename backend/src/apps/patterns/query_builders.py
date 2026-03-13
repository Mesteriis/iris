from __future__ import annotations

from sqlalchemy import and_, select

from src.apps.cross_market.models import Sector
from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.models import Coin
from src.apps.patterns.models import MarketCycle
from src.apps.signals.models import Signal


def signal_select():
    return (
        select(
            Signal.id,
            Signal.coin_id,
            Coin.symbol,
            Coin.name,
            Sector.name.label("sector"),
            Signal.timeframe,
            Signal.signal_type,
            Signal.confidence,
            Signal.priority_score,
            Signal.context_score,
            Signal.regime_alignment,
            Signal.market_regime.label("signal_market_regime"),
            Signal.candle_timestamp,
            Signal.created_at,
            CoinMetrics.market_regime,
            CoinMetrics.market_regime_details,
            MarketCycle.cycle_phase,
            MarketCycle.confidence.label("cycle_confidence"),
        )
        .join(Coin, Coin.id == Signal.coin_id)
        .outerjoin(Sector, Sector.id == Coin.sector_id)
        .outerjoin(CoinMetrics, CoinMetrics.coin_id == Coin.id)
        .outerjoin(
            MarketCycle,
            and_(
                MarketCycle.coin_id == Signal.coin_id,
                MarketCycle.timeframe == Signal.timeframe,
            ),
        )
        .where(Coin.deleted_at.is_(None))
    )


__all__ = ["signal_select"]
