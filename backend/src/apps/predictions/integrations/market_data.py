from __future__ import annotations

from datetime import datetime

from src.apps.market_data.domain import ensure_utc
from src.apps.market_data.repositories import CandleRepository
from src.apps.predictions.engines.contracts import PredictionWindowCandleInput
from src.core.db.uow import BaseAsyncUnitOfWork


class PredictionMarketDataAdapter:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._candles = CandleRepository(uow.session)

    async def fetch_prediction_window(
        self,
        *,
        coin_id: int,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[PredictionWindowCandleInput, ...]:
        rows = await self._candles.fetch_points_between(
            coin_id=int(coin_id),
            timeframe=15,
            window_start=window_start,
            window_end=window_end,
        )
        return tuple(
            PredictionWindowCandleInput(
                timestamp=ensure_utc(candle.timestamp),
                high=float(candle.high),
                low=float(candle.low),
                close=float(candle.close),
            )
            for candle in rows
        )


__all__ = ["PredictionMarketDataAdapter"]
