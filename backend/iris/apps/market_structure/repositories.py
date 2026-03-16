from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from iris.apps.anomalies.models import MarketStructureSnapshot
from iris.apps.market_data.domain import ensure_utc
from iris.apps.market_data.models import Coin
from iris.apps.market_structure.models import MarketStructureSource
from iris.apps.market_structure.plugins import FetchedMarketStructureSnapshot
from iris.core.db.persistence import AsyncRepository


@dataclass(slots=True, frozen=True)
class MarketStructureSnapshotIngestedEvent:
    coin_id: int
    timeframe: int
    timestamp: datetime
    source_id: int
    plugin_name: str
    symbol: str
    venue: str


@dataclass(slots=True, frozen=True)
class MarketStructureSnapshotPersistResult:
    created: int
    latest_snapshot_at: datetime | None
    events: tuple[MarketStructureSnapshotIngestedEvent, ...]


class MarketStructureSourceRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="market_structure", repository_name="MarketStructureSourceRepository")

    async def get_by_id(self, source_id: int) -> MarketStructureSource | None:
        self._log_debug("repo.get_market_structure_source", mode="read", source_id=source_id)
        source = await self.session.get(MarketStructureSource, source_id)
        self._log_debug("repo.get_market_structure_source.result", mode="read", found=source is not None)
        return source

    async def get_for_update(self, source_id: int) -> MarketStructureSource | None:
        self._log_debug("repo.get_market_structure_source_for_update", mode="write", source_id=source_id, lock=True)
        source = await self.session.scalar(
            select(MarketStructureSource).where(MarketStructureSource.id == source_id).with_for_update().limit(1)
        )
        self._log_debug("repo.get_market_structure_source_for_update.result", mode="write", found=source is not None)
        return source

    async def get_by_plugin_display_name(
        self,
        *,
        plugin_name: str,
        display_name: str,
        exclude_source_id: int | None = None,
    ) -> MarketStructureSource | None:
        self._log_debug(
            "repo.get_market_structure_source_by_plugin_display_name",
            mode="write",
            plugin_name=plugin_name,
            display_name=display_name,
            exclude_source_id=exclude_source_id,
        )
        stmt = select(MarketStructureSource).where(
            MarketStructureSource.plugin_name == plugin_name,
            MarketStructureSource.display_name == display_name,
        )
        if exclude_source_id is not None:
            stmt = stmt.where(MarketStructureSource.id != exclude_source_id)
        source = await self.session.scalar(stmt.limit(1))
        self._log_debug(
            "repo.get_market_structure_source_by_plugin_display_name.result",
            mode="write",
            found=source is not None,
        )
        return source

    async def list_enabled_ids(self) -> tuple[int, ...]:
        self._log_debug("repo.list_enabled_market_structure_source_ids", mode="write")
        rows = (
            (
                await self.session.execute(
                    select(MarketStructureSource.id)
                    .where(MarketStructureSource.enabled.is_(True))
                    .order_by(MarketStructureSource.updated_at.asc(), MarketStructureSource.id.asc())
                )
            )
            .scalars()
            .all()
        )
        items = tuple(int(value) for value in rows)
        self._log_debug("repo.list_enabled_market_structure_source_ids.result", mode="write", count=len(items))
        return items

    async def list_all_for_update(self) -> list[MarketStructureSource]:
        self._log_debug("repo.list_market_structure_sources_for_update", mode="write", lock=True)
        rows = (
            (
                await self.session.execute(
                    select(MarketStructureSource)
                    .order_by(MarketStructureSource.updated_at.asc(), MarketStructureSource.id.asc())
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        items = list(rows)
        self._log_debug("repo.list_market_structure_sources_for_update.result", mode="write", count=len(items))
        return items

    async def add(self, source: MarketStructureSource) -> MarketStructureSource:
        self._log_info("repo.add_market_structure_source", mode="write", plugin_name=source.plugin_name)
        self.session.add(source)
        await self.session.flush()
        return source

    async def delete(self, source: MarketStructureSource) -> None:
        self._log_info("repo.delete_market_structure_source", mode="write", source_id=int(source.id))
        await self.session.delete(source)
        await self.session.flush()

    async def refresh(self, source: MarketStructureSource) -> None:
        await self.session.refresh(source)


class MarketStructureCoinRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="market_structure", repository_name="MarketStructureCoinRepository")

    async def get_by_symbol(self, coin_symbol: str) -> Coin | None:
        normalized_symbol = coin_symbol.upper()
        self._log_debug("repo.get_market_structure_coin_by_symbol", mode="read", coin_symbol=normalized_symbol)
        coin = await self.session.scalar(
            select(Coin).where(Coin.symbol == normalized_symbol, Coin.deleted_at.is_(None)).limit(1)
        )
        self._log_debug("repo.get_market_structure_coin_by_symbol.result", mode="read", found=coin is not None)
        return coin


class MarketStructureSnapshotRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="market_structure", repository_name="MarketStructureSnapshotRepository")

    async def upsert_many(
        self,
        *,
        coin: Coin,
        timeframe: int,
        source: MarketStructureSource,
        snapshots: list[FetchedMarketStructureSnapshot],
    ) -> MarketStructureSnapshotPersistResult:
        self._log_info(
            "repo.upsert_market_structure_snapshots",
            mode="write",
            bulk=True,
            count=len(snapshots),
            strategy="core_upsert",
            source_id=int(source.id),
        )
        if not snapshots:
            return MarketStructureSnapshotPersistResult(created=0, latest_snapshot_at=None, events=())

        created = 0
        latest_snapshot_at: datetime | None = None
        events: list[MarketStructureSnapshotIngestedEvent] = []
        for snapshot in snapshots:
            payload_json = dict(snapshot.payload_json or {})
            payload_json.update(
                {
                    "source_id": int(source.id),
                    "source_display_name": source.display_name,
                    "plugin_name": source.plugin_name,
                }
            )
            venue = str(snapshot.venue).lower()
            snapshot_timestamp = ensure_utc(snapshot.timestamp)
            stmt = (
                insert(MarketStructureSnapshot)
                .values(
                    coin_id=int(coin.id),
                    symbol=str(coin.symbol),
                    timeframe=timeframe,
                    venue=venue,
                    timestamp=snapshot_timestamp,
                    last_price=snapshot.last_price,
                    mark_price=snapshot.mark_price,
                    index_price=snapshot.index_price,
                    funding_rate=snapshot.funding_rate,
                    open_interest=snapshot.open_interest,
                    basis=snapshot.basis,
                    liquidations_long=snapshot.liquidations_long,
                    liquidations_short=snapshot.liquidations_short,
                    volume=snapshot.volume,
                    payload_json=payload_json,
                )
                .on_conflict_do_update(
                    index_elements=["coin_id", "timeframe", "venue", "timestamp"],
                    set_={
                        "last_price": snapshot.last_price,
                        "mark_price": snapshot.mark_price,
                        "index_price": snapshot.index_price,
                        "funding_rate": snapshot.funding_rate,
                        "open_interest": snapshot.open_interest,
                        "basis": snapshot.basis,
                        "liquidations_long": snapshot.liquidations_long,
                        "liquidations_short": snapshot.liquidations_short,
                        "volume": snapshot.volume,
                        "payload_json": payload_json,
                    },
                )
            )
            await self.session.execute(stmt)
            created += 1
            if latest_snapshot_at is None or snapshot_timestamp > latest_snapshot_at:
                latest_snapshot_at = snapshot_timestamp
            events.append(
                MarketStructureSnapshotIngestedEvent(
                    coin_id=int(coin.id),
                    timeframe=int(timeframe),
                    timestamp=snapshot_timestamp,
                    source_id=int(source.id),
                    plugin_name=str(source.plugin_name),
                    symbol=str(coin.symbol),
                    venue=venue,
                )
            )
        await self.session.flush()
        return MarketStructureSnapshotPersistResult(
            created=created,
            latest_snapshot_at=latest_snapshot_at,
            events=tuple(events),
        )


__all__ = [
    "MarketStructureCoinRepository",
    "MarketStructureSnapshotIngestedEvent",
    "MarketStructureSnapshotPersistResult",
    "MarketStructureSnapshotRepository",
    "MarketStructureSourceRepository",
]
