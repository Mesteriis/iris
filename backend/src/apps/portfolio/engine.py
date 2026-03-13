from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.runtime.streams.publisher import publish_event
from src.apps.portfolio.clients import create_exchange_plugin
from src.apps.market_data.models import Coin
from src.apps.indicators.models import CoinMetrics
from src.apps.portfolio.models import ExchangeAccount
from src.apps.signals.models import MarketDecision
from src.apps.portfolio.models import PortfolioAction
from src.apps.portfolio.models import PortfolioBalance
from src.apps.portfolio.models import PortfolioPosition
from src.apps.portfolio.models import PortfolioState
from src.apps.portfolio.support import (
    DEFAULT_PORTFOLIO_TIMEFRAME,
    PORTFOLIO_ACTIONS,
    SIMULATION_EXCHANGE,
    calculate_position_size,
    calculate_stops,
    clamp_portfolio_value as _clamp,
)
from src.apps.market_data.domain import utc_now
from src.apps.portfolio.cache import cache_portfolio_balances, cache_portfolio_state
from src.apps.market_data.schemas import CoinCreate
from src.apps.portfolio.read_models import portfolio_state_read_model_from_mapping
from src.apps.portfolio.services import (
    PortfolioActionEvaluationResult,
    PortfolioSyncItem,
    PortfolioSyncResult,
)
from src.core.db.persistence import PERSISTENCE_LOGGER, sanitize_log_value

PORTFOLIO_POSITION_STATUSES = {"open", "closed", "partial"}


def _log_compat(level: int, event: str, /, *, component_type: str, component: str, **fields: Any) -> None:
    PERSISTENCE_LOGGER.log(
        level,
        event,
        extra={
            "persistence": {
                "event": event,
                "component_type": component_type,
                "domain": "portfolio",
                "component": component,
                **{key: sanitize_log_value(value) for key, value in fields.items()},
            }
        },
    )


def _open_positions(db: Session) -> list[PortfolioPosition]:
    return db.scalars(
        select(PortfolioPosition)
        .where(PortfolioPosition.status.in_(("open", "partial")))
        .order_by(PortfolioPosition.position_value.desc(), PortfolioPosition.id.asc())
    ).all()


def _latest_market_decision(db: Session, *, coin_id: int, timeframe: int) -> MarketDecision | None:
    return db.scalar(
        select(MarketDecision)
        .where(MarketDecision.coin_id == coin_id, MarketDecision.timeframe == timeframe)
        .order_by(MarketDecision.created_at.desc(), MarketDecision.id.desc())
        .limit(1)
    )


def _ensure_portfolio_state_impl(db: Session) -> PortfolioState:
    settings = get_settings()
    state = db.get(PortfolioState, 1)
    if state is None:
        state = PortfolioState(
            id=1,
            total_capital=float(settings.portfolio_total_capital),
            allocated_capital=0.0,
            available_capital=float(settings.portfolio_total_capital),
        )
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def _refresh_portfolio_state_impl(db: Session) -> PortfolioState:
    state = _ensure_portfolio_state_impl(db)
    allocated = float(
        db.scalar(
            select(func.coalesce(func.sum(PortfolioPosition.position_value), 0.0)).where(
                PortfolioPosition.status.in_(("open", "partial"))
            )
        )
        or 0.0
    )
    state.allocated_capital = allocated
    state.available_capital = max(float(state.total_capital) - allocated, 0.0)
    state.updated_at = utc_now()
    db.commit()
    db.refresh(state)
    cache_portfolio_state(
        {
            "total_capital": float(state.total_capital),
            "allocated_capital": float(state.allocated_capital),
            "available_capital": float(state.available_capital),
            "updated_at": state.updated_at.isoformat(),
            "open_positions": len(_open_positions(db)),
            "max_positions": int(get_settings().portfolio_max_positions),
        }
    )
    return state


def _sector_exposure_ratio(db: Session, *, sector_id: int | None, total_capital: float) -> float:
    if sector_id is None or total_capital <= 0:
        return 0.0
    value = float(
        db.scalar(
            select(func.coalesce(func.sum(PortfolioPosition.position_value), 0.0))
            .join(Coin, Coin.id == PortfolioPosition.coin_id)
            .where(
                PortfolioPosition.status.in_(("open", "partial")),
                Coin.sector_id == sector_id,
            )
        )
        or 0.0
    )
    return value / total_capital


