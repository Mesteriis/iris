from typing import Any

from sqlalchemy import and_, case, select

from src.apps.cross_market.models import Sector
from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.models import Coin
from src.apps.patterns.models import MarketCycle
from src.apps.signals.models import Signal


def signal_select() -> Any:
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


def pattern_signal_ordering() -> Any:
    signal_kind_order = case(
        (Signal.signal_type.like("pattern_hierarchy_%"), 2),
        (Signal.signal_type.like("pattern_cluster_%"), 1),
        else_=0,
    )
    return (
        Signal.candle_timestamp.desc(),
        signal_kind_order.asc(),
        Signal.confidence.desc(),
        Signal.created_at.desc(),
        Signal.signal_type.asc(),
    )


__all__ = ["pattern_signal_ordering", "signal_select"]
