from __future__ import annotations

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.settings import get_settings
from src.runtime.streams.publisher import publish_event
from src.apps.market_data.domain import utc_now
from src.apps.market_data.schemas import CoinCreate
from src.apps.market_data.services import create_coin_async, get_coin_by_symbol_async
from src.apps.portfolio.cache import (
    cache_portfolio_balances_async,
    cache_portfolio_state_async,
    read_cached_portfolio_state_async,
)
from src.apps.portfolio.clients import create_exchange_plugin
from src.apps.portfolio.engine import (
    DEFAULT_PORTFOLIO_TIMEFRAME,
    calculate_position_size,
    calculate_stops,
    evaluate_portfolio_action,
    sync_exchange_balances,
)
from src.apps.portfolio.models import ExchangeAccount, PortfolioBalance, PortfolioPosition, PortfolioState
from src.apps.market_data.models import Coin
from src.apps.cross_market.models import Sector
from src.apps.indicators.models import CoinMetrics
from src.apps.signals.models import MarketDecision
from src.apps.patterns.domain.regime import read_regime_details
from src.apps.portfolio.models import PortfolioAction
from src.apps.portfolio.selectors import _latest_market_decisions_subquery, get_portfolio_state, list_portfolio_actions, list_portfolio_positions


async def list_portfolio_positions_async(db: AsyncSession, *, limit: int = 200):
    latest_decisions = _latest_market_decisions_subquery()
    rows = (
        await db.execute(
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
        )
    ).all()
    payload: list[dict[str, object]] = []
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
                "latest_decision_confidence": float(row.latest_decision_confidence)
                if row.latest_decision_confidence is not None
                else None,
                "regime": regime,
                "risk_to_stop": risk_to_stop,
            }
        )
    return payload


async def list_portfolio_actions_async(db: AsyncSession, *, limit: int = 200):
    rows = (
        await db.execute(
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
        )
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


async def get_portfolio_state_async(db: AsyncSession):
    cached = await read_cached_portfolio_state_async()
    if cached is not None:
        return cached
    state = await db.get(PortfolioState, 1)
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
        (
            await db.execute(
                select(func.count()).select_from(PortfolioPosition).where(
                    PortfolioPosition.status.in_(("open", "partial"))
                )
            )
        ).scalar_one()
        or 0
    )
    payload = {
        "total_capital": float(state.total_capital),
        "allocated_capital": float(state.allocated_capital),
        "available_capital": float(state.available_capital),
        "updated_at": state.updated_at.isoformat(),
        "open_positions": open_positions,
        "max_positions": int(get_settings().portfolio_max_positions),
    }
    await cache_portfolio_state_async(payload)
    return payload


async def _ensure_portfolio_state_async(db: AsyncSession) -> PortfolioState:
    state = await db.get(PortfolioState, 1)
    if state is not None:
        return state
    settings = get_settings()
    state = PortfolioState(
        id=1,
        total_capital=float(settings.portfolio_total_capital),
        allocated_capital=0.0,
        available_capital=float(settings.portfolio_total_capital),
    )
    db.add(state)
    await db.flush()
    return state


async def _ensure_coin_for_balance_async(
    db: AsyncSession,
    *,
    symbol: str,
    exchange_name: str,
) -> Coin:
    normalized = symbol.upper()
    coin = await get_coin_by_symbol_async(db, normalized)
    if coin is not None:
        return coin
    return await create_coin_async(
        db,
        CoinCreate(
            symbol=normalized,
            name=normalized,
            asset_type="crypto",
            theme="portfolio",
            source=exchange_name.lower(),
            enabled=False,
        ),
    )


