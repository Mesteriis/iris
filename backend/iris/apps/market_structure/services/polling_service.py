from typing import Any

from iris.apps.market_data.domain import ensure_utc, utc_now
from iris.apps.market_structure.constants import DEFAULT_MARKET_STRUCTURE_POLL_LIMIT
from iris.apps.market_structure.contracts import ManualMarketStructureIngestRequest, MarketStructureSourceHealthRead
from iris.apps.market_structure.engines.health_engine import (
    apply_market_structure_alert_transition,
    build_market_structure_source_health,
    isoformat_or_none,
    mark_market_structure_poll_failure,
    mark_market_structure_source_success,
    market_structure_backoff_active,
    market_structure_is_quarantined,
    market_structure_source_provider,
    sync_market_structure_source_health_fields,
)
from iris.apps.market_structure.exceptions import (
    UnauthorizedMarketStructureIngestError,
    UnsupportedMarketStructurePluginError,
)
from iris.apps.market_structure.normalizers import create_market_structure_webhook_normalizer
from iris.apps.market_structure.plugins import (
    FetchedMarketStructureSnapshot,
    create_market_structure_plugin,
    get_market_structure_plugin,
)
from iris.apps.market_structure.services._shared import MarketStructureServiceSupport
from iris.apps.market_structure.services.results import (
    MarketStructureIngestResult,
    MarketStructurePollBatchResult,
    MarketStructurePollSourceResult,
    MarketStructureRefreshHealthResult,
)


