from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.anomalies.constants import ANOMALY_STATUS_ACTIVE, ANOMALY_STATUS_NEW, PORTFOLIO_OPEN_POSITION_STATUS
from src.apps.anomalies.models import MarketAnomaly
from src.apps.anomalies.read_models import AnomalyReadModel, anomaly_read_model_from_orm
from src.apps.portfolio.models import PortfolioPosition
from src.core.db.persistence import AsyncQueryService

_VISIBLE_ANOMALY_STATUSES = (ANOMALY_STATUS_NEW, ANOMALY_STATUS_ACTIVE)


class AnomalyQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="anomalies", service_name="AnomalyQueryService")

    async def get_read_by_id(self, anomaly_id: int) -> AnomalyReadModel | None:
        self._log_debug("query.get_anomaly_read_by_id", mode="read", anomaly_id=anomaly_id)
        anomaly = await self.session.scalar(
            select(MarketAnomaly)
            .where(MarketAnomaly.id == anomaly_id)
            .execution_options(populate_existing=True)
            .limit(1)
        )
        if anomaly is None:
            self._log_debug("query.get_anomaly_read_by_id.result", mode="read", found=False)
            return None
        item = anomaly_read_model_from_orm(anomaly)
        self._log_debug("query.get_anomaly_read_by_id.result", mode="read", found=True)
        return item

    async def list_active_anomalies(
        self,
        *,
        symbol: str | None = None,
        timeframe: int | None = None,
        limit: int = 50,
    ) -> tuple[AnomalyReadModel, ...]:
        self._log_debug(
            "query.list_active_anomalies",
            mode="read",
            symbol=symbol.upper() if symbol is not None else None,
            timeframe=timeframe,
            limit=limit,
        )
        stmt = (
            select(MarketAnomaly)
            .where(MarketAnomaly.status.in_(_VISIBLE_ANOMALY_STATUSES))
            .order_by(MarketAnomaly.detected_at.desc())
            .limit(limit)
        )
        if symbol is not None:
            stmt = stmt.where(MarketAnomaly.symbol == symbol.upper())
        if timeframe is not None:
            stmt = stmt.where(MarketAnomaly.timeframe == timeframe)
        rows = (await self.session.execute(stmt)).scalars().all()
        items = tuple(anomaly_read_model_from_orm(item) for item in rows)
        self._log_debug("query.list_active_anomalies.result", mode="read", count=len(items))
        return items

    async def list_portfolio_relevant_anomalies(self, *, limit: int = 25) -> tuple[AnomalyReadModel, ...]:
        self._log_debug("query.list_portfolio_relevant_anomalies", mode="read", limit=limit)
        open_position_exists = (
            select(PortfolioPosition.id)
            .where(
                PortfolioPosition.coin_id == MarketAnomaly.coin_id,
                PortfolioPosition.timeframe == MarketAnomaly.timeframe,
                PortfolioPosition.status == PORTFOLIO_OPEN_POSITION_STATUS,
            )
            .exists()
        )
        stmt = (
            select(MarketAnomaly)
            .where(MarketAnomaly.status.in_(_VISIBLE_ANOMALY_STATUSES), open_position_exists)
            .order_by(MarketAnomaly.detected_at.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        items = tuple(anomaly_read_model_from_orm(item) for item in rows)
        self._log_debug("query.list_portfolio_relevant_anomalies.result", mode="read", count=len(items))
        return items


__all__ = ["AnomalyQueryService"]