async def _sync_balance_position_async(
    db: AsyncSession,
    *,
    account: ExchangeAccount,
    coin: Coin,
    value_usd: float,
    balance: float,
) -> None:
    position = await db.scalar(
        select(PortfolioPosition)
        .where(
            PortfolioPosition.exchange_account_id == account.id,
            PortfolioPosition.coin_id == coin.id,
            PortfolioPosition.timeframe == DEFAULT_PORTFOLIO_TIMEFRAME,
        )
        .order_by(PortfolioPosition.opened_at.desc(), PortfolioPosition.id.desc())
        .limit(1)
    )
    metrics = await db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin.id))
    entry_price = (
        float(metrics.price_current)
        if metrics is not None and metrics.price_current is not None
        else (value_usd / max(balance, 1e-9) if balance > 0 else 0.0)
    )
    stops = calculate_stops(
        entry_price=entry_price,
        atr=float(metrics.atr_14) if metrics is not None and metrics.atr_14 is not None else None,
    )
    if position is None and value_usd > 0:
        db.add(
            PortfolioPosition(
                coin_id=int(coin.id),
                exchange_account_id=int(account.id),
                source_exchange=account.exchange_name,
                position_type="spot",
                timeframe=DEFAULT_PORTFOLIO_TIMEFRAME,
                entry_price=entry_price,
                position_size=balance,
                position_value=value_usd,
                stop_loss=stops.stop_loss,
                take_profit=stops.take_profit,
                status="open",
            )
        )
        return
    if position is None:
        return
    position.entry_price = entry_price
    position.position_size = balance
    position.position_value = value_usd
    position.stop_loss = stops.stop_loss
    position.take_profit = stops.take_profit
    if value_usd <= 0:
        position.status = "closed"
        position.closed_at = utc_now()
    else:
        position.status = "open"
        position.closed_at = None


def _apply_auto_watch(
    *,
    coin: Coin,
    value_usd: float,
) -> bool:
    settings = get_settings()
    if value_usd < settings.auto_watch_min_position_value:
        return False
    changed = not coin.enabled or not bool(getattr(coin, "auto_watch_enabled", False))
    coin.enabled = True
    coin.auto_watch_enabled = True
    coin.auto_watch_source = "portfolio"
    coin.next_history_sync_at = utc_now()
    return changed


async def _sync_balance_row_async(
    db: AsyncSession,
    *,
    account_id: int,
    exchange_name: str,
    balance_row: dict[str, object],
    emit_events: bool,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    account = await db.get(ExchangeAccount, int(account_id))
    if account is None:
        return None, None
    symbol = str(balance_row.get("symbol", "")).upper()
    if not symbol:
        return None, None
    balance_value = float(balance_row.get("balance", 0.0) or 0.0)
    value_usd = float(balance_row.get("value_usd", 0.0) or 0.0)
    coin = await _ensure_coin_for_balance_async(db, symbol=symbol, exchange_name=exchange_name)
    row = await db.scalar(
        select(PortfolioBalance)
        .where(
            PortfolioBalance.exchange_account_id == account.id,
            PortfolioBalance.symbol == symbol,
        )
        .limit(1)
    )
    previous_value = float(row.value_usd) if row is not None else 0.0
    if row is None:
        row = PortfolioBalance(
            exchange_account_id=int(account.id),
            coin_id=int(coin.id),
            symbol=symbol,
            balance=balance_value,
            value_usd=value_usd,
        )
        db.add(row)
    else:
        row.coin_id = int(coin.id)
        row.balance = balance_value
        row.value_usd = value_usd
        row.updated_at = utc_now()
    await _sync_balance_position_async(
        db,
        account=account,
        coin=coin,
        value_usd=value_usd,
        balance=balance_value,
    )
    auto_watch_enabled = _apply_auto_watch(coin=coin, value_usd=value_usd)
    event_timestamp = utc_now()
    await db.commit()
    if auto_watch_enabled:
        publish_event(
            "coin_auto_watch_enabled",
            {
                "coin_id": int(coin.id),
                "timeframe": DEFAULT_PORTFOLIO_TIMEFRAME,
                "timestamp": event_timestamp,
                "source": account.exchange_name.lower(),
                "symbol": symbol,
                "value_usd": value_usd,
            },
        )
    cached_row = {
        "exchange_account_id": int(account.id),
        "exchange_name": account.exchange_name,
        "account_name": account.account_name,
        "coin_id": int(coin.id),
        "symbol": symbol,
        "balance": balance_value,
        "value_usd": value_usd,
        "auto_watch_enabled": auto_watch_enabled,
    }
    event_payload = None
    if emit_events and abs(previous_value - value_usd) > 1e-9:
        event_payload = {
            "coin_id": int(coin.id),
            "timeframe": DEFAULT_PORTFOLIO_TIMEFRAME,
            "timestamp": event_timestamp,
            "exchange_account_id": int(account.id),
            "exchange_name": account.exchange_name,
            "symbol": symbol,
            "balance": balance_value,
            "value_usd": value_usd,
        }
    item = {
        "exchange_account_id": int(account.id),
        "symbol": symbol,
        "balance": balance_value,
        "value_usd": value_usd,
    }
    return cached_row, event_payload or item


async def _refresh_portfolio_state_async(db: AsyncSession) -> None:
    state = await _ensure_portfolio_state_async(db)
    allocated = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(PortfolioPosition.position_value), 0.0)).where(
                    PortfolioPosition.status.in_(("open", "partial"))
                )
            )
        ).scalar_one()
        or 0.0
    )
    state.allocated_capital = allocated
    state.available_capital = max(float(state.total_capital) - allocated, 0.0)
    state.updated_at = utc_now()
    await db.commit()
    await db.refresh(state)
    open_positions = int(
        (
            await db.execute(
                select(func.count()).select_from(PortfolioPosition).where(
                    PortfolioPosition.status.in_(("open", "partial"))
                )
            )
        ).scalar_one()
        or 0
    )
    await cache_portfolio_state_async(
        {
            "total_capital": float(state.total_capital),
            "allocated_capital": float(state.allocated_capital),
            "available_capital": float(state.available_capital),
            "updated_at": state.updated_at.isoformat(),
            "open_positions": open_positions,
            "max_positions": int(get_settings().portfolio_max_positions),
        }
    )


