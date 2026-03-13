from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.apps.market_data.domain import utc_now
from src.apps.market_data.models import Coin
from src.apps.market_data.repositories import CoinMetricsRepository, CoinRepository
from src.apps.portfolio.cache import cache_portfolio_balances_async, cache_portfolio_state_async
from src.apps.portfolio.clients import create_exchange_plugin
from src.apps.portfolio.support import (
    DEFAULT_PORTFOLIO_TIMEFRAME,
    PORTFOLIO_ACTIONS,
    SIMULATION_EXCHANGE,
    calculate_position_size,
    calculate_stops,
)
from src.apps.portfolio.models import ExchangeAccount, PortfolioAction, PortfolioBalance, PortfolioPosition, PortfolioState
from src.apps.portfolio.read_models import PortfolioStateReadModel
from src.apps.portfolio.repositories import ExchangeAccountRepository, PortfolioRepository
from src.apps.signals.models import MarketDecision
from src.core.db.persistence import PersistenceComponent
from src.core.db.uow import BaseAsyncUnitOfWork
from src.core.settings import get_settings
from src.runtime.streams.publisher import publish_event


@dataclass(slots=True, frozen=True)
class PortfolioSyncItem:
    exchange_account_id: int
    symbol: str
    balance: float
    value_usd: float

    def to_payload(self) -> dict[str, object]:
        return {
            "exchange_account_id": self.exchange_account_id,
            "symbol": self.symbol,
            "balance": self.balance,
            "value_usd": self.value_usd,
        }


@dataclass(slots=True, frozen=True)
class PortfolioCachedBalanceRow:
    exchange_account_id: int
    exchange_name: str
    account_name: str
    coin_id: int
    symbol: str
    balance: float
    value_usd: float
    auto_watch_enabled: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "exchange_account_id": self.exchange_account_id,
            "exchange_name": self.exchange_name,
            "account_name": self.account_name,
            "coin_id": self.coin_id,
            "symbol": self.symbol,
            "balance": self.balance,
            "value_usd": self.value_usd,
            "auto_watch_enabled": self.auto_watch_enabled,
        }


@dataclass(slots=True, frozen=True)
class PortfolioPendingEvent:
    event_type: str
    payload: dict[str, object]


@dataclass(slots=True, frozen=True)
class PortfolioSyncResult:
    status: str
    accounts: int
    items: tuple[PortfolioSyncItem, ...]
    cached_rows: tuple[PortfolioCachedBalanceRow, ...]
    state: PortfolioStateReadModel
    pending_events: tuple[PortfolioPendingEvent, ...]

    @property
    def balances(self) -> int:
        return len(self.items)

    def to_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "accounts": self.accounts,
            "balances": self.balances,
            "items": [item.to_payload() for item in self.items],
        }


