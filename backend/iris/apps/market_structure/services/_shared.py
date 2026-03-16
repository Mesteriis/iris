from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from iris.apps.market_data.domain import ensure_utc, utc_now
from iris.apps.market_structure.constants import MARKET_STRUCTURE_ALERT_KIND_QUARANTINED
from iris.apps.market_structure.engines.health_engine import (
    market_structure_source_alert_event_payload,
    market_structure_source_health_event_payload,
)
from iris.apps.market_structure.exceptions import InvalidMarketStructureSourceConfigurationError
from iris.apps.market_structure.models import MarketStructureSource
from iris.apps.market_structure.plugins import FetchedMarketStructureSnapshot
from iris.apps.market_structure.query_services import MarketStructureQueryService
from iris.apps.market_structure.repositories import (
    MarketStructureCoinRepository,
    MarketStructureSnapshotPersistResult,
    MarketStructureSnapshotRepository,
    MarketStructureSourceRepository,
)
from iris.apps.market_structure.services.side_effects import MarketStructureSideEffectDispatcher
from iris.core.db.uow import BaseAsyncUnitOfWork

if TYPE_CHECKING:
    from iris.apps.market_data.models import Coin


class MarketStructureServiceSupport:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._queries = MarketStructureQueryService(uow.session)
        self._sources = MarketStructureSourceRepository(uow.session)
        self._coins = MarketStructureCoinRepository(uow.session)
        self._snapshots = MarketStructureSnapshotRepository(uow.session)
        self._side_effects = MarketStructureSideEffectDispatcher(uow)

    async def _resolve_coin(self, coin_symbol: str) -> Coin:
        coin = await self._coins.get_by_symbol(coin_symbol)
        if coin is None:
            raise InvalidMarketStructureSourceConfigurationError(f"Coin '{coin_symbol.upper()}' was not found.")
        return coin

    async def _source_event_context(self, source: MarketStructureSource) -> dict[str, Any] | None:
        settings = dict(source.settings_json or {})
        coin_symbol = str(settings.get("coin_symbol") or "").strip().upper()
        if not coin_symbol:
            return None
        try:
            coin = await self._resolve_coin(coin_symbol)
        except InvalidMarketStructureSourceConfigurationError:
            return None
        return {
            "coin_id": int(coin.id),
            "timeframe": int(settings.get("timeframe") or 15),
            "symbol": coin_symbol,
            "venue": str(settings.get("venue") or "manual").strip().lower(),
        }

    async def _persist_snapshots(
        self,
        *,
        source: MarketStructureSource,
        snapshots: list[FetchedMarketStructureSnapshot],
    ) -> MarketStructureSnapshotPersistResult:
        if not snapshots:
            return MarketStructureSnapshotPersistResult(created=0, latest_snapshot_at=None, events=())
        settings = dict(source.settings_json or {})
        coin = await self._resolve_coin(str(settings.get("coin_symbol") or ""))
        timeframe = int(settings.get("timeframe") or 15)
        return await self._snapshots.upsert_many(
            coin=coin,
            timeframe=timeframe,
            source=source,
            snapshots=snapshots,
        )

    def _publish_snapshot_events(self, result: MarketStructureSnapshotPersistResult) -> None:
        for item in result.events:
            self._side_effects.publish_snapshot_ingested(
                payload={
                    "coin_id": int(item.coin_id),
                    "timeframe": int(item.timeframe),
                    "timestamp": item.timestamp,
                    "source_id": int(item.source_id),
                    "plugin_name": item.plugin_name,
                    "symbol": item.symbol,
                    "venue": item.venue,
                }
            )

    async def _publish_source_health_dispatch(
        self,
        source: MarketStructureSource,
        *,
        alert_kind: str | None = None,
        now: datetime | None = None,
    ) -> None:
        emitted_at = ensure_utc(now or utc_now())
        context = await self._source_event_context(source)
        if context is None:
            return
        self._side_effects.publish_source_health_updated(
            payload={**context, **market_structure_source_health_event_payload(source, now=emitted_at)}
        )
        if alert_kind is None:
            return
        payload = {
            **context,
            **market_structure_source_alert_event_payload(source, alert_kind=alert_kind, now=emitted_at),
        }
        self._side_effects.publish_source_alerted(payload=payload)
        if alert_kind == MARKET_STRUCTURE_ALERT_KIND_QUARANTINED:
            self._side_effects.publish_source_quarantined(payload=payload)

    async def _publish_source_deleted(self, source: MarketStructureSource, *, now: datetime) -> None:
        context = await self._source_event_context(source)
        if context is None:
            return
        self._side_effects.publish_source_deleted(
            payload={**context, **market_structure_source_health_event_payload(source, now=ensure_utc(now))}
        )


__all__ = ["MarketStructureServiceSupport"]
