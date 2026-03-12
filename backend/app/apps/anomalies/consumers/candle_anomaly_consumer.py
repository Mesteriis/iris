from __future__ import annotations

from app.apps.anomalies.services import AnomalyService
from app.core.db.session import AsyncSessionLocal
from app.runtime.streams.types import IrisEvent


class CandleAnomalyConsumer:
    def __init__(self, *, session_factory=AsyncSessionLocal) -> None:
        self._session_factory = session_factory

    async def handle_event(self, event: IrisEvent) -> None:
        if event.event_type != "candle_closed" or event.coin_id <= 0 or event.timeframe <= 0:
            return
        async with self._session_factory() as db:
            service = AnomalyService(db)
            await service.process_candle_closed(
                coin_id=event.coin_id,
                timeframe=event.timeframe,
                timestamp=event.timestamp,
                source=str(event.payload.get("source")) if event.payload.get("source") is not None else None,
            )
