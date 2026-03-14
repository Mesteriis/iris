from __future__ import annotations

from src.apps.market_structure.contracts import (
    ManualMarketStructureIngestRequest,
    MarketStructureSnapshotRead,
    MarketStructureSourceCreate,
    MarketStructureSourceHealthRead,
    MarketStructureSourceRead,
    MarketStructureSourceUpdate,
)
from src.apps.market_structure.query_services import MarketStructureQueryService
from src.apps.market_structure.repositories import MarketStructureSourceRepository
from src.apps.market_structure.services.polling_service import MarketStructurePollingService
from src.apps.market_structure.services.source_command_service import MarketStructureSourceCommandService
from src.core.db.uow import BaseAsyncUnitOfWork


class MarketStructureService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._queries = MarketStructureQueryService(uow.session)
        self._sources = MarketStructureSourceRepository(uow.session)
        self._commands = MarketStructureSourceCommandService(uow)
        self._polling = MarketStructurePollingService(uow)

    async def list_plugins(self):
        return await self._queries.list_plugins()

    async def list_sources(self):
        return await self._queries.list_sources()

    async def get_source(self, source_id: int):
        return await self._sources.get_by_id(source_id)

    async def read_source_health(self, source_id: int) -> MarketStructureSourceHealthRead | None:
        item = await self._queries.get_source_health_read_by_id(source_id)
        if item is None:
            return None
        return MarketStructureSourceHealthRead.model_validate(item)

    async def refresh_source_health(self, *, emit_events: bool = True):
        return await self._polling.refresh_source_health(emit_events=emit_events)

    async def create_source(self, payload: MarketStructureSourceCreate) -> MarketStructureSourceRead:
        return await self._commands.create_source(payload)

    async def update_source(
        self,
        source_id: int,
        payload: MarketStructureSourceUpdate,
    ) -> MarketStructureSourceRead | None:
        return await self._commands.update_source(source_id, payload)

    async def delete_source(self, source_id: int) -> bool:
        return await self._commands.delete_source(source_id)

    async def list_snapshots(
        self,
        *,
        coin_symbol: str | None = None,
        venue: str | None = None,
        limit: int = 50,
    ) -> list[MarketStructureSnapshotRead]:
        items = await self._queries.list_snapshots(coin_symbol=coin_symbol, venue=venue, limit=limit)
        return [MarketStructureSnapshotRead.model_validate(item) for item in items]

    async def poll_source(self, *, source_id: int, limit: int = 1):
        return await self._polling.poll_source(source_id=source_id, limit=limit)

    async def poll_enabled_sources(self, *, limit_per_source: int = 1):
        return await self._polling.poll_enabled_sources(limit_per_source=limit_per_source)

    async def ingest_manual_snapshots(
        self,
        *,
        source_id: int,
        payload: ManualMarketStructureIngestRequest,
        ingest_token: str | None = None,
    ):
        return await self._polling.ingest_manual_snapshots(
            source_id=source_id,
            payload=payload,
            ingest_token=ingest_token,
        )

    async def ingest_native_webhook_payload(
        self,
        *,
        source_id: int,
        payload: dict[str, object],
        ingest_token: str | None = None,
    ):
        return await self._polling.ingest_native_webhook_payload(
            source_id=source_id,
            payload=dict(payload),
            ingest_token=ingest_token,
        )


__all__ = ["MarketStructureService"]
