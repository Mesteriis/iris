from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.apps.market_data.models import Coin
from app.apps.indicators.models import CoinMetrics
from app.apps.signals.models import MarketDecision
from app.apps.portfolio.models import PortfolioAction
from app.apps.portfolio.models import PortfolioPosition
from app.apps.portfolio.models import PortfolioState
from app.apps.cross_market.models import Sector
from app.apps.patterns.domain.regime import read_regime_details
from app.core.settings import get_settings
from app.apps.portfolio.cache import read_cached_portfolio_state


def _latest_market_decisions_subquery():
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


def list_portfolio_positions(db: Session, *, limit: int = 200) -> Sequence[dict[str, Any]]:
    latest_decisions = _latest_market_decisions_subquery()
    rows = db.execute(
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
        .where(PortfolioPosition.status.in_(("open", "partial")))
        .order_by(PortfolioPosition.position_value.desc(), PortfolioPosition.id.desc())
        .limit(max(limit, 1))
    ).all()
    payload: list[dict[str, Any]] = []
    for row in rows:
        current_price = float(row.price_current or 0.0)
        entry_price = float(row.entry_price or 0.0)
        unrealized_pnl = (current_price - entry_price) * float(row.position_size or 0.0) if current_price and entry_price else 0.0
        detailed = read_regime_details(row.market_regime_details, int(row.timeframe))
        regime = detailed.regime if detailed is not None else row.market_regime
        risk_to_stop = (
            max((entry_price - float(row.stop_loss or 0.0)) / entry_price, 0.0)
            if entry_price and row.stop_loss is not None
            else None
        )
        payload.append(
            {
                "id": int(row.id),
                "coin_id": int(row.coin_id),
                "symbol": str(row.symbol),
                "name": str(row.name),
                "sector": row.sector,
                "exchange_account_id": row.exchange_account_id,
                "source_exchange": row.source_exchange,
                "position_type": str(row.position_type),
                "timeframe": int(row.timeframe),
                "entry_price": entry_price,
                "position_size": float(row.position_size),
                "position_value": float(row.position_value),
                "stop_loss": float(row.stop_loss) if row.stop_loss is not None else None,
                "take_profit": float(row.take_profit) if row.take_profit is not None else None,
                "status": str(row.status),
                "opened_at": row.opened_at,
                "closed_at": row.closed_at,
                "current_price": current_price or None,
                "unrealized_pnl": unrealized_pnl,
                "latest_decision": row.latest_decision,
                "latest_decision_confidence": float(row.latest_decision_confidence) if row.latest_decision_confidence is not None else None,
                "regime": regime,
                "risk_to_stop": risk_to_stop,
            }
        )
    return payload


def list_portfolio_actions(db: Session, *, limit: int = 200) -> Sequence[dict[str, Any]]:
    rows = db.execute(
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
        .order_by(PortfolioAction.created_at.desc(), PortfolioAction.id.desc())
        .limit(max(limit, 1))
    ).all()
    return [
        {
            "id": int(row.id),
            "coin_id": int(row.coin_id),
            "symbol": str(row.symbol),
            "name": str(row.name),
            "action": str(row.action),
            "size": float(row.size),
            "confidence": float(row.confidence),
            "decision_id": int(row.decision_id),
            "market_decision": str(row.market_decision),
            "created_at": row.created_at,
        }
        for row in rows
    ]


def get_portfolio_state(db: Session) -> dict[str, Any]:
    cached = read_cached_portfolio_state()
    if cached is not None:
        return cached
    state = db.get(PortfolioState, 1)
    if state is None:
        return {
            "total_capital": 0.0,
            "allocated_capital": 0.0,
            "available_capital": 0.0,
            "updated_at": None,
            "open_positions": 0,
            "max_positions": 0,
        }
    open_positions = int(
        db.scalar(
            select(func.count()).select_from(PortfolioPosition).where(PortfolioPosition.status.in_(("open", "partial")))
        )
        or 0
    )
    return {
        "total_capital": float(state.total_capital),
        "allocated_capital": float(state.allocated_capital),
        "available_capital": float(state.available_capital),
        "updated_at": state.updated_at.isoformat(),
        "open_positions": open_positions,
        "max_positions": int(get_settings().portfolio_max_positions),
    }