async def sync_exchange_balances_async(db: AsyncSession, *, emit_events: bool = True) -> dict[str, object]:
    accounts = (
        await db.execute(
            select(ExchangeAccount)
            .where(ExchangeAccount.enabled.is_(True))
            .order_by(ExchangeAccount.exchange_name.asc(), ExchangeAccount.account_name.asc())
        )
    ).scalars().all()
    items: list[dict[str, object]] = []
    cached_rows: list[dict[str, object]] = []
    for account in accounts:
        plugin = create_exchange_plugin(account)
        balances = await plugin.fetch_balances()
        for balance_row in balances:
            cached_row, payload = await _sync_balance_row_async(
                db,
                account_id=int(account.id),
                exchange_name=account.exchange_name,
                balance_row=balance_row,
                emit_events=emit_events,
            )
            if cached_row is None or payload is None:
                continue
            cached_rows.append(cached_row)
            if emit_events and payload.get("timeframe") == DEFAULT_PORTFOLIO_TIMEFRAME:
                publish_event("portfolio_balance_updated", payload)
                publish_event("portfolio_position_changed", payload)
                items.append(
                    {
                        "exchange_account_id": payload["exchange_account_id"],
                        "symbol": payload["symbol"],
                        "balance": payload["balance"],
                        "value_usd": payload["value_usd"],
                    }
                )
            else:
                items.append(payload)
    await cache_portfolio_balances_async(cached_rows)
    await _refresh_portfolio_state_async(db)
    return {
        "status": "ok",
        "accounts": len(accounts),
        "balances": len(items),
        "items": items,
    }


__all__ = [
    "calculate_position_size",
    "calculate_stops",
    "evaluate_portfolio_action",
    "get_portfolio_state",
    "get_portfolio_state_async",
    "list_portfolio_actions",
    "list_portfolio_actions_async",
    "list_portfolio_positions",
    "list_portfolio_positions_async",
    "sync_exchange_balances_async",
    "sync_exchange_balances",
]