@dataclass(slots=True, frozen=True)
class PortfolioActionEvaluationResult:
    status: str
    coin_id: int
    timeframe: int
    reason: str | None = None
    decision: str | None = None
    action: str | None = None
    size: float = 0.0
    portfolio_state: PortfolioStateReadModel | None = None
    pending_events: tuple[PortfolioPendingEvent, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status,
            "coin_id": self.coin_id,
            "timeframe": self.timeframe,
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.decision is not None:
            payload["decision"] = self.decision
        if self.action is not None:
            payload["action"] = self.action
        if self.status == "ok":
            payload["size"] = float(self.size)
            payload["portfolio_state"] = (
                {
                    "total_capital": float(self.portfolio_state.total_capital),
                    "allocated_capital": float(self.portfolio_state.allocated_capital),
                    "available_capital": float(self.portfolio_state.available_capital),
                }
                if self.portfolio_state is not None
                else None
            )
        return payload


@dataclass(slots=True, frozen=True)
class _BalanceSyncOutcome:
    item: PortfolioSyncItem
    cached_row: PortfolioCachedBalanceRow
    pending_events: tuple[PortfolioPendingEvent, ...]


class PortfolioSideEffectDispatcher:
    async def apply_sync_result(self, result: PortfolioSyncResult) -> None:
        await cache_portfolio_balances_async([row.to_payload() for row in result.cached_rows])
        await cache_portfolio_state_async(
            {
                "total_capital": result.state.total_capital,
                "allocated_capital": result.state.allocated_capital,
                "available_capital": result.state.available_capital,
                "updated_at": result.state.updated_at,
                "open_positions": result.state.open_positions,
                "max_positions": result.state.max_positions,
            }
        )
        for event in result.pending_events:
            publish_event(event.event_type, event.payload)

    async def apply_action_result(self, result: PortfolioActionEvaluationResult) -> None:
        if result.portfolio_state is not None:
            await cache_portfolio_state_async(
                {
                    "total_capital": result.portfolio_state.total_capital,
                    "allocated_capital": result.portfolio_state.allocated_capital,
                    "available_capital": result.portfolio_state.available_capital,
                    "updated_at": result.portfolio_state.updated_at,
                    "open_positions": result.portfolio_state.open_positions,
                    "max_positions": result.portfolio_state.max_positions,
                }
            )
        for event in result.pending_events:
            publish_event(event.event_type, event.payload)


class PortfolioService(PersistenceComponent):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(
            uow.session,
            component_type="service",
            domain="portfolio",
            component_name="PortfolioService",
        )
        self._uow = uow
        self._accounts = ExchangeAccountRepository(uow.session)
        self._portfolio = PortfolioRepository(uow.session)
        self._coins = CoinRepository(uow.session)
        self._coin_metrics = CoinMetricsRepository(uow.session)

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(value, upper))

    @staticmethod
    def _rebalance_position(
        *,
        position: PortfolioPosition,
        target_value: float,
        entry_price: float,
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

    async def evaluate_portfolio_action(
        self,
        *,
        coin_id: int,
        timeframe: int,
        decision: MarketDecision | None = None,
        emit_events: bool = True,
    ) -> PortfolioActionEvaluationResult:
        self._log_debug(
            "service.evaluate_portfolio_action",
            mode="write",
            coin_id=coin_id,
            timeframe=timeframe,
            emit_events=emit_events,
        )
        settings = get_settings()
        state = await self._refresh_portfolio_state()
        decision_row = decision or await self._portfolio.get_latest_market_decision(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
        )
        if decision_row is None:
            self._log_debug(
                "service.evaluate_portfolio_action.result",
                mode="write",
                status="skipped",
                reason="decision_not_found",
                coin_id=coin_id,
                timeframe=timeframe,
            )
            return PortfolioActionEvaluationResult(
                status="skipped",
                reason="decision_not_found",
                coin_id=int(coin_id),
                timeframe=int(timeframe),
            )

        coin = await self._coins.get_by_id(int(coin_id))
        metrics = await self._portfolio.get_coin_metrics(coin_id=int(coin_id))
        if coin is None or metrics is None or metrics.price_current is None:
            self._log_debug(
                "service.evaluate_portfolio_action.result",
                mode="write",
                status="skipped",
                reason="coin_metrics_not_found",
                coin_id=coin_id,
                timeframe=timeframe,
            )
            return PortfolioActionEvaluationResult(
                status="skipped",
                reason="coin_metrics_not_found",
                coin_id=int(coin_id),
                timeframe=int(timeframe),
            )

        existing = await self._portfolio.get_open_position(coin_id=int(coin_id), timeframe=int(timeframe))
        open_count = await self._portfolio.count_open_positions()
        sector_ratio = 0.0
        if coin.sector_id is not None:
            sector_ratio = await self._portfolio.sum_sector_position_value(sector_id=int(coin.sector_id)) / max(
                float(state.total_capital), 1e-9
            )

        size_context = calculate_position_size(
            total_capital=float(state.total_capital),
            available_capital=float(state.available_capital)
            + (float(existing.position_value) if existing is not None else 0.0),
            decision_confidence=float(decision_row.confidence),
            regime=metrics.market_regime,
            price_current=float(metrics.price_current),
            atr_14=float(metrics.atr_14) if metrics.atr_14 is not None else None,
        )
        target_value = float(size_context["position_value"])
        if existing is None and open_count >= settings.portfolio_max_positions:
            target_value = 0.0
        if existing is None and sector_ratio >= settings.portfolio_max_sector_exposure:
            target_value = 0.0

        action = "HOLD_POSITION"
        action_size = 0.0
        if decision_row.decision == "BUY":
            if existing is None:
                if target_value > 0:
                    stops = calculate_stops(
                        entry_price=float(metrics.price_current),
                        atr=float(metrics.atr_14) if metrics.atr_14 is not None else None,
                    )
                    existing = await self._portfolio.add_position(
                        PortfolioPosition(
                            coin_id=int(coin_id),
                            exchange_account_id=None,
                            source_exchange=SIMULATION_EXCHANGE,
                            position_type="long",
                            timeframe=int(timeframe),
                            entry_price=float(metrics.price_current),
                            position_size=target_value / max(float(metrics.price_current), 1e-9),
                            position_value=target_value,
                            stop_loss=stops.stop_loss,
                            take_profit=stops.take_profit,
                            status="open",
                            closed_at=None,
                        )
                    )
                    del existing
                    action = "OPEN_POSITION"
                    action_size = target_value
            else:
                action, action_size = self._rebalance_position(
                    position=existing,
                    target_value=target_value if target_value > 0 else float(existing.position_value),
                    entry_price=float(metrics.price_current),
                    atr_14=float(metrics.atr_14) if metrics.atr_14 is not None else None,
                )
        elif decision_row.decision == "SELL":
            if existing is not None:
                sell_target = 0.0 if float(decision_row.confidence) >= 0.55 else float(existing.position_value) * 0.5
                action, action_size = self._rebalance_position(
                    position=existing,
                    target_value=sell_target,
                    entry_price=float(metrics.price_current),
                    atr_14=float(metrics.atr_14) if metrics.atr_14 is not None else None,
                )

        await self.session.flush()
        action_row = await self._portfolio.add_action(
            PortfolioAction(
                coin_id=int(coin_id),
                action=action if action in PORTFOLIO_ACTIONS else "HOLD_POSITION",
                size=max(float(action_size), 0.0),
                confidence=self._clamp(float(decision_row.confidence), 0.0, 1.0),
                decision_id=int(decision_row.id),
            )
        )
        state = await self._refresh_portfolio_state()

        pending_events: list[PortfolioPendingEvent] = []
        if emit_events:
            if action == "OPEN_POSITION":
                pending_events.append(
                    PortfolioPendingEvent(
                        "portfolio_position_opened",
                        {
                            "coin_id": int(coin_id),
                            "timeframe": int(timeframe),
                            "timestamp": action_row.created_at,
                            "action_id": int(action_row.id),
                            "decision_id": int(decision_row.id),
                            "size": float(action_size),
                            "confidence": float(decision_row.confidence),
                        },
                    )
                )
            elif action == "CLOSE_POSITION":
                pending_events.append(
                    PortfolioPendingEvent(
                        "portfolio_position_closed",
                        {
                            "coin_id": int(coin_id),
                            "timeframe": int(timeframe),
                            "timestamp": action_row.created_at,
                            "action_id": int(action_row.id),
                            "decision_id": int(decision_row.id),
                            "size": float(action_size),
                            "confidence": float(decision_row.confidence),
                        },
                    )
                )
            elif action in {"INCREASE_POSITION", "REDUCE_POSITION"}:
                pending_events.append(
                    PortfolioPendingEvent(
                        "portfolio_rebalanced",
                        {
                            "coin_id": int(coin_id),
                            "timeframe": int(timeframe),
                            "timestamp": action_row.created_at,
                            "action_id": int(action_row.id),
                            "decision_id": int(decision_row.id),
                            "size": float(action_size),
                            "confidence": float(decision_row.confidence),
                        },
                    )
                )

        result = PortfolioActionEvaluationResult(
            status="ok",
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            decision=str(decision_row.decision),
            action=action,
            size=float(action_size),
            portfolio_state=state,
            pending_events=tuple(pending_events),
        )
        self._log_info(
            "service.evaluate_portfolio_action.result",
            mode="write",
            coin_id=coin_id,
            timeframe=timeframe,
            action=result.action,
        )
        return result

    async def sync_exchange_balances(self, *, emit_events: bool = True) -> PortfolioSyncResult:
        self._log_debug("service.sync_exchange_balances", mode="write", emit_events=emit_events)
        accounts = await self._accounts.list_enabled()
        items: list[PortfolioSyncItem] = []
        cached_rows: list[PortfolioCachedBalanceRow] = []
        pending_events: list[PortfolioPendingEvent] = []

        for account in accounts:
            plugin = create_exchange_plugin(account)
            balances = await plugin.fetch_balances()
            for balance_row in balances:
                outcome = await self._sync_balance_row(
                    account=account,
                    balance_row=balance_row,
                    emit_events=emit_events,
                )
                if outcome is None:
                    continue
                items.append(outcome.item)
                cached_rows.append(outcome.cached_row)
                pending_events.extend(outcome.pending_events)

        state = await self._refresh_portfolio_state()
        return PortfolioSyncResult(
            status="ok",
            accounts=len(accounts),
            items=tuple(items),
            cached_rows=tuple(cached_rows),
            state=state,
            pending_events=tuple(pending_events),
        )

    async def _ensure_portfolio_state(self) -> PortfolioState:
        state = await self._portfolio.get_state(for_update=True)
        if state is not None:
            return state
        settings = get_settings()
        return await self._portfolio.add_state(
            PortfolioState(
                id=1,
                total_capital=float(settings.portfolio_total_capital),
                allocated_capital=0.0,
                available_capital=float(settings.portfolio_total_capital),
            )
        )

    async def _refresh_portfolio_state(self) -> PortfolioStateReadModel:
        state = await self._ensure_portfolio_state()
        allocated = await self._portfolio.sum_allocated_capital()
        state.allocated_capital = allocated
        state.available_capital = max(float(state.total_capital) - allocated, 0.0)
        state.updated_at = utc_now()
        return PortfolioStateReadModel(
            total_capital=float(state.total_capital),
            allocated_capital=float(state.allocated_capital),
            available_capital=float(state.available_capital),
            updated_at=state.updated_at.isoformat(),
            open_positions=await self._portfolio.count_open_positions(),
            max_positions=int(get_settings().portfolio_max_positions),
        )

    async def _ensure_coin_for_balance(
        self,
        *,
        symbol: str,
        exchange_name: str,
    ) -> Coin:
        normalized = symbol.upper()
        coin = await self._coins.get_by_symbol(normalized)
        if coin is not None:
            return coin
        created = await self._coins.add(
            Coin(
                symbol=normalized,
                name=normalized,
                asset_type="crypto",
                theme="portfolio",
                sector_code="portfolio",
                source=exchange_name.lower(),
                enabled=False,
                sort_order=0,
                candles_config=[],
            )
        )
        await self._coin_metrics.ensure_row(int(created.id))
        return created

    async def _sync_balance_position(
        self,
        *,
        account: ExchangeAccount,
        coin: Coin,
        value_usd: float,
        balance: float,
    ) -> None:
        position = await self._portfolio.get_balance_position(
            exchange_account_id=int(account.id),
            coin_id=int(coin.id),
            timeframe=DEFAULT_PORTFOLIO_TIMEFRAME,
        )
        metrics = await self._portfolio.get_coin_metrics(coin_id=int(coin.id))
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
            await self._portfolio.add_position(
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

    @staticmethod
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

    async def _sync_balance_row(
        self,
        *,
        account: ExchangeAccount,
        balance_row: dict[str, object],
        emit_events: bool,
    ) -> _BalanceSyncOutcome | None:
        symbol = str(balance_row.get("symbol", "")).upper()
        if not symbol:
            self._log_debug(
                "service.sync_exchange_balance_row.skipped",
                mode="write",
                account_id=int(account.id),
                reason="blank_symbol",
            )
            return None

        balance_value = float(balance_row.get("balance", 0.0) or 0.0)
        value_usd = float(balance_row.get("value_usd", 0.0) or 0.0)
        coin = await self._ensure_coin_for_balance(symbol=symbol, exchange_name=account.exchange_name)
        row = await self._portfolio.get_balance_row(account_id=int(account.id), symbol=symbol)
        previous_value = float(row.value_usd) if row is not None else 0.0
        if row is None:
            row = await self._portfolio.add_balance_row(
                PortfolioBalance(
                    exchange_account_id=int(account.id),
                    coin_id=int(coin.id),
                    symbol=symbol,
                    balance=balance_value,
                    value_usd=value_usd,
                )
            )
        else:
            row.coin_id = int(coin.id)
            row.balance = balance_value
            row.value_usd = value_usd
            row.updated_at = utc_now()

        await self._sync_balance_position(
            account=account,
            coin=coin,
            value_usd=value_usd,
            balance=balance_value,
        )
        auto_watch_enabled = self._apply_auto_watch(coin=coin, value_usd=value_usd)
        event_timestamp: datetime = utc_now()
        pending_events: list[PortfolioPendingEvent] = []

        if auto_watch_enabled:
            pending_events.append(
                PortfolioPendingEvent(
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
            )

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
            pending_events.append(PortfolioPendingEvent("portfolio_balance_updated", dict(event_payload)))
            pending_events.append(PortfolioPendingEvent("portfolio_position_changed", dict(event_payload)))

        outcome = _BalanceSyncOutcome(
            item=PortfolioSyncItem(
                exchange_account_id=int(account.id),
                symbol=symbol,
                balance=balance_value,
                value_usd=value_usd,
            ),
            cached_row=PortfolioCachedBalanceRow(
                exchange_account_id=int(account.id),
                exchange_name=account.exchange_name,
                account_name=account.account_name,
                coin_id=int(coin.id),
                symbol=symbol,
                balance=balance_value,
                value_usd=value_usd,
                auto_watch_enabled=auto_watch_enabled,
            ),
            pending_events=tuple(pending_events),
        )
        self._log_debug(
            "service.sync_exchange_balance_row.result",
            mode="write",
            account_id=int(account.id),
            symbol=symbol,
            emitted_events=len(outcome.pending_events),
            auto_watch_enabled=auto_watch_enabled,
        )
        return outcome


__all__ = [
    "PortfolioActionEvaluationResult",
    "PortfolioCachedBalanceRow",
    "PortfolioPendingEvent",
    "PortfolioService",
    "PortfolioSideEffectDispatcher",
    "PortfolioSyncItem",
    "PortfolioSyncResult",
]
