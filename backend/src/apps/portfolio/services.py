from src.apps.market_data.models import Coin
from src.apps.portfolio.action_support import PortfolioActionCoordinator, apply_portfolio_rebalance
from src.apps.portfolio.cache import cache_portfolio_balances_async, cache_portfolio_state_async
from src.apps.portfolio.clients import create_exchange_plugin
from src.apps.portfolio.models import ExchangeAccount, PortfolioPosition, PortfolioState
from src.apps.portfolio.read_models import PortfolioStateReadModel
from src.apps.portfolio.repositories import ExchangeAccountRepository, PortfolioRepository
from src.apps.portfolio.results import (
    BalanceSyncOutcome,
    PortfolioActionEvaluationResult,
    PortfolioCachedBalanceRow,
    PortfolioPendingEvent,
    PortfolioSyncItem,
    PortfolioSyncResult,
)
from src.apps.portfolio.serializers import (
    portfolio_cached_balance_row_payload,
    portfolio_state_cache_payload,
)
from src.apps.portfolio.sync_support import PortfolioStateCoordinator, PortfolioSyncCoordinator
from src.apps.signals.models import MarketDecision
from src.core.db.persistence import PersistenceComponent
from src.core.db.uow import BaseAsyncUnitOfWork
from src.runtime.streams.publisher import publish_event


class PortfolioSideEffectDispatcher:
    async def apply_sync_result(self, result: PortfolioSyncResult) -> None:
        await cache_portfolio_balances_async(
            [portfolio_cached_balance_row_payload(row) for row in result.cached_rows]
        )
        await cache_portfolio_state_async(portfolio_state_cache_payload(result.state))
        for event in result.pending_events:
            publish_event(event.event_type, event.payload)

    async def apply_action_result(self, result: PortfolioActionEvaluationResult) -> None:
        if result.portfolio_state is not None:
            await cache_portfolio_state_async(portfolio_state_cache_payload(result.portfolio_state))
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
        self._state = PortfolioStateCoordinator(portfolio=self._portfolio)
        self._actions = PortfolioActionCoordinator(
            session=uow.session,
            portfolio=self._portfolio,
            state_support=self._state,
        )
        self._sync = PortfolioSyncCoordinator(
            session=uow.session,
            accounts=self._accounts,
            portfolio=self._portfolio,
            state_support=self._state,
        )

    @staticmethod
    def _rebalance_position(
        *,
        position: PortfolioPosition,
        target_value: float,
        entry_price: float,
        atr_14: float | None,
    ) -> tuple[str, float]:
        return apply_portfolio_rebalance(
            position=position,
            target_value=target_value,
            entry_price=entry_price,
            atr_14=atr_14,
        )

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
        result = await self._actions.evaluate_portfolio_action(
            coin_id=coin_id,
            timeframe=timeframe,
            decision=decision,
            emit_events=emit_events,
        )
        if result.status == "ok":
            self._log_info(
                "service.evaluate_portfolio_action.result",
                mode="write",
                coin_id=coin_id,
                timeframe=timeframe,
                action=result.action,
            )
        else:
            self._log_debug(
                "service.evaluate_portfolio_action.result",
                mode="write",
                status=result.status,
                reason=result.reason,
                coin_id=coin_id,
                timeframe=timeframe,
            )
        return result

    async def sync_exchange_balances(self, *, emit_events: bool = True) -> PortfolioSyncResult:
        self._log_debug("service.sync_exchange_balances", mode="write", emit_events=emit_events)
        result = await self._sync.sync_exchange_balances(
            emit_events=emit_events,
            plugin_factory=create_exchange_plugin,
        )
        self._log_debug(
            "service.sync_exchange_balances.result",
            mode="write",
            accounts=result.accounts,
            balances=result.balances,
        )
        return result

    async def _ensure_portfolio_state(self) -> PortfolioState:
        return await self._state.ensure_portfolio_state()

    async def _refresh_portfolio_state(self) -> PortfolioStateReadModel:
        return await self._state.refresh_portfolio_state()

    async def _ensure_coin_for_balance(
        self,
        *,
        symbol: str,
        exchange_name: str,
    ) -> Coin:
        return await self._sync.ensure_coin_for_balance(symbol=symbol, exchange_name=exchange_name)

    async def _sync_balance_position(
        self,
        *,
        account: ExchangeAccount,
        coin: Coin,
        value_usd: float,
        balance: float,
    ) -> None:
        await self._sync.sync_balance_position(
            account=account,
            coin=coin,
            value_usd=value_usd,
            balance=balance,
        )

    @staticmethod
    def _apply_auto_watch(
        *,
        coin: Coin,
        value_usd: float,
    ) -> bool:
        return PortfolioSyncCoordinator.apply_auto_watch(coin=coin, value_usd=value_usd)

    async def _sync_balance_row(
        self,
        *,
        account: ExchangeAccount,
        balance_row: dict[str, object],
        emit_events: bool,
    ) -> BalanceSyncOutcome | None:
        return await self._sync.sync_balance_row(
            account=account,
            balance_row=balance_row,
            emit_events=emit_events,
        )


__all__ = [
    "PortfolioActionEvaluationResult",
    "PortfolioCachedBalanceRow",
    "PortfolioPendingEvent",
    "PortfolioService",
    "PortfolioSideEffectDispatcher",
    "PortfolioSyncItem",
    "PortfolioSyncResult",
]