class MarketStructurePollingService(MarketStructureServiceSupport):
    async def refresh_source_health(self, *, emit_events: bool = True) -> MarketStructureRefreshHealthResult:
        rows = await self._sources.list_all_for_update()
        now = utc_now()
        changed_sources = 0
        for source in rows:
            previous_health_status = source.health_status
            if sync_market_structure_source_health_fields(source, now=now):
                alert_kind = (
                    apply_market_structure_alert_transition(
                        source,
                        previous_health_status=previous_health_status,
                        now=now,
                    )
                    if emit_events
                    else None
                )
                changed_sources += 1
                if emit_events:
                    await self._publish_source_health_dispatch(source, alert_kind=alert_kind, now=now)
        return MarketStructureRefreshHealthResult(status="ok", sources=len(rows), changed=changed_sources)

    async def poll_source(
        self,
        *,
        source_id: int,
        limit: int = DEFAULT_MARKET_STRUCTURE_POLL_LIMIT,
    ) -> MarketStructurePollSourceResult:
        source = await self._sources.get_for_update(source_id)
        if source is None:
            return MarketStructurePollSourceResult(status="error", source_id=source_id, reason="source_not_found")
        if market_structure_is_quarantined(source):
            return MarketStructurePollSourceResult(
                status="skipped",
                source_id=source_id,
                plugin_name=source.plugin_name,
                reason="source_quarantined",
                quarantined=True,
                quarantined_at=isoformat_or_none(source.quarantined_at),
                quarantine_reason=source.quarantine_reason,
            )
        if not source.enabled:
            return MarketStructurePollSourceResult(status="skipped", source_id=source_id, reason="source_disabled")

        current_time = utc_now()
        if market_structure_backoff_active(source, now=current_time):
            return MarketStructurePollSourceResult(
                status="skipped",
                source_id=source_id,
                plugin_name=source.plugin_name,
                reason="source_backoff",
                consecutive_failures=int(source.consecutive_failures or 0),
                backoff_until=isoformat_or_none(source.backoff_until),
            )

        plugin = create_market_structure_plugin(source)
        if not plugin.descriptor.supports_polling:
            return MarketStructurePollSourceResult(
                status="skipped",
                source_id=source_id,
                plugin_name=source.plugin_name,
                reason="plugin_requires_manual_ingest",
            )
        try:
            result = await plugin.fetch_snapshots(cursor=dict(source.cursor_json or {}), limit=limit)
        except Exception as exc:
            source.last_polled_at = utc_now()
            previous_health_status = source.health_status
            mark_market_structure_poll_failure(source, error_message=str(exc), now=source.last_polled_at)
            sync_market_structure_source_health_fields(source, now=source.last_polled_at)
            alert_kind = apply_market_structure_alert_transition(
                source,
                previous_health_status=previous_health_status,
                now=source.last_polled_at,
            )
            await self._publish_source_health_dispatch(source, alert_kind=alert_kind, now=source.last_polled_at)
            return MarketStructurePollSourceResult(
                status="error",
                source_id=source_id,
                plugin_name=source.plugin_name,
                reason="poll_failed",
                error=source.last_error,
                consecutive_failures=int(source.consecutive_failures or 0),
                backoff_until=isoformat_or_none(source.backoff_until),
                quarantined=market_structure_is_quarantined(source),
                quarantine_reason=source.quarantine_reason,
            )

        source.cursor_json = dict(result.next_cursor)
        source.last_polled_at = utc_now()
        persisted = await self._persist_snapshots(source=source, snapshots=result.snapshots)
        previous_health_status = source.health_status
        mark_market_structure_source_success(
            source,
            now=source.last_polled_at,
            latest_snapshot_at=persisted.latest_snapshot_at,
        )
        sync_market_structure_source_health_fields(source, now=source.last_polled_at)
        alert_kind = apply_market_structure_alert_transition(
            source,
            previous_health_status=previous_health_status,
            now=source.last_polled_at,
        )
        self._publish_snapshot_events(persisted)
        await self._publish_source_health_dispatch(source, alert_kind=alert_kind, now=source.last_polled_at)
        return MarketStructurePollSourceResult(
            status="ok",
            source_id=int(source.id),
            plugin_name=source.plugin_name,
            fetched=len(result.snapshots),
            created=persisted.created,
            cursor=dict(source.cursor_json or {}),
        )

    async def poll_enabled_sources(
        self,
        *,
        limit_per_source: int = DEFAULT_MARKET_STRUCTURE_POLL_LIMIT,
    ) -> MarketStructurePollBatchResult:
        rows = await self._sources.list_enabled_ids()
        items = [await self.poll_source(source_id=int(source_id), limit=limit_per_source) for source_id in rows]
        return MarketStructurePollBatchResult(
            status="ok",
            sources=len(rows),
            items=tuple(items),
            created=sum(item.created for item in items),
        )

    async def ingest_manual_snapshots(
        self,
        *,
        source_id: int,
        payload: ManualMarketStructureIngestRequest,
        ingest_token: str | None = None,
    ) -> MarketStructureIngestResult:
        source = await self._sources.get_for_update(source_id)
        if source is None:
            return MarketStructureIngestResult(status="error", source_id=source_id, reason="source_not_found")

        plugin_cls = get_market_structure_plugin(source.plugin_name)
        if plugin_cls is None:
            raise UnsupportedMarketStructurePluginError(f"Unsupported market structure plugin '{source.plugin_name}'.")
        if not plugin_cls.descriptor.supports_manual_ingest:
            return MarketStructureIngestResult(
                status="skipped",
                source_id=source_id,
                plugin_name=source.plugin_name,
                reason="plugin_does_not_support_manual_ingest",
            )

        required_token = str((source.credentials_json or {}).get("ingest_token") or "").strip()
        if required_token and required_token != str(ingest_token or "").strip():
            raise UnauthorizedMarketStructureIngestError("Manual ingest token is missing or invalid.")

        settings = dict(source.settings_json or {})
        snapshots = [
            FetchedMarketStructureSnapshot(
                venue=str(item.venue or settings.get("venue") or "manual").strip().lower(),
                timestamp=ensure_utc(item.timestamp),
                last_price=item.last_price,
                mark_price=item.mark_price,
                index_price=item.index_price,
                funding_rate=item.funding_rate,
                open_interest=item.open_interest,
                basis=item.basis,
                liquidations_long=item.liquidations_long,
                liquidations_short=item.liquidations_short,
                volume=item.volume,
                payload_json=dict(item.payload_json),
            )
            for item in payload.snapshots
        ]
        persisted = await self._persist_snapshots(source=source, snapshots=snapshots)
        source.last_polled_at = utc_now()
        previous_health_status = source.health_status
        mark_market_structure_source_success(
            source,
            now=source.last_polled_at,
            latest_snapshot_at=persisted.latest_snapshot_at,
        )
        sync_market_structure_source_health_fields(source, now=source.last_polled_at)
        alert_kind = apply_market_structure_alert_transition(
            source,
            previous_health_status=previous_health_status,
            now=source.last_polled_at,
        )
        self._publish_snapshot_events(persisted)
        await self._publish_source_health_dispatch(source, alert_kind=alert_kind, now=source.last_polled_at)
        return MarketStructureIngestResult(
            status="ok",
            source_id=int(source.id),
            plugin_name=source.plugin_name,
            created=persisted.created,
        )

    async def ingest_native_webhook_payload(
        self,
        *,
        source_id: int,
        payload: dict[str, Any],
        ingest_token: str | None = None,
    ) -> MarketStructureIngestResult:
        source = await self._sources.get_by_id(source_id)
        if source is None:
            return MarketStructureIngestResult(status="error", source_id=source_id, reason="source_not_found")

        settings = dict(source.settings_json or {})
        provider = market_structure_source_provider(source)
        venue = str(settings.get("venue") or provider or "manual").strip().lower()
        normalizer = create_market_structure_webhook_normalizer(provider=provider, venue=venue)
        normalized_payload = normalizer.normalize_payload(payload)
        return await self.ingest_manual_snapshots(
            source_id=source_id,
            payload=normalized_payload,
            ingest_token=ingest_token,
        )

    async def read_source_health(self, source_id: int) -> MarketStructureSourceHealthRead | None:
        item = await self._queries.get_source_health_read_by_id(source_id)
        if item is None:
            return None
        return MarketStructureSourceHealthRead.model_validate(item)


__all__ = ["MarketStructurePollingService"]
