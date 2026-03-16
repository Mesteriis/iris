from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from iris.apps.market_data.domain import utc_now
from iris.apps.market_data.models import Coin
from iris.apps.market_data.repositories import CoinMetricsRepository, CoinRepository
from iris.apps.portfolio.clients import ExchangePlugin
from iris.apps.portfolio.models import ExchangeAccount, PortfolioBalance, PortfolioPosition, PortfolioState
from iris.apps.portfolio.read_models import PortfolioStateReadModel
from iris.apps.portfolio.repositories import ExchangeAccountRepository, PortfolioRepository
from iris.apps.portfolio.results import (
    BalanceSyncOutcome,
    PortfolioCachedBalanceRow,
    PortfolioPendingEvent,
    PortfolioSyncItem,
    PortfolioSyncResult,
)
from iris.apps.portfolio.support import DEFAULT_PORTFOLIO_TIMEFRAME, calculate_stops
from iris.core.settings import get_settings


def _float_value(value: object) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


class PortfolioStateCoordinator:
    def __init__(self, *, portfolio: PortfolioRepository) -> None:
        self._portfolio = portfolio

    async def ensure_portfolio_state(self) -> PortfolioState:
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

    async def refresh_portfolio_state(self) -> PortfolioStateReadModel:
        state = await self.ensure_portfolio_state()
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


class PortfolioSyncCoordinator:
    def __init__(
        self,
        *,
        session: AsyncSession,
        accounts: ExchangeAccountRepository,
        portfolio: PortfolioRepository,
        state_support: PortfolioStateCoordinator,
    ) -> None:
        self._accounts = accounts
        self._portfolio = portfolio
        self._state = state_support
        self._coins = CoinRepository(session)
        self._coin_metrics = CoinMetricsRepository(session)

    async def sync_exchange_balances(
        self,
        *,
        emit_events: bool,
        plugin_factory: Callable[[ExchangeAccount], ExchangePlugin],
    ) -> PortfolioSyncResult:
        accounts = await self._accounts.list_enabled()
        items: list[PortfolioSyncItem] = []
        cached_rows: list[PortfolioCachedBalanceRow] = []
        pending_events: list[PortfolioPendingEvent] = []

        for account in accounts:
            plugin = plugin_factory(account)
            balances = await plugin.fetch_balances()
            for balance_row in balances:
                outcome = await self.sync_balance_row(
                    account=account,
                    balance_row=balance_row,
                    emit_events=emit_events,
                )
                if outcome is None:
                    continue
                items.append(outcome.item)
                cached_rows.append(outcome.cached_row)
                pending_events.extend(outcome.pending_events)

        state = await self._state.refresh_portfolio_state()
        return PortfolioSyncResult(
            status="ok",
            accounts=len(accounts),
            items=tuple(items),
            cached_rows=tuple(cached_rows),
            state=state,
            pending_events=tuple(pending_events),
        )

    async def ensure_coin_for_balance(
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

    async def sync_balance_position(
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
    def apply_auto_watch(
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

    async def sync_balance_row(
        self,
        *,
        account: ExchangeAccount,
        balance_row: dict[str, object],
        emit_events: bool,
    ) -> BalanceSyncOutcome | None:
        symbol = str(balance_row.get("symbol", "")).upper()
        if not symbol:
            return None

        balance_value = _float_value(balance_row.get("balance", 0.0))
        value_usd = _float_value(balance_row.get("value_usd", 0.0))
        coin = await self.ensure_coin_for_balance(symbol=symbol, exchange_name=account.exchange_name)
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

        await self.sync_balance_position(
            account=account,
            coin=coin,
            value_usd=value_usd,
            balance=balance_value,
        )
        auto_watch_enabled = self.apply_auto_watch(coin=coin, value_usd=value_usd)
        event_timestamp = utc_now()
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

        return BalanceSyncOutcome(
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


__all__ = ["PortfolioStateCoordinator", "PortfolioSyncCoordinator"]
