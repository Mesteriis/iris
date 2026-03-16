from datetime import datetime

from iris.apps.market_data.candles import CandlePoint
from iris.apps.market_data.repositories import CandleRepository
from iris.core.db.uow import BaseAsyncUnitOfWork


class SignalHistoryMarketDataAdapter:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._candles = CandleRepository(uow.session)

    async def fetch_points_between(
        self,
        *,
        coin_id: int,
        timeframe: int,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CandlePoint]:
        return list(
            await self._candles.fetch_points_between(
            coin_id=coin_id,
            timeframe=timeframe,
            window_start=window_start,
            window_end=window_end,
        )
        )


__all__ = ["SignalHistoryMarketDataAdapter"]
