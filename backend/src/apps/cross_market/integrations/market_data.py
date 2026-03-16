from src.apps.market_data.candles import CandlePoint
from src.apps.market_data.repositories import CandleRepository
from src.core.db.uow import BaseAsyncUnitOfWork


class CrossMarketMarketDataAdapter:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._candles = CandleRepository(uow.session)

    async def fetch_points(
        self,
        *,
        coin_id: int,
        timeframe: int,
        limit: int,
    ) -> list[CandlePoint]:
        return await self._candles.fetch_points(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            limit=int(limit),
        )

    async def fetch_points_for_coin_ids(
        self,
        *,
        coin_ids: list[int],
        timeframe: int,
        limit: int,
    ) -> dict[int, list[CandlePoint]]:
        return await self._candles.fetch_points_for_coin_ids(
            coin_ids=[int(item) for item in coin_ids],
            timeframe=int(timeframe),
            limit=int(limit),
        )


__all__ = ["CrossMarketMarketDataAdapter"]
