from __future__ import annotations

from src.apps.anomalies.services import AnomalyService
from src.core.db.session import AsyncSessionLocal
from src.core.db.uow import AsyncUnitOfWork
from src.runtime.streams.types import IrisEvent


class CandleAnomalyConsumer:
    def __init__(self, *, session_factory=AsyncSessionLocal) -> None:
        self._session_factory = session_factory

    async def handle_event(self, event: IrisEvent) -> None:
        if event.event_type != "candle_closed" or event.coin_id <= 0 or event.timeframe <= 0:
            return
        async with AsyncUnitOfWork(session_factory=self._session_factory) as uow:
            service = AnomalyService(uow)
            await service.process_candle_closed(
                coin_id=event.coin_id,
                timeframe=event.timeframe,
                timestamp=event.timestamp,
                source=str(event.payload.get("source")) if event.payload.get("source") is not None else None,
            )
