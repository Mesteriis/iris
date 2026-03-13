from __future__ import annotations

from sqlalchemy import and_, func, select

from src.apps.cross_market.models import Sector
from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.models import Coin
from src.apps.portfolio.models import PortfolioAction, PortfolioPosition
from src.apps.signals.models import MarketDecision


def latest_market_decisions_subquery():
    return (
        select(
            MarketDecision.coin_id.label("coin_id"),
            MarketDecision.timeframe.label("timeframe"),
            MarketDecision.decision.label("decision"),
            MarketDecision.confidence.label("confidence"),
            func.row_number()
            .over(
                partition_by=(MarketDecision.coin_id, MarketDecision.timeframe),
                order_by=(MarketDecision.created_at.desc(), MarketDecision.id.desc()),
            )
            .label("decision_rank"),
        )
        .subquery()
    )


def portfolio_positions_select():
    latest_decisions = latest_market_decisions_subquery()
    return (
        select(
            PortfolioPosition.id,
            PortfolioPosition.coin_id,
            Coin.symbol,
            Coin.name,
            Sector.name.label("sector"),
            PortfolioPosition.exchange_account_id,
            PortfolioPosition.source_exchange,
            PortfolioPosition.position_type,
            PortfolioPosition.timeframe,
            PortfolioPosition.entry_price,
            PortfolioPosition.position_size,
            PortfolioPosition.position_value,
            PortfolioPosition.stop_loss,
            PortfolioPosition.take_profit,
            PortfolioPosition.status,
            PortfolioPosition.opened_at,
            PortfolioPosition.closed_at,
            CoinMetrics.price_current,
            CoinMetrics.market_regime,
            CoinMetrics.market_regime_details,
            latest_decisions.c.decision.label("latest_decision"),
            latest_decisions.c.confidence.label("latest_decision_confidence"),
        )
        .join(Coin, Coin.id == PortfolioPosition.coin_id)
        .outerjoin(Sector, Sector.id == Coin.sector_id)
        .outerjoin(CoinMetrics, CoinMetrics.coin_id == PortfolioPosition.coin_id)
        .outerjoin(
            latest_decisions,
            and_(
                latest_decisions.c.coin_id == PortfolioPosition.coin_id,
                latest_decisions.c.timeframe == PortfolioPosition.timeframe,
                latest_decisions.c.decision_rank == 1,
            ),
        )
    )


def portfolio_actions_select():
    return (
        select(
            PortfolioAction.id,
            PortfolioAction.coin_id,
            Coin.symbol,
            Coin.name,
            PortfolioAction.action,
            PortfolioAction.size,
            PortfolioAction.confidence,
            PortfolioAction.decision_id,
            MarketDecision.decision.label("market_decision"),
            PortfolioAction.created_at,
        )
        .join(Coin, Coin.id == PortfolioAction.coin_id)
        .join(MarketDecision, MarketDecision.id == PortfolioAction.decision_id)
    )


__all__ = [
    "latest_market_decisions_subquery",
    "portfolio_actions_select",
    "portfolio_positions_select",
]
