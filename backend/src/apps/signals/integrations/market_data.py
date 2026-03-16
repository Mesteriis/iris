from src.apps.market_data.candles import CandlePoint
from src.apps.market_data.repositories import CandleRepository
from src.core.db.uow import BaseAsyncUnitOfWork


class SignalHistoryMarketDataAdapter:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._candles = CandleRepository(uow.session)

    async def fetch_points_between(
        self,
        *,
        coin_id: int,
        timeframe: int,
        window_start: object,
        window_end: object,
    ) -> list[CandlePoint]:
        return await self._candles.fetch_points_between(
            coin_id=coin_id,
            timeframe=timeframe,
            window_start=window_start,
            window_end=window_end,
        )


__all__ = ["SignalHistoryMarketDataAdapter"]