def _existing_position(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
) -> PortfolioPosition | None:
    return db.scalar(
        select(PortfolioPosition)
        .where(
            PortfolioPosition.coin_id == coin_id,
            PortfolioPosition.timeframe == timeframe,
            PortfolioPosition.status.in_(("open", "partial")),
        )
        .order_by(PortfolioPosition.position_value.desc(), PortfolioPosition.id.asc())
        .limit(1)
    )


def _record_action(
    db: Session,
    *,
    coin_id: int,
    action: str,
    size: float,
    confidence: float,
    decision_id: int,
) -> PortfolioAction:
    row = PortfolioAction(
        coin_id=coin_id,
        action=action,
        size=max(size, 0.0),
        confidence=_clamp(confidence, 0.0, 1.0),
        decision_id=decision_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _rebalance_existing_position(
    *,
    position: PortfolioPosition,
    target_value: float,
    entry_price: float,
    decision_confidence: float,
    atr_14: float | None,
) -> tuple[str, float]:
    stops = calculate_stops(entry_price=entry_price, atr=atr_14)
    current_value = float(position.position_value)
    if target_value <= 0:
        position.status = "closed"
        position.closed_at = utc_now()
        position.position_value = 0.0
        position.position_size = 0.0
        position.stop_loss = None
        position.take_profit = None
        return "CLOSE_POSITION", current_value
    if current_value <= 0:
        position.entry_price = entry_price
        position.position_value = target_value
        position.position_size = target_value / max(entry_price, 1e-9)
        position.stop_loss = stops.stop_loss
        position.take_profit = stops.take_profit
        position.status = "open"
        position.closed_at = None
        return "OPEN_POSITION", target_value
    delta = target_value - current_value
    position.position_value = target_value
    position.position_size = target_value / max(entry_price, 1e-9)
    position.entry_price = entry_price
    position.stop_loss = stops.stop_loss
    position.take_profit = stops.take_profit
    if delta > current_value * 0.1:
        return "INCREASE_POSITION", delta
    if delta < -(current_value * 0.1):
        position.status = "partial"
        return "REDUCE_POSITION", abs(delta)
    return "HOLD_POSITION", 0.0


def _evaluate_portfolio_action_impl(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    decision: MarketDecision | None = None,
    emit_events: bool = True,
) -> dict[str, object]:
    settings = get_settings()
    state = _refresh_portfolio_state_impl(db)
    decision_row = decision or _latest_market_decision(db, coin_id=coin_id, timeframe=timeframe)
    if decision_row is None:
        return {"status": "skipped", "reason": "decision_not_found", "coin_id": coin_id, "timeframe": timeframe}

    coin = db.get(Coin, coin_id)
    metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id))
    if coin is None or metrics is None or metrics.price_current is None:
        return {"status": "skipped", "reason": "coin_metrics_not_found", "coin_id": coin_id, "timeframe": timeframe}

    existing = _existing_position(db, coin_id=coin_id, timeframe=timeframe)
    open_positions = _open_positions(db)
    open_count = len(open_positions)
    sector_ratio = _sector_exposure_ratio(
        db,
        sector_id=coin.sector_id,
        total_capital=float(state.total_capital),
    )
    size_context = calculate_position_size(
        total_capital=float(state.total_capital),
        available_capital=float(state.available_capital) + (float(existing.position_value) if existing is not None else 0.0),
        decision_confidence=float(decision_row.confidence),
        regime=metrics.market_regime,
        price_current=float(metrics.price_current),
        atr_14=float(metrics.atr_14) if metrics.atr_14 is not None else None,
    )
    target_value = float(size_context["position_value"])
    if existing is None and open_count >= settings.portfolio_max_positions:
        target_value = 0.0
    if sector_ratio >= settings.portfolio_max_sector_exposure and existing is None:
        target_value = 0.0

    action = "HOLD_POSITION"
    action_size = 0.0
    if decision_row.decision == "BUY":
        if existing is None:
            if target_value <= 0:
                action = "HOLD_POSITION"
            else:
                stops = calculate_stops(
                    entry_price=float(metrics.price_current),
                    atr=float(metrics.atr_14) if metrics.atr_14 is not None else None,
                )
                existing = PortfolioPosition(
                    coin_id=coin_id,
                    exchange_account_id=None,
                    source_exchange=SIMULATION_EXCHANGE,
                    position_type="long",
                    timeframe=timeframe,
                    entry_price=float(metrics.price_current),
                    position_size=target_value / max(float(metrics.price_current), 1e-9),
                    position_value=target_value,
                    stop_loss=stops.stop_loss,
                    take_profit=stops.take_profit,
                    status="open",
                    closed_at=None,
                )
                db.add(existing)
                action = "OPEN_POSITION"
                action_size = target_value
        else:
            action, action_size = _rebalance_existing_position(
                position=existing,
                target_value=target_value if target_value > 0 else float(existing.position_value),
                entry_price=float(metrics.price_current),
                decision_confidence=float(decision_row.confidence),
                atr_14=float(metrics.atr_14) if metrics.atr_14 is not None else None,
            )
    elif decision_row.decision == "SELL":
        if existing is not None:
            target_value = 0.0 if float(decision_row.confidence) >= 0.55 else float(existing.position_value) * 0.5
            action, action_size = _rebalance_existing_position(
                position=existing,
                target_value=target_value,
                entry_price=float(metrics.price_current),
                decision_confidence=float(decision_row.confidence),
                atr_14=float(metrics.atr_14) if metrics.atr_14 is not None else None,
            )
        else:
            action = "HOLD_POSITION"
    else:
        action = "HOLD_POSITION"
        action_size = 0.0

    db.commit()
    action_row = _record_action(
        db,
        coin_id=coin_id,
        action=action,
        size=action_size,
        confidence=float(decision_row.confidence),
        decision_id=int(decision_row.id),
    )
    state = _refresh_portfolio_state_impl(db)
    if emit_events:
        if action == "OPEN_POSITION":
            publish_event(
                "portfolio_position_opened",
                {
                    "coin_id": coin_id,
                    "timeframe": timeframe,
                    "timestamp": action_row.created_at,
                    "action_id": action_row.id,
                    "decision_id": decision_row.id,
                    "size": action_size,
                    "confidence": float(decision_row.confidence),
                },
            )
        elif action == "CLOSE_POSITION":
            publish_event(
                "portfolio_position_closed",
                {
                    "coin_id": coin_id,
                    "timeframe": timeframe,
                    "timestamp": action_row.created_at,
                    "action_id": action_row.id,
                    "decision_id": decision_row.id,
                    "size": action_size,
                    "confidence": float(decision_row.confidence),
                },
            )
        elif action in {"INCREASE_POSITION", "REDUCE_POSITION"}:
            publish_event(
                "portfolio_rebalanced",
                {
                    "coin_id": coin_id,
                    "timeframe": timeframe,
                    "timestamp": action_row.created_at,
                    "action_id": action_row.id,
                    "decision_id": decision_row.id,
                    "size": action_size,
                    "confidence": float(decision_row.confidence),
                },
            )
    return {
        "status": "ok",
        "coin_id": coin_id,
        "timeframe": timeframe,
        "decision": decision_row.decision,
        "action": action,
        "size": action_size,
        "portfolio_state": {
            "total_capital": float(state.total_capital),
            "allocated_capital": float(state.allocated_capital),
            "available_capital": float(state.available_capital),
            "updated_at": state.updated_at.isoformat(),
            "open_positions": len(_open_positions(db)),
            "max_positions": int(get_settings().portfolio_max_positions),
        },
    }


