from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from iris.apps.indicators.models import CoinMetrics
from iris.apps.market_data.models import Coin
from iris.apps.portfolio.models import (
    ExchangeAccount,
    PortfolioAction,
    PortfolioBalance,
    PortfolioPosition,
    PortfolioState,
)
from iris.apps.signals.models import MarketDecision
from iris.core.db.persistence import AsyncRepository

_OPEN_POSITION_STATUSES = ("open", "partial")


class ExchangeAccountRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="portfolio", repository_name="ExchangeAccountRepository")

    async def list_enabled(self) -> list[ExchangeAccount]:
        self._log_debug("repo.list_enabled_exchange_accounts", mode="read")
        rows = (
            await self.session.execute(
                select(ExchangeAccount)
                .where(ExchangeAccount.enabled.is_(True))
                .order_by(ExchangeAccount.exchange_name.asc(), ExchangeAccount.account_name.asc())
            )
        ).scalars().all()
        items = list(rows)
        self._log_debug("repo.list_enabled_exchange_accounts.result", mode="read", count=len(items))
        return items

    async def get_by_id(self, account_id: int) -> ExchangeAccount | None:
        self._log_debug("repo.get_exchange_account_by_id", mode="read", account_id=account_id)
        item = await self.session.get(ExchangeAccount, int(account_id))
        self._log_debug("repo.get_exchange_account_by_id.result", mode="read", found=item is not None)
        return item


class PortfolioRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="portfolio", repository_name="PortfolioRepository")

    async def get_state(self, *, for_update: bool = False) -> PortfolioState | None:
        self._log_debug("repo.get_portfolio_state", mode="write" if for_update else "read", lock=for_update)
        stmt = select(PortfolioState).where(PortfolioState.id == 1)
        if for_update:
            stmt = stmt.with_for_update()
        item = await self.session.scalar(stmt.limit(1))
        self._log_debug("repo.get_portfolio_state.result", mode="write" if for_update else "read", found=item is not None)
        return item

    async def add_state(self, state: PortfolioState) -> PortfolioState:
        self._log_info("repo.add_portfolio_state", mode="write", state_id=int(state.id))
        self.session.add(state)
        await self.session.flush()
        return state

    async def refresh(self, item: object) -> None:
        await self.session.refresh(item)

    async def count_open_positions(self) -> int:
        self._log_debug("repo.count_open_portfolio_positions", mode="read")
        count = int(
            (
                await self.session.execute(
                    select(func.count()).select_from(PortfolioPosition).where(
                        PortfolioPosition.status.in_(_OPEN_POSITION_STATUSES)
                    )
                )
            ).scalar_one()
            or 0
        )
        self._log_debug("repo.count_open_portfolio_positions.result", mode="read", count=count)
        return count

    async def sum_allocated_capital(self) -> float:
        self._log_debug("repo.sum_allocated_capital", mode="read")
        value = float(
            (
                await self.session.execute(
                    select(func.coalesce(func.sum(PortfolioPosition.position_value), 0.0)).where(
                        PortfolioPosition.status.in_(_OPEN_POSITION_STATUSES)
                    )
                )
            ).scalar_one()
            or 0.0
        )
        self._log_debug("repo.sum_allocated_capital.result", mode="read", allocated=value)
        return value

    async def get_balance_row(self, *, account_id: int, symbol: str) -> PortfolioBalance | None:
        self._log_debug("repo.get_portfolio_balance_row", mode="write", account_id=account_id, symbol=symbol)
        item = await self.session.scalar(
            select(PortfolioBalance)
            .where(
                PortfolioBalance.exchange_account_id == int(account_id),
                PortfolioBalance.symbol == symbol,
            )
            .limit(1)
        )
        self._log_debug("repo.get_portfolio_balance_row.result", mode="write", found=item is not None)
        return item

    async def add_balance_row(self, item: PortfolioBalance) -> PortfolioBalance:
        self._log_info(
            "repo.add_portfolio_balance_row",
            mode="write",
            account_id=int(item.exchange_account_id),
            symbol=item.symbol,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def get_balance_position(
        self,
        *,
        exchange_account_id: int,
        coin_id: int,
        timeframe: int,
    ) -> PortfolioPosition | None:
        self._log_debug(
            "repo.get_balance_portfolio_position",
            mode="write",
            exchange_account_id=exchange_account_id,
            coin_id=coin_id,
            timeframe=timeframe,
        )
        item = await self.session.scalar(
            select(PortfolioPosition)
            .where(
                PortfolioPosition.exchange_account_id == int(exchange_account_id),
                PortfolioPosition.coin_id == int(coin_id),
                PortfolioPosition.timeframe == int(timeframe),
            )
            .order_by(PortfolioPosition.opened_at.desc(), PortfolioPosition.id.desc())
            .limit(1)
        )
        self._log_debug("repo.get_balance_portfolio_position.result", mode="write", found=item is not None)
        return item

    async def get_open_position(self, *, coin_id: int, timeframe: int) -> PortfolioPosition | None:
        self._log_debug("repo.get_open_portfolio_position", mode="write", coin_id=coin_id, timeframe=timeframe)
        item = await self.session.scalar(
            select(PortfolioPosition)
            .where(
                PortfolioPosition.coin_id == int(coin_id),
                PortfolioPosition.timeframe == int(timeframe),
                PortfolioPosition.status.in_(_OPEN_POSITION_STATUSES),
            )
            .order_by(PortfolioPosition.position_value.desc(), PortfolioPosition.id.asc())
            .limit(1)
        )
        self._log_debug("repo.get_open_portfolio_position.result", mode="write", found=item is not None)
        return item

    async def add_position(self, item: PortfolioPosition) -> PortfolioPosition:
        self._log_info(
            "repo.add_portfolio_position",
            mode="write",
            coin_id=int(item.coin_id),
            timeframe=int(item.timeframe),
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def sum_sector_position_value(self, *, sector_id: int) -> float:
        self._log_debug("repo.sum_sector_position_value", mode="read", sector_id=sector_id)
        value = float(
            (
                await self.session.execute(
                    select(func.coalesce(func.sum(PortfolioPosition.position_value), 0.0))
                    .join(Coin, Coin.id == PortfolioPosition.coin_id)
                    .where(
                        PortfolioPosition.status.in_(_OPEN_POSITION_STATUSES),
                        Coin.sector_id == int(sector_id),
                    )
                )
            ).scalar_one()
            or 0.0
        )
        self._log_debug("repo.sum_sector_position_value.result", mode="read", value=value)
        return value

    async def get_coin_metrics(self, *, coin_id: int) -> CoinMetrics | None:
        self._log_debug("repo.get_portfolio_coin_metrics", mode="read", coin_id=coin_id)
        item = await self.session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(coin_id)).limit(1))
        self._log_debug("repo.get_portfolio_coin_metrics.result", mode="read", found=item is not None)
        return item

    async def get_latest_market_decision(self, *, coin_id: int, timeframe: int) -> MarketDecision | None:
        self._log_debug(
            "repo.get_latest_portfolio_market_decision",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
        )
        item = await self.session.scalar(
            select(MarketDecision)
            .where(MarketDecision.coin_id == int(coin_id), MarketDecision.timeframe == int(timeframe))
            .order_by(MarketDecision.created_at.desc(), MarketDecision.id.desc())
            .limit(1)
        )
        self._log_debug("repo.get_latest_portfolio_market_decision.result", mode="read", found=item is not None)
        return item

    async def add_action(self, item: PortfolioAction) -> PortfolioAction:
        self._log_info(
            "repo.add_portfolio_action",
            mode="write",
            coin_id=int(item.coin_id),
            decision_id=int(item.decision_id),
            action=item.action,
        )
        self.session.add(item)
        await self.session.flush()
        return item


__all__ = ["ExchangeAccountRepository", "PortfolioRepository"]
