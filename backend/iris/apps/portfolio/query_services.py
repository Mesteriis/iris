from collections.abc import Mapping
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from iris.apps.patterns.domain.regime import read_regime_details
from iris.apps.portfolio.cache import cache_portfolio_state_async, read_cached_portfolio_state_async
from iris.apps.portfolio.models import PortfolioAction, PortfolioPosition, PortfolioState
from iris.apps.portfolio.query_builders import (
    portfolio_actions_select as _portfolio_actions_select,
)
from iris.apps.portfolio.query_builders import (
    portfolio_positions_select as _portfolio_positions_select,
)
from iris.apps.portfolio.read_models import (
    PortfolioActionReadModel,
    PortfolioPositionReadModel,
    PortfolioStateReadModel,
    portfolio_action_read_model_from_mapping,
    portfolio_position_read_model_from_mapping,
    portfolio_state_read_model_from_mapping,
)
from iris.core.db.persistence import AsyncQueryService
from iris.core.settings import get_settings


class PortfolioQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="portfolio", service_name="PortfolioQueryService")

    async def list_positions(self, *, limit: int = 200) -> tuple[PortfolioPositionReadModel, ...]:
        self._log_debug("query.list_portfolio_positions", mode="read", limit=limit, loading_profile="projection")
        rows = (
            await self.session.execute(
                _portfolio_positions_select()
                .where(PortfolioPosition.status.in_(("open", "partial")))
                .order_by(PortfolioPosition.position_value.desc(), PortfolioPosition.id.desc())
                .limit(max(limit, 1))
            )
        ).all()
        items = tuple(
            portfolio_position_read_model_from_mapping(
                {
                    **row._mapping,
                    "entry_price": float(row.entry_price or 0.0),
                    "current_price": float(row.price_current or 0.0) or None,
                    "unrealized_pnl": (
                        (float(row.price_current or 0.0) - float(row.entry_price or 0.0))
                        * float(row.position_size or 0.0)
                        if row.price_current and row.entry_price
                        else 0.0
                    ),
                    "regime": (
                        detailed.regime
                        if (detailed := read_regime_details(row.market_regime_details, int(row.timeframe))) is not None
                        else row.market_regime
                    ),
                    "risk_to_stop": (
                        max(
                            (float(row.entry_price or 0.0) - float(row.stop_loss or 0.0))
                            / float(row.entry_price or 1.0),
                            0.0,
                        )
                        if row.entry_price and row.stop_loss is not None
                        else None
                    ),
                }
            )
            for row in rows
        )
        self._log_debug("query.list_portfolio_positions.result", mode="read", count=len(items))
        return items

    async def list_actions(self, *, limit: int = 200) -> tuple[PortfolioActionReadModel, ...]:
        self._log_debug("query.list_portfolio_actions", mode="read", limit=limit, loading_profile="projection")
        rows = (
            await self.session.execute(
                _portfolio_actions_select()
                .order_by(PortfolioAction.created_at.desc(), PortfolioAction.id.desc())
                .limit(max(limit, 1))
            )
        ).all()
        items = tuple(
            portfolio_action_read_model_from_mapping(cast(Mapping[str, Any], row._mapping))
            for row in rows
        )
        self._log_debug("query.list_portfolio_actions.result", mode="read", count=len(items))
        return items

    async def get_state(self) -> PortfolioStateReadModel:
        self._log_debug("query.get_portfolio_state", mode="read", loading_profile="cached_snapshot")
        cached = await read_cached_portfolio_state_async()
        if cached is not None:
            self._log_debug("query.get_portfolio_state.cache_hit", mode="read")
            return portfolio_state_read_model_from_mapping(cached)
        self._log_debug("query.get_portfolio_state.cache_miss", mode="read")
        state = await self.session.get(PortfolioState, 1)
        if state is None:
            item = PortfolioStateReadModel(
                total_capital=0.0,
                allocated_capital=0.0,
                available_capital=0.0,
                updated_at=None,
                open_positions=0,
                max_positions=0,
            )
            self._log_debug("query.get_portfolio_state.result", mode="read", found=False)
            return item
        open_positions = int(
            (
                await self.session.execute(
                    select(func.count()).select_from(PortfolioPosition).where(
                        PortfolioPosition.status.in_(("open", "partial"))
                    )
                )
            ).scalar_one()
            or 0
        )
        item = PortfolioStateReadModel(
            total_capital=float(state.total_capital),
            allocated_capital=float(state.allocated_capital),
            available_capital=float(state.available_capital),
            updated_at=state.updated_at.isoformat(),
            open_positions=open_positions,
            max_positions=int(get_settings().portfolio_max_positions),
        )
        await cache_portfolio_state_async(
            {
                "total_capital": item.total_capital,
                "allocated_capital": item.allocated_capital,
                "available_capital": item.available_capital,
                "updated_at": item.updated_at,
                "open_positions": item.open_positions,
                "max_positions": item.max_positions,
            }
        )
        self._log_debug("query.get_portfolio_state.result", mode="read", found=True)
        return item


__all__ = ["PortfolioQueryService"]