def _ensure_coin_for_balance(db: Session, *, symbol: str, exchange_name: str) -> Coin:
    from src.apps.market_data.service_layer import create_coin, get_coin_by_symbol

    normalized = symbol.upper()
    coin = get_coin_by_symbol(db, normalized)
    if coin is not None:
        return coin
    return create_coin(
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


def _maybe_auto_watch_coin(db: Session, *, coin: Coin, value_usd: float, exchange_name: str) -> bool:
    settings = get_settings()
    if value_usd < settings.auto_watch_min_position_value:
        return False
    changed = not coin.enabled or not bool(getattr(coin, "auto_watch_enabled", False))
    coin.enabled = True
    coin.auto_watch_enabled = True
    coin.auto_watch_source = "portfolio"
    coin.next_history_sync_at = utc_now()
    db.commit()
    if changed:
        publish_event(
            "coin_auto_watch_enabled",
            {
                "coin_id": coin.id,
                "timeframe": DEFAULT_PORTFOLIO_TIMEFRAME,
                "timestamp": utc_now(),
                "source": exchange_name.lower(),
                "symbol": coin.symbol,
                "value_usd": value_usd,
            },
        )
    return changed


def _sync_balance_position(
    db: Session,
    *,
    account: ExchangeAccount,
    coin: Coin,
    value_usd: float,
    balance: float,
) -> None:
    position = db.scalar(
        select(PortfolioPosition)
        .where(
            PortfolioPosition.exchange_account_id == account.id,
            PortfolioPosition.coin_id == coin.id,
            PortfolioPosition.timeframe == DEFAULT_PORTFOLIO_TIMEFRAME,
        )
        .order_by(PortfolioPosition.opened_at.desc(), PortfolioPosition.id.desc())
        .limit(1)
    )
    metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin.id))
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
                coin_id=coin.id,
                exchange_account_id=account.id,
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
    elif position is not None:
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


