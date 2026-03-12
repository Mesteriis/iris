from __future__ import annotations

from src.apps.hypothesis_engine.constants import SUPPORTED_HYPOTHESIS_SOURCE_EVENTS
from src.apps.hypothesis_engine.services import HypothesisService
from src.core.db.session import AsyncSessionLocal
from src.runtime.streams.types import IrisEvent


class HypothesisConsumer:
    def __init__(self, *, session_factory=AsyncSessionLocal) -> None:
        self._session_factory = session_factory

    async def handle_event(self, event: IrisEvent) -> None:
        if event.event_type not in SUPPORTED_HYPOTHESIS_SOURCE_EVENTS or event.coin_id <= 0:
            return
        async with self._session_factory() as db:
            await HypothesisService(db).create_from_event(event)