def _sync_exchange_balances_impl(db: Session, *, emit_events: bool = True) -> dict[str, object]:
    accounts = db.scalars(
        select(ExchangeAccount)
        .where(ExchangeAccount.enabled.is_(True))
        .order_by(ExchangeAccount.exchange_name.asc(), ExchangeAccount.account_name.asc())
    ).all()
    items: list[dict[str, object]] = []
    cached_rows: list[dict[str, object]] = []
    for account in accounts:
        plugin = create_exchange_plugin(account)
        # NOTE:
        # This synchronous bridge remains intentionally for legacy/test code.
        # Runtime task orchestration uses the async portfolio service instead.
        balances = asyncio.run(plugin.fetch_balances())
        for balance_row in balances:
            symbol = str(balance_row.get("symbol", "")).upper()
            if not symbol:
                continue
            balance_value = float(balance_row.get("balance", 0.0) or 0.0)
            value_usd = float(balance_row.get("value_usd", 0.0) or 0.0)
            coin = _ensure_coin_for_balance(db, symbol=symbol, exchange_name=account.exchange_name)
            row = db.scalar(
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
                    exchange_account_id=account.id,
                    coin_id=coin.id,
                    symbol=symbol,
                    balance=balance_value,
                    value_usd=value_usd,
                )
                db.add(row)
            else:
                row.coin_id = coin.id
                row.balance = balance_value
                row.value_usd = value_usd
                row.updated_at = utc_now()
            _sync_balance_position(
                db,
                account=account,
                coin=coin,
                value_usd=value_usd,
                balance=balance_value,
            )
            auto_watch_enabled = _maybe_auto_watch_coin(
                db,
                coin=coin,
                value_usd=value_usd,
                exchange_name=account.exchange_name,
            )
            db.commit()
            cached_rows.append(
                {
                    "exchange_account_id": account.id,
                    "exchange_name": account.exchange_name,
                    "account_name": account.account_name,
                    "coin_id": coin.id,
                    "symbol": symbol,
                    "balance": balance_value,
                    "value_usd": value_usd,
                    "auto_watch_enabled": auto_watch_enabled,
                }
            )
            if emit_events and abs(previous_value - value_usd) > 1e-9:
                event_payload = {
                    "coin_id": coin.id,
                    "timeframe": DEFAULT_PORTFOLIO_TIMEFRAME,
                    "timestamp": utc_now(),
                    "exchange_account_id": account.id,
                    "exchange_name": account.exchange_name,
                    "symbol": symbol,
                    "balance": balance_value,
                    "value_usd": value_usd,
                }
                publish_event("portfolio_balance_updated", event_payload)
                publish_event("portfolio_position_changed", event_payload)
            items.append(
                {
                    "exchange_account_id": account.id,
                    "symbol": symbol,
                    "balance": balance_value,
                    "value_usd": value_usd,
                }
            )
    cache_portfolio_balances(cached_rows)
    state = _refresh_portfolio_state_impl(db)
    return {
        "status": "ok",
        "accounts": len(accounts),
        "balances": len(items),
        "items": items,
        "portfolio_state": {
            "total_capital": float(state.total_capital),
            "allocated_capital": float(state.allocated_capital),
            "available_capital": float(state.available_capital),
            "updated_at": state.updated_at.isoformat(),
            "open_positions": len(_open_positions(db)),
            "max_positions": int(get_settings().portfolio_max_positions),
        },
    }


class PortfolioCompatibilityService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _log(self, level: int, event: str, /, **fields: Any) -> None:
        _log_compat(
            level,
            event,
            component_type="compatibility_service",
            component="PortfolioCompatibilityService",
            **fields,
        )

    def evaluate_portfolio_action(
        self,
        *,
        coin_id: int,
        timeframe: int,
        decision: MarketDecision | None = None,
        emit_events: bool = True,
    ) -> dict[str, object]:
        result = _evaluate_portfolio_action_impl(
            self._db,
            coin_id=coin_id,
            timeframe=timeframe,
            decision=decision,
            emit_events=emit_events,
        )
        state_payload = result.get("portfolio_state")
        return PortfolioActionEvaluationResult(
            status=str(result["status"]),
            coin_id=int(result["coin_id"]),
            timeframe=int(result["timeframe"]),
            reason=str(result["reason"]) if result.get("reason") is not None else None,
            decision=str(result["decision"]) if result.get("decision") is not None else None,
            action=str(result["action"]) if result.get("action") is not None else None,
            size=float(result.get("size") or 0.0),
            portfolio_state=(
                portfolio_state_read_model_from_mapping(
                    {
                        "total_capital": float(state_payload.get("total_capital", 0.0)),
                        "allocated_capital": float(state_payload.get("allocated_capital", 0.0)),
                        "available_capital": float(state_payload.get("available_capital", 0.0)),
                        "updated_at": state_payload.get("updated_at"),
                        "open_positions": int(state_payload.get("open_positions", 0)),
                        "max_positions": int(state_payload.get("max_positions", 0)),
                    }
                )
                if isinstance(state_payload, dict)
                else None
            ),
        ).to_payload()

    def sync_exchange_balances(self, *, emit_events: bool = True) -> dict[str, object]:
        result = _sync_exchange_balances_impl(
            self._db,
            emit_events=emit_events,
        )
        state_payload = result.get("portfolio_state") or {
            "total_capital": 0.0,
            "allocated_capital": 0.0,
            "available_capital": 0.0,
            "updated_at": None,
            "open_positions": 0,
            "max_positions": 0,
        }
        return PortfolioSyncResult(
            status=str(result["status"]),
            accounts=int(result.get("accounts") or 0),
            items=tuple(
                PortfolioSyncItem(
                    exchange_account_id=int(item["exchange_account_id"]),
                    symbol=str(item["symbol"]),
                    balance=float(item["balance"]),
                    value_usd=float(item["value_usd"]),
                )
                for item in result.get("items", [])
                if isinstance(item, dict)
            ),
            cached_rows=tuple(),
            state=portfolio_state_read_model_from_mapping(state_payload),
            pending_events=tuple(),
        ).to_payload()


def ensure_portfolio_state(db: Session) -> PortfolioState:
    _log_compat(
        logging.WARNING,
        "compat.ensure_portfolio_state.deprecated",
        component_type="compatibility_service",
        component="ensure_portfolio_state",
        mode="write",
    )
    return _ensure_portfolio_state_impl(db)


def refresh_portfolio_state(db: Session) -> PortfolioState:
    _log_compat(
        logging.WARNING,
        "compat.refresh_portfolio_state.deprecated",
        component_type="compatibility_service",
        component="refresh_portfolio_state",
        mode="write",
    )
    return _refresh_portfolio_state_impl(db)


def evaluate_portfolio_action(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    decision: MarketDecision | None = None,
    emit_events: bool = True,
) -> dict[str, object]:
    service = PortfolioCompatibilityService(db)
    service._log(
        logging.WARNING,
        "compat.evaluate_portfolio_action.deprecated",
        mode="write",
        coin_id=coin_id,
        timeframe=timeframe,
        emit_events=emit_events,
    )
    return service.evaluate_portfolio_action(
        coin_id=coin_id,
        timeframe=timeframe,
        decision=decision,
        emit_events=emit_events,
    )


def sync_exchange_balances(db: Session, *, emit_events: bool = True) -> dict[str, object]:
    service = PortfolioCompatibilityService(db)
    service._log(
        logging.WARNING,
        "compat.sync_exchange_balances.deprecated",
        mode="write",
        emit_events=emit_events,
    )
    return service.sync_exchange_balances(emit_events=emit_events)


__all__ = [
    "PORTFOLIO_POSITION_STATUSES",
    "PortfolioCompatibilityService",
    "_ensure_coin_for_balance",
    "_maybe_auto_watch_coin",
    "_rebalance_existing_position",
    "_sync_balance_position",
    "calculate_position_size",
    "calculate_stops",
    "ensure_portfolio_state",
    "evaluate_portfolio_action",
    "refresh_portfolio_state",
    "sync_exchange_balances",
]
