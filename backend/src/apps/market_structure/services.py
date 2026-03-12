from __future__ import annotations

import secrets
from datetime import timedelta
from typing import Any

from src.apps.market_data.domain import ensure_utc, utc_now
from src.apps.market_data.models import Coin
from src.apps.market_structure.constants import (
    DEFAULT_MARKET_STRUCTURE_FAILURE_BACKOFF_BASE_SECONDS,
    DEFAULT_MARKET_STRUCTURE_FAILURE_BACKOFF_MAX_SECONDS,
    DEFAULT_MARKET_STRUCTURE_POLL_LIMIT,
    DEFAULT_MARKET_STRUCTURE_QUARANTINE_AFTER_FAILURES,
    MARKET_STRUCTURE_ALERT_KIND_ERROR,
    MARKET_STRUCTURE_ALERT_KIND_QUARANTINED,
    MARKET_STRUCTURE_ALERT_KIND_STALE,
    MARKET_STRUCTURE_EVENT_SOURCE_ALERTED,
    MARKET_STRUCTURE_EVENT_SOURCE_DELETED,
    MARKET_STRUCTURE_EVENT_SOURCE_HEALTH_UPDATED,
    MARKET_STRUCTURE_EVENT_SOURCE_QUARANTINED,
    MARKET_STRUCTURE_EVENT_SNAPSHOT_INGESTED,
    MARKET_STRUCTURE_HEALTH_STATUS_DISABLED,
    MARKET_STRUCTURE_HEALTH_STATUS_ERROR,
    MARKET_STRUCTURE_HEALTH_STATUS_HEALTHY,
    MARKET_STRUCTURE_HEALTH_STATUS_IDLE,
    MARKET_STRUCTURE_HEALTH_STATUS_QUARANTINED,
    MARKET_STRUCTURE_HEALTH_STATUS_STALE,
    MARKET_STRUCTURE_INGEST_TOKEN_HEADER,
    MARKET_STRUCTURE_INGEST_TOKEN_QUERY_PARAMETER,
    MARKET_STRUCTURE_MANUAL_PROVIDER_COINALYZE,
    MARKET_STRUCTURE_MANUAL_PROVIDER_COINGLASS,
    MARKET_STRUCTURE_MANUAL_INGEST_MODE_WEBHOOK,
    MARKET_STRUCTURE_MANUAL_PROVIDER_DERIVATIVES_WEBHOOK,
    MARKET_STRUCTURE_MANUAL_PROVIDER_HYBLOCK,
    MARKET_STRUCTURE_MANUAL_PROVIDER_LIQSCOPE,
    MARKET_STRUCTURE_MANUAL_PROVIDER_LIQUIDATION_WEBHOOK,
    MARKET_STRUCTURE_PLUGIN_BINANCE_USDM,
    MARKET_STRUCTURE_PLUGIN_BYBIT_DERIVATIVES,
    MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH,
    MARKET_STRUCTURE_SOURCE_STATUS_ACTIVE,
    MARKET_STRUCTURE_SOURCE_STATUS_DISABLED,
    MARKET_STRUCTURE_SOURCE_STATUS_ERROR,
    MARKET_STRUCTURE_SOURCE_STATUS_QUARANTINED,
)
from src.apps.market_structure.exceptions import (
    InvalidMarketStructureSourceConfigurationError,
    InvalidMarketStructureWebhookPayloadError,
    UnsupportedMarketStructurePluginError,
    UnauthorizedMarketStructureIngestError,
)
from src.apps.market_structure.models import MarketStructureSource
from src.apps.market_structure.normalizers import (
    create_market_structure_webhook_normalizer,
)
from src.apps.market_structure.plugins import (
    FetchedMarketStructureSnapshot,
    create_market_structure_plugin,
    get_market_structure_plugin,
)
from src.apps.market_structure.query_services import MarketStructureQueryService
from src.apps.market_structure.read_models import (
    market_structure_source_read_model_from_orm,
    market_structure_webhook_registration_read_model_from_orm,
)
from src.apps.market_structure.repositories import (
    MarketStructureCoinRepository,
    MarketStructureSnapshotPersistResult,
    MarketStructureSnapshotRepository,
    MarketStructureSourceRepository,
)
from src.apps.market_structure.schemas import (
    BinanceMarketStructureSourceCreateRequest,
    BybitMarketStructureSourceCreateRequest,
    ManualMarketStructureIngestRequest,
    ManualWebhookMarketStructureSourceCreateRequest,
    ManualPushMarketStructureSourceCreateRequest,
    MarketStructureOnboardingFieldRead,
    MarketStructureOnboardingPresetRead,
    MarketStructureOnboardingRead,
    MarketStructurePluginRead,
    MarketStructureSnapshotCreate,
    MarketStructureSnapshotRead,
    MarketStructureSourceCreate,
    MarketStructureSourceHealthRead,
    MarketStructureSourceRead,
    MarketStructureSourceUpdate,
    MarketStructureWebhookRegistrationRead,
)
from src.core.db.persistence import thaw_json_value
from src.core.db.uow import BaseAsyncUnitOfWork
from src.core.settings import get_settings
from src.runtime.streams.publisher import publish_event


def _merge_mapping(base: dict[str, Any], patch: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    if patch is None:
        return merged
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def _webhook_registration_schema_from_read_model(item) -> MarketStructureWebhookRegistrationRead:
    return MarketStructureWebhookRegistrationRead.model_validate(
        {
            "source": MarketStructureSourceRead.model_validate(item.source),
            "provider": item.provider,
            "venue": item.venue,
            "ingest_path": item.ingest_path,
            "native_ingest_path": item.native_ingest_path,
            "method": item.method,
            "token_header": item.token_header,
            "token_query_parameter": item.token_query_parameter,
            "token_required": bool(item.token_required),
            "token": item.token,
            "sample_payload": thaw_json_value(item.sample_payload),
            "native_payload_example": thaw_json_value(item.native_payload_example),
            "notes": list(item.notes),
        }
    )


def _source_status(source: MarketStructureSource) -> str:
    if source.quarantined_at is not None:
        return MARKET_STRUCTURE_SOURCE_STATUS_QUARANTINED
    if not source.enabled:
        return MARKET_STRUCTURE_SOURCE_STATUS_DISABLED
    if source.last_error:
        return MARKET_STRUCTURE_SOURCE_STATUS_ERROR
    return MARKET_STRUCTURE_SOURCE_STATUS_ACTIVE


def _credential_fields_present(credentials: dict[str, Any]) -> list[str]:
    return sorted([key for key, value in credentials.items() if value not in (None, "", [], {}, ())])


def _isoformat_or_none(value) -> str | None:
    return ensure_utc(value).isoformat() if value is not None else None


def _is_quarantined(source: MarketStructureSource) -> bool:
    return source.quarantined_at is not None


def _backoff_until_or_none(source: MarketStructureSource) -> object | None:
    return ensure_utc(source.backoff_until) if source.backoff_until is not None else None


def _backoff_active(source: MarketStructureSource, *, now) -> bool:
    backoff_until = _backoff_until_or_none(source)
    return backoff_until is not None and backoff_until > ensure_utc(now)


def _backoff_seconds_for_failure_count(consecutive_failures: int) -> int:
    settings = get_settings()
    base_seconds = max(
        int(getattr(settings, "taskiq_market_structure_failure_backoff_base_seconds", 0))
        or DEFAULT_MARKET_STRUCTURE_FAILURE_BACKOFF_BASE_SECONDS,
        0,
    )
    max_seconds = max(
        int(getattr(settings, "taskiq_market_structure_failure_backoff_max_seconds", 0))
        or DEFAULT_MARKET_STRUCTURE_FAILURE_BACKOFF_MAX_SECONDS,
        base_seconds,
    )
    if consecutive_failures <= 0 or base_seconds <= 0:
        return 0
    return min(base_seconds * (2 ** max(consecutive_failures - 1, 0)), max_seconds)


def _quarantine_after_failures() -> int:
    settings = get_settings()
    return max(
        int(getattr(settings, "taskiq_market_structure_quarantine_after_failures", 0))
        or DEFAULT_MARKET_STRUCTURE_QUARANTINE_AFTER_FAILURES,
        0,
    )


def _serialize_plugin(plugin_cls) -> MarketStructurePluginRead:
    descriptor = plugin_cls.descriptor
    return MarketStructurePluginRead(
        name=descriptor.name,
        display_name=descriptor.display_name,
        description=descriptor.description,
        auth_mode=descriptor.auth_mode,
        supported=descriptor.supported,
        supports_polling=descriptor.supports_polling,
        supports_manual_ingest=descriptor.supports_manual_ingest,
        required_credentials=list(descriptor.required_credentials),
        required_settings=list(descriptor.required_settings),
        runtime_dependencies=list(descriptor.runtime_dependencies),
        unsupported_reason=descriptor.unsupported_reason,
    )


def _serialize_source(source: MarketStructureSource) -> MarketStructureSourceRead:
    health = _build_source_health(source)
    return MarketStructureSourceRead(
        id=int(source.id),
        plugin_name=source.plugin_name,
        display_name=source.display_name,
        enabled=bool(source.enabled),
        status=_source_status(source),
        auth_mode=source.auth_mode,
        credential_fields_present=_credential_fields_present(dict(source.credentials_json or {})),
        settings=dict(source.settings_json or {}),
        cursor=dict(source.cursor_json or {}),
        last_polled_at=source.last_polled_at,
        last_success_at=source.last_success_at,
        last_snapshot_at=source.last_snapshot_at,
        last_error=source.last_error,
        health_status=source.health_status,
        health_changed_at=source.health_changed_at,
        consecutive_failures=int(source.consecutive_failures or 0),
        backoff_until=source.backoff_until,
        quarantined_at=source.quarantined_at,
        quarantine_reason=source.quarantine_reason,
        last_alerted_at=source.last_alerted_at,
        last_alert_kind=source.last_alert_kind,
        health=health,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def _sample_webhook_payload() -> dict[str, Any]:
    return {
        "snapshots": [
            {
                "timestamp": "2026-03-12T12:00:00+00:00",
                "last_price": 3150.0,
                "funding_rate": 0.0009,
                "open_interest": 21000.0,
                "liquidations_long": 3300.0,
                "liquidations_short": 120.0,
            }
        ]
    }


def _source_provider(source: MarketStructureSource) -> str:
    settings = dict(source.settings_json or {})
    return str(settings.get("provider") or settings.get("venue") or MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH).strip().lower()


def _source_ingest_mode(source: MarketStructureSource) -> str:
    settings = dict(source.settings_json or {})
    explicit = str(settings.get("ingest_mode") or "").strip().lower()
    if explicit:
        return explicit
    plugin_cls = get_market_structure_plugin(source.plugin_name)
    if plugin_cls is not None and plugin_cls.descriptor.supports_polling:
        return "polling"
    return "manual"


def _stale_after_seconds(source: MarketStructureSource) -> int | None:
    settings = get_settings()
    timeframe_minutes = max(int((source.settings_json or {}).get("timeframe") or 15), 1)
    timeframe_seconds = timeframe_minutes * 60
    ingest_mode = _source_ingest_mode(source)
    if ingest_mode == MARKET_STRUCTURE_MANUAL_INGEST_MODE_WEBHOOK:
        return max(timeframe_seconds * 6, 1800)
    plugin_cls = get_market_structure_plugin(source.plugin_name)
    if plugin_cls is not None and plugin_cls.descriptor.supports_polling:
        return max(int(settings.taskiq_market_structure_snapshot_poll_interval_seconds) * 3, timeframe_seconds * 3)
    return max(timeframe_seconds * 12, 3600)


def _build_source_health(
    source: MarketStructureSource,
    *,
    now=None,
) -> MarketStructureSourceHealthRead:
    current_time = ensure_utc(now or utc_now())
    last_activity_at = source.last_polled_at
    last_success_at = source.last_success_at
    last_snapshot_at = source.last_snapshot_at
    stale_after_seconds = _stale_after_seconds(source)
    ingest_mode = _source_ingest_mode(source)
    backoff_until = _backoff_until_or_none(source)
    backoff_active = _backoff_active(source, now=current_time)
    consecutive_failures = int(source.consecutive_failures or 0)
    quarantined = _is_quarantined(source)
    if quarantined:
        status = MARKET_STRUCTURE_HEALTH_STATUS_QUARANTINED
        severity = "critical"
        stale = False
        message = str(source.quarantine_reason or "Source was quarantined after repeated polling failures.")
    elif not source.enabled:
        status = MARKET_STRUCTURE_HEALTH_STATUS_DISABLED
        severity = "info"
        stale = False
        message = "Source is disabled."
    elif source.last_error:
        status = MARKET_STRUCTURE_HEALTH_STATUS_ERROR
        severity = "error"
        stale = False
        if backoff_active and backoff_until is not None:
            retry_in_seconds = max(int((backoff_until - current_time).total_seconds()), 0)
            message = f"{source.last_error}. Retry scheduled in {retry_in_seconds}s."
        else:
            message = str(source.last_error)
    else:
        reference_candidates = [value for value in (last_snapshot_at, last_success_at) if value is not None]
        reference_time = max((ensure_utc(value) for value in reference_candidates), default=None)
        if reference_time is None:
            status = MARKET_STRUCTURE_HEALTH_STATUS_IDLE
            severity = "info"
            stale = False
            message = "Waiting for first successful snapshot."
        else:
            age_seconds = max(int((current_time - ensure_utc(reference_time)).total_seconds()), 0)
            if stale_after_seconds is not None and age_seconds > stale_after_seconds:
                status = MARKET_STRUCTURE_HEALTH_STATUS_STALE
                severity = "warning"
                stale = True
                message = f"Source is stale. Latest successful activity is {age_seconds}s old."
            else:
                status = MARKET_STRUCTURE_HEALTH_STATUS_HEALTHY
                severity = "ok"
                stale = False
                message = "Source is healthy."
    return MarketStructureSourceHealthRead(
        status=status,
        severity=severity,
        ingest_mode=ingest_mode,
        stale=stale,
        stale_after_seconds=stale_after_seconds,
        last_activity_at=last_activity_at,
        last_success_at=last_success_at,
        last_snapshot_at=last_snapshot_at,
        last_error=source.last_error,
        health_changed_at=source.health_changed_at,
        consecutive_failures=consecutive_failures,
        backoff_until=backoff_until,
        backoff_active=backoff_active,
        quarantined=quarantined,
        quarantined_at=source.quarantined_at,
        quarantine_reason=source.quarantine_reason,
        last_alerted_at=source.last_alerted_at,
        last_alert_kind=source.last_alert_kind,
        message=message,
    )


class MarketStructureService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._queries = MarketStructureQueryService(uow.session)
        self._sources = MarketStructureSourceRepository(uow.session)
        self._coins = MarketStructureCoinRepository(uow.session)
        self._snapshots = MarketStructureSnapshotRepository(uow.session)

    async def list_plugins(self):
        return await self._queries.list_plugins()

    async def list_sources(self):
        return await self._queries.list_sources()

    async def get_source(self, source_id: int) -> MarketStructureSource | None:
        return await self._sources.get_by_id(source_id)

    async def read_source_health(self, source_id: int) -> MarketStructureSourceHealthRead | None:
        item = await self._queries.get_source_health_read_by_id(source_id)
        if item is None:
            return None
        return MarketStructureSourceHealthRead.model_validate(item)

    async def refresh_source_health(self, *, emit_events: bool = True) -> dict[str, object]:
        rows = await self._sources.list_all_for_update()
        now = utc_now()
        changed_sources: list[tuple[MarketStructureSource, str | None]] = []
        for source in rows:
            previous_health_status = source.health_status
            if self._sync_source_health_fields(source, now=now):
                alert_kind = (
                    self._apply_alert_transition(
                        source,
                        previous_health_status=previous_health_status,
                        now=now,
                    )
                    if emit_events
                    else None
                )
                changed_sources.append((source, alert_kind))
        await self._uow.commit()
        if emit_events:
            for source, alert_kind in changed_sources:
                await self._emit_source_health_event(source, now=now)
                await self._emit_source_alert_event(source, alert_kind=alert_kind, now=now)
        return {
            "status": "ok",
            "sources": len(rows),
            "changed": len(changed_sources),
        }

    async def create_source(self, payload: MarketStructureSourceCreate) -> MarketStructureSourceRead:
        plugin_name = payload.plugin_name.strip().lower()
        plugin_cls = get_market_structure_plugin(plugin_name)
        if plugin_cls is None:
            raise InvalidMarketStructureSourceConfigurationError(
                f"Unsupported market structure plugin '{payload.plugin_name}'."
            )
        plugin_cls.validate_configuration(credentials=payload.credentials, settings=payload.settings)
        existing = await self._sources.get_by_plugin_display_name(
            plugin_name=plugin_name,
            display_name=payload.display_name.strip(),
        )
        if existing is not None:
            raise InvalidMarketStructureSourceConfigurationError(
                f"Market structure source '{payload.display_name.strip()}' already exists for plugin '{plugin_name}'."
            )
        source = await self._sources.add(
            MarketStructureSource(
                plugin_name=plugin_name,
                display_name=payload.display_name.strip(),
                enabled=payload.enabled,
                auth_mode=plugin_cls.descriptor.auth_mode,
                credentials_json=dict(payload.credentials),
                settings_json=dict(payload.settings),
                cursor_json={},
            )
        )
        self._sync_source_health_fields(source, now=utc_now())
        await self._uow.commit()
        await self._sources.refresh(source)
        await self._emit_source_health_event(source)
        item = await self._queries.get_source_read_by_id(int(source.id))
        return MarketStructureSourceRead.model_validate(
            item if item is not None else market_structure_source_read_model_from_orm(source)
        )

    async def update_source(
        self, source_id: int, payload: MarketStructureSourceUpdate
    ) -> MarketStructureSourceRead | None:
        source = await self._sources.get_for_update(source_id)
        if source is None:
            return None

        plugin_cls = get_market_structure_plugin(source.plugin_name)
        if plugin_cls is None:
            raise InvalidMarketStructureSourceConfigurationError(
                f"Unsupported market structure plugin '{source.plugin_name}'."
            )

        display_name = payload.display_name.strip() if payload.display_name is not None else source.display_name
        merged_credentials = _merge_mapping(dict(source.credentials_json or {}), payload.credentials)
        merged_settings = _merge_mapping(dict(source.settings_json or {}), payload.settings)
        plugin_cls.validate_configuration(credentials=merged_credentials, settings=merged_settings)

        if display_name != source.display_name:
            existing = await self._sources.get_by_plugin_display_name(
                plugin_name=source.plugin_name,
                display_name=display_name,
                exclude_source_id=int(source.id),
            )
            if existing is not None:
                raise InvalidMarketStructureSourceConfigurationError(
                    f"Market structure source '{display_name}' already exists for plugin '{source.plugin_name}'."
                )
            source.display_name = display_name

        if payload.enabled is not None:
            source.enabled = payload.enabled
        if payload.credentials is not None:
            source.credentials_json = merged_credentials
        if payload.settings is not None:
            source.settings_json = merged_settings
        if payload.reset_cursor:
            source.cursor_json = {}
        if payload.clear_error:
            self._clear_failure_state(source)
            source.last_error = None
        if payload.release_quarantine:
            source.quarantined_at = None
            source.quarantine_reason = None
            self._clear_failure_state(source)
        now = utc_now()
        previous_health_status = source.health_status
        self._sync_source_health_fields(source, now=now)
        alert_kind = self._apply_alert_transition(source, previous_health_status=previous_health_status, now=now)

        await self._uow.commit()
        await self._sources.refresh(source)
        await self._emit_source_health_event(source, now=now)
        await self._emit_source_alert_event(source, alert_kind=alert_kind, now=now)
        item = await self._queries.get_source_read_by_id(int(source.id))
        return MarketStructureSourceRead.model_validate(
            item if item is not None else market_structure_source_read_model_from_orm(source, now=now)
        )

    async def delete_source(self, source_id: int) -> bool:
        source = await self._sources.get_for_update(source_id)
        if source is None:
            return False
        event_context = await self._source_event_context(source)
        payload = self._source_health_event_payload(source, now=utc_now())
        await self._sources.delete(source)
        await self._uow.commit()
        if event_context is not None:
            publish_event(
                MARKET_STRUCTURE_EVENT_SOURCE_DELETED,
                {
                    **event_context,
                    **payload,
                },
            )
        return True

    async def list_snapshots(
        self,
        *,
        coin_symbol: str | None = None,
        venue: str | None = None,
        limit: int = 50,
    ) -> list[MarketStructureSnapshotRead]:
        items = await self._queries.list_snapshots(coin_symbol=coin_symbol, venue=venue, limit=limit)
        return [MarketStructureSnapshotRead.model_validate(item) for item in items]

    async def poll_source(
        self,
        *,
        source_id: int,
        limit: int = DEFAULT_MARKET_STRUCTURE_POLL_LIMIT,
    ) -> dict[str, object]:
        source = await self._sources.get_for_update(source_id)
        if source is None:
            return {"status": "error", "reason": "source_not_found", "source_id": source_id}
        if _is_quarantined(source):
            return {
                "status": "skipped",
                "reason": "source_quarantined",
                "source_id": source_id,
                "plugin_name": source.plugin_name,
                "quarantined_at": _isoformat_or_none(source.quarantined_at),
                "quarantine_reason": source.quarantine_reason,
            }
        if not source.enabled:
            return {"status": "skipped", "reason": "source_disabled", "source_id": source_id}
        if _backoff_active(source, now=utc_now()):
            return {
                "status": "skipped",
                "reason": "source_backoff",
                "source_id": source_id,
                "plugin_name": source.plugin_name,
                "backoff_until": _isoformat_or_none(source.backoff_until),
                "consecutive_failures": int(source.consecutive_failures or 0),
            }

        plugin = create_market_structure_plugin(source)
        if not plugin.descriptor.supports_polling:
            return {
                "status": "skipped",
                "reason": "plugin_requires_manual_ingest",
                "source_id": source_id,
                "plugin_name": source.plugin_name,
            }
        try:
            result = await plugin.fetch_snapshots(cursor=dict(source.cursor_json or {}), limit=limit)
        except Exception as exc:
            source.last_polled_at = utc_now()
            previous_health_status = source.health_status
            self._mark_poll_failure(source, error_message=str(exc), now=source.last_polled_at)
            self._sync_source_health_fields(source, now=source.last_polled_at)
            alert_kind = self._apply_alert_transition(
                source,
                previous_health_status=previous_health_status,
                now=source.last_polled_at,
            )
            await self._uow.commit()
            await self._emit_source_health_event(source, now=source.last_polled_at)
            await self._emit_source_alert_event(source, alert_kind=alert_kind, now=source.last_polled_at)
            return {
                "status": "error",
                "reason": "poll_failed",
                "source_id": source_id,
                "plugin_name": source.plugin_name,
                "error": source.last_error,
                "consecutive_failures": int(source.consecutive_failures or 0),
                "backoff_until": _isoformat_or_none(source.backoff_until),
                "quarantined": _is_quarantined(source),
                "quarantine_reason": source.quarantine_reason,
            }

        source.cursor_json = dict(result.next_cursor)
        source.last_polled_at = utc_now()
        persisted = await self._persist_snapshots(source=source, snapshots=result.snapshots)
        previous_health_status = source.health_status
        self._mark_source_success(source, now=source.last_polled_at, latest_snapshot_at=persisted.latest_snapshot_at)
        self._sync_source_health_fields(source, now=source.last_polled_at)
        alert_kind = self._apply_alert_transition(
            source, previous_health_status=previous_health_status, now=source.last_polled_at
        )
        await self._uow.commit()
        self._publish_snapshot_events(persisted)
        await self._emit_source_health_event(source, now=source.last_polled_at)
        await self._emit_source_alert_event(source, alert_kind=alert_kind, now=source.last_polled_at)
        return {
            "status": "ok",
            "source_id": int(source.id),
            "plugin_name": source.plugin_name,
            "fetched": len(result.snapshots),
            "created": persisted.created,
            "cursor": dict(source.cursor_json or {}),
        }

    async def poll_enabled_sources(
        self, *, limit_per_source: int = DEFAULT_MARKET_STRUCTURE_POLL_LIMIT
    ) -> dict[str, object]:
        rows = await self._sources.list_enabled_ids()
        items = []
        for source_id in rows:
            items.append(await self.poll_source(source_id=int(source_id), limit=limit_per_source))
        return {
            "status": "ok",
            "sources": len(rows),
            "items": items,
            "created": sum(int(item.get("created", 0)) for item in items),
        }

    async def ingest_manual_snapshots(
        self,
        *,
        source_id: int,
        payload: ManualMarketStructureIngestRequest,
        ingest_token: str | None = None,
    ) -> dict[str, object]:
        source = await self._sources.get_for_update(source_id)
        if source is None:
            return {"status": "error", "reason": "source_not_found", "source_id": source_id}
        plugin_cls = get_market_structure_plugin(source.plugin_name)
        if plugin_cls is None:
            raise UnsupportedMarketStructurePluginError(f"Unsupported market structure plugin '{source.plugin_name}'.")
        if not plugin_cls.descriptor.supports_manual_ingest:
            return {
                "status": "skipped",
                "reason": "plugin_does_not_support_manual_ingest",
                "source_id": source_id,
                "plugin_name": source.plugin_name,
            }
        required_token = str((source.credentials_json or {}).get("ingest_token") or "").strip()
        if required_token and required_token != str(ingest_token or "").strip():
            raise UnauthorizedMarketStructureIngestError("Manual ingest token is missing or invalid.")

        snapshots = [
            FetchedMarketStructureSnapshot(
                venue=str(item.venue or source.settings_json.get("venue") or "manual").strip().lower(),
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
        self._mark_source_success(source, now=source.last_polled_at, latest_snapshot_at=persisted.latest_snapshot_at)
        self._sync_source_health_fields(source, now=source.last_polled_at)
        alert_kind = self._apply_alert_transition(
            source, previous_health_status=previous_health_status, now=source.last_polled_at
        )
        await self._uow.commit()
        self._publish_snapshot_events(persisted)
        await self._emit_source_health_event(source, now=source.last_polled_at)
        await self._emit_source_alert_event(source, alert_kind=alert_kind, now=source.last_polled_at)
        return {
            "status": "ok",
            "source_id": int(source.id),
            "plugin_name": source.plugin_name,
            "created": persisted.created,
        }

    async def ingest_native_webhook_payload(
        self,
        *,
        source_id: int,
        payload: dict[str, Any],
        ingest_token: str | None = None,
    ) -> dict[str, object]:
        source = await self._sources.get_by_id(source_id)
        if source is None:
            return {"status": "error", "reason": "source_not_found", "source_id": source_id}
        provider = _source_provider(source)
        venue = str((source.settings_json or {}).get("venue") or provider or "manual").strip().lower()
        normalizer = create_market_structure_webhook_normalizer(provider=provider, venue=venue)
        normalized_payload = normalizer.normalize_payload(payload)
        return await self.ingest_manual_snapshots(
            source_id=source_id,
            payload=normalized_payload,
            ingest_token=ingest_token,
        )

    @staticmethod
    def _clear_failure_state(source: MarketStructureSource) -> None:
        source.consecutive_failures = 0
        source.backoff_until = None

    def _mark_poll_failure(self, source: MarketStructureSource, *, error_message: str, now) -> None:
        failure_count = int(source.consecutive_failures or 0) + 1
        source.last_error = str(error_message)[:255]
        source.consecutive_failures = failure_count

        quarantine_after_failures = _quarantine_after_failures()
        if quarantine_after_failures > 0 and failure_count >= quarantine_after_failures:
            source.enabled = False
            source.backoff_until = None
            source.quarantined_at = ensure_utc(now)
            source.quarantine_reason = (
                f"Source entered quarantine after {failure_count} consecutive polling failures: {source.last_error}"
            )[:255]
            return

        backoff_seconds = _backoff_seconds_for_failure_count(failure_count)
        if backoff_seconds > 0:
            source.backoff_until = ensure_utc(now) + timedelta(seconds=backoff_seconds)
        else:
            source.backoff_until = None

    def _mark_source_success(self, source: MarketStructureSource, *, now, latest_snapshot_at) -> None:
        source.last_success_at = ensure_utc(now)
        if latest_snapshot_at is not None:
            source.last_snapshot_at = latest_snapshot_at
        source.last_error = None
        self._clear_failure_state(source)

    def _sync_source_health_fields(self, source: MarketStructureSource, *, now) -> bool:
        health = _build_source_health(source, now=now)
        changed = source.health_status != health.status
        source.health_status = health.status
        if changed or source.health_changed_at is None:
            source.health_changed_at = ensure_utc(now)
        return changed

    @staticmethod
    def _next_alert_kind(previous_health_status: str | None, current_health_status: str) -> str | None:
        if current_health_status == MARKET_STRUCTURE_HEALTH_STATUS_QUARANTINED:
            return (
                MARKET_STRUCTURE_ALERT_KIND_QUARANTINED
                if previous_health_status != MARKET_STRUCTURE_HEALTH_STATUS_QUARANTINED
                else None
            )
        if current_health_status == MARKET_STRUCTURE_HEALTH_STATUS_ERROR:
            return (
                MARKET_STRUCTURE_ALERT_KIND_ERROR
                if previous_health_status != MARKET_STRUCTURE_HEALTH_STATUS_ERROR
                else None
            )
        if current_health_status == MARKET_STRUCTURE_HEALTH_STATUS_STALE:
            return (
                MARKET_STRUCTURE_ALERT_KIND_STALE
                if previous_health_status != MARKET_STRUCTURE_HEALTH_STATUS_STALE
                else None
            )
        return None

    def _apply_alert_transition(
        self,
        source: MarketStructureSource,
        *,
        previous_health_status: str | None,
        now,
    ) -> str | None:
        alert_kind = self._next_alert_kind(previous_health_status, _build_source_health(source, now=now).status)
        if alert_kind is None:
            return None
        source.last_alert_kind = alert_kind
        source.last_alerted_at = ensure_utc(now)
        return alert_kind

    async def _source_event_context(self, source: MarketStructureSource) -> dict[str, Any] | None:
        coin_symbol = str((source.settings_json or {}).get("coin_symbol") or "").strip().upper()
        if not coin_symbol:
            return None
        try:
            coin = await self._resolve_coin(coin_symbol)
        except InvalidMarketStructureSourceConfigurationError:
            return None
        return {
            "coin_id": int(coin.id),
            "timeframe": int((source.settings_json or {}).get("timeframe") or 15),
            "symbol": coin_symbol,
            "venue": str((source.settings_json or {}).get("venue") or "manual").strip().lower(),
        }

    def _source_health_event_payload(
        self,
        source: MarketStructureSource,
        *,
        now,
    ) -> dict[str, Any]:
        health = _build_source_health(source, now=now)
        return {
            "timestamp": ensure_utc(now),
            "source_id": int(source.id),
            "plugin_name": source.plugin_name,
            "display_name": source.display_name,
            "enabled": bool(source.enabled),
            "auth_mode": source.auth_mode,
            "health_status": health.status,
            "health_severity": health.severity,
            "ingest_mode": health.ingest_mode,
            "stale": bool(health.stale),
            "stale_after_seconds": health.stale_after_seconds,
            "last_activity_at": _isoformat_or_none(health.last_activity_at),
            "last_success_at": _isoformat_or_none(health.last_success_at),
            "last_snapshot_at": _isoformat_or_none(health.last_snapshot_at),
            "last_error": health.last_error,
            "health_changed_at": _isoformat_or_none(health.health_changed_at),
            "consecutive_failures": int(health.consecutive_failures),
            "backoff_until": _isoformat_or_none(health.backoff_until),
            "backoff_active": bool(health.backoff_active),
            "quarantined": bool(health.quarantined),
            "quarantined_at": _isoformat_or_none(health.quarantined_at),
            "quarantine_reason": health.quarantine_reason,
            "last_alerted_at": _isoformat_or_none(health.last_alerted_at),
            "last_alert_kind": health.last_alert_kind,
            "message": health.message,
        }

    def _source_alert_event_payload(
        self,
        source: MarketStructureSource,
        *,
        alert_kind: str,
        now,
    ) -> dict[str, Any]:
        health = _build_source_health(source, now=now)
        rule = {
            MARKET_STRUCTURE_ALERT_KIND_ERROR: "poll_failure_detected",
            MARKET_STRUCTURE_ALERT_KIND_STALE: "source_stale_detected",
            MARKET_STRUCTURE_ALERT_KIND_QUARANTINED: "poll_failure_quarantine_triggered",
        }[alert_kind]
        recommended_action = {
            MARKET_STRUCTURE_ALERT_KIND_ERROR: "Allow backoff to retry or inspect source credentials and upstream API health.",
            MARKET_STRUCTURE_ALERT_KIND_STALE: "Inspect upstream collector latency and recent snapshot ingestion flow.",
            MARKET_STRUCTURE_ALERT_KIND_QUARANTINED: "Review the source, clear the error, release quarantine, then re-enable polling.",
        }[alert_kind]
        return {
            **self._source_health_event_payload(source, now=now),
            "alert_kind": alert_kind,
            "rule": rule,
            "recommended_action": recommended_action,
            "severity": health.severity,
        }

    async def _emit_source_health_event(self, source: MarketStructureSource, *, now=None) -> None:
        emitted_at = ensure_utc(now or utc_now())
        context = await self._source_event_context(source)
        if context is None:
            return
        publish_event(
            MARKET_STRUCTURE_EVENT_SOURCE_HEALTH_UPDATED,
            {
                **context,
                **self._source_health_event_payload(source, now=emitted_at),
            },
        )

    async def _emit_source_alert_event(
        self,
        source: MarketStructureSource,
        *,
        alert_kind: str | None,
        now=None,
    ) -> None:
        if alert_kind is None:
            return
        emitted_at = ensure_utc(now or utc_now())
        context = await self._source_event_context(source)
        if context is None:
            return

        payload = {
            **context,
            **self._source_alert_event_payload(source, alert_kind=alert_kind, now=emitted_at),
        }
        publish_event(MARKET_STRUCTURE_EVENT_SOURCE_ALERTED, payload)
        if alert_kind == MARKET_STRUCTURE_ALERT_KIND_QUARANTINED:
            publish_event(MARKET_STRUCTURE_EVENT_SOURCE_QUARANTINED, payload)

    async def _resolve_coin(self, coin_symbol: str) -> Coin:
        coin = await self._coins.get_by_symbol(coin_symbol)
        if coin is None:
            raise InvalidMarketStructureSourceConfigurationError(f"Coin '{coin_symbol.upper()}' was not found.")
        return coin

    async def _persist_snapshots(
        self,
        *,
        source: MarketStructureSource,
        snapshots: list[FetchedMarketStructureSnapshot],
    ) -> MarketStructureSnapshotPersistResult:
        if not snapshots:
            return MarketStructureSnapshotPersistResult(created=0, latest_snapshot_at=None, events=())
        coin = await self._resolve_coin(str(source.settings_json.get("coin_symbol") or ""))
        timeframe = int(source.settings_json.get("timeframe") or 15)
        return await self._snapshots.upsert_many(coin=coin, timeframe=timeframe, source=source, snapshots=snapshots)

    @staticmethod
    def _publish_snapshot_events(result: MarketStructureSnapshotPersistResult) -> None:
        for item in result.events:
            publish_event(
                MARKET_STRUCTURE_EVENT_SNAPSHOT_INGESTED,
                {
                    "coin_id": int(item.coin_id),
                    "timeframe": int(item.timeframe),
                    "timestamp": item.timestamp,
                    "source_id": int(item.source_id),
                    "plugin_name": item.plugin_name,
                    "symbol": item.symbol,
                    "venue": item.venue,
                },
            )


class MarketStructureSourceProvisioningService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._uow = uow
        self._service = MarketStructureService(uow)
        self._queries = MarketStructureQueryService(uow.session)
        self._sources = MarketStructureSourceRepository(uow.session)

    async def create_binance_source(
        self,
        payload: BinanceMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureSourceRead:
        payload = BinanceMarketStructureSourceCreateRequest.model_validate(payload)
        request = MarketStructureSourceCreate(
            plugin_name=MARKET_STRUCTURE_PLUGIN_BINANCE_USDM,
            display_name=(payload.display_name or f"{payload.coin_symbol.upper()} Binance USD-M").strip(),
            enabled=bool(payload.enabled),
            settings={
                "coin_symbol": payload.coin_symbol.upper(),
                "market_symbol": self._resolve_market_symbol(payload.coin_symbol, payload.market_symbol),
                "timeframe": int(payload.timeframe),
                "venue": (payload.venue or "binance_usdm").strip().lower(),
            },
        )
        return await self._service.create_source(request)

    async def create_bybit_source(
        self,
        payload: BybitMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureSourceRead:
        payload = BybitMarketStructureSourceCreateRequest.model_validate(payload)
        request = MarketStructureSourceCreate(
            plugin_name=MARKET_STRUCTURE_PLUGIN_BYBIT_DERIVATIVES,
            display_name=(payload.display_name or f"{payload.coin_symbol.upper()} Bybit Derivatives").strip(),
            enabled=bool(payload.enabled),
            settings={
                "coin_symbol": payload.coin_symbol.upper(),
                "market_symbol": self._resolve_market_symbol(payload.coin_symbol, payload.market_symbol),
                "timeframe": int(payload.timeframe),
                "venue": (payload.venue or "bybit_derivatives").strip().lower(),
                "category": payload.category.strip().lower(),
            },
        )
        return await self._service.create_source(request)

    async def create_manual_source(
        self,
        payload: ManualPushMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureSourceRead:
        payload = ManualPushMarketStructureSourceCreateRequest.model_validate(payload)
        request = MarketStructureSourceCreate(
            plugin_name=MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH,
            display_name=(
                payload.display_name or f"{payload.coin_symbol.upper()} {payload.venue.strip()} Feed"
            ).strip(),
            enabled=bool(payload.enabled),
            settings={
                "coin_symbol": payload.coin_symbol.upper(),
                "timeframe": int(payload.timeframe),
                "venue": payload.venue.strip().lower(),
            },
        )
        return await self._service.create_source(request)

    async def create_liqscope_webhook_source(
        self,
        payload: ManualWebhookMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureWebhookRegistrationRead:
        return await self._create_webhook_source(
            payload=payload,
            provider=MARKET_STRUCTURE_MANUAL_PROVIDER_LIQSCOPE,
            venue_default=MARKET_STRUCTURE_MANUAL_PROVIDER_LIQSCOPE,
            display_suffix="Liqscope Webhook",
        )

    async def create_liquidation_webhook_source(
        self,
        payload: ManualWebhookMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureWebhookRegistrationRead:
        return await self._create_webhook_source(
            payload=payload,
            provider=MARKET_STRUCTURE_MANUAL_PROVIDER_LIQUIDATION_WEBHOOK,
            venue_default="liquidations_api",
            display_suffix="Liquidation Webhook",
        )

    async def create_derivatives_webhook_source(
        self,
        payload: ManualWebhookMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureWebhookRegistrationRead:
        return await self._create_webhook_source(
            payload=payload,
            provider=MARKET_STRUCTURE_MANUAL_PROVIDER_DERIVATIVES_WEBHOOK,
            venue_default="derivatives_webhook",
            display_suffix="Derivatives Webhook",
        )

    async def create_coinglass_webhook_source(
        self,
        payload: ManualWebhookMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureWebhookRegistrationRead:
        return await self._create_webhook_source(
            payload=payload,
            provider=MARKET_STRUCTURE_MANUAL_PROVIDER_COINGLASS,
            venue_default=MARKET_STRUCTURE_MANUAL_PROVIDER_COINGLASS,
            display_suffix="Coinglass Webhook",
        )

    async def create_hyblock_webhook_source(
        self,
        payload: ManualWebhookMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureWebhookRegistrationRead:
        return await self._create_webhook_source(
            payload=payload,
            provider=MARKET_STRUCTURE_MANUAL_PROVIDER_HYBLOCK,
            venue_default=MARKET_STRUCTURE_MANUAL_PROVIDER_HYBLOCK,
            display_suffix="Hyblock Webhook",
        )

    async def create_coinalyze_webhook_source(
        self,
        payload: ManualWebhookMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureWebhookRegistrationRead:
        return await self._create_webhook_source(
            payload=payload,
            provider=MARKET_STRUCTURE_MANUAL_PROVIDER_COINALYZE,
            venue_default=MARKET_STRUCTURE_MANUAL_PROVIDER_COINALYZE,
            display_suffix="Coinalyze Webhook",
        )

    async def read_webhook_registration(
        self,
        source_id: int,
        *,
        include_token: bool = False,
    ) -> MarketStructureWebhookRegistrationRead | None:
        item = await self._queries.get_webhook_registration_read_by_id(source_id, include_token=include_token)
        if item is None:
            return None
        return _webhook_registration_schema_from_read_model(item)

    async def rotate_webhook_token(self, source_id: int) -> MarketStructureWebhookRegistrationRead | None:
        source = await self._sources.get_for_update(source_id)
        if source is None:
            return None
        self._ensure_webhook_capable_source(source)
        credentials = dict(source.credentials_json or {})
        credentials["ingest_token"] = self._issue_ingest_token()
        source.credentials_json = credentials
        await self._uow.commit()
        await self._sources.refresh(source)
        item = await self._queries.get_webhook_registration_read_by_id(source_id, include_token=True)
        return _webhook_registration_schema_from_read_model(
            item
            if item is not None
            else market_structure_webhook_registration_read_model_from_orm(source, include_token=True)
        )

    @staticmethod
    def wizard_spec() -> MarketStructureOnboardingRead:
        return MarketStructureOnboardingRead(
            title="Market Structure Source Wizard",
            presets=[
                MarketStructureOnboardingPresetRead(
                    id="binance_usdm",
                    plugin_name=MARKET_STRUCTURE_PLUGIN_BINANCE_USDM,
                    title="Binance USD-M",
                    description="Create a public polling source for mark price, index price, funding and open interest from Binance USD-M Futures.",
                    endpoint="/market-structure/onboarding/sources/binance-usdm",
                    method="POST",
                    fields=[
                        MarketStructureOnboardingFieldRead(
                            id="coin_symbol",
                            label="Coin Symbol",
                            type="text",
                            required=True,
                            description="Internal IRIS coin symbol, e.g. ETHUSD_EVT.",
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="timeframe", label="Timeframe", type="number", required=True, default=15
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="display_name", label="Display Name", type="text", required=False
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="market_symbol",
                            label="Exchange Symbol",
                            type="text",
                            required=False,
                            description="Optional. Defaults to inferred USDT perpetual symbol.",
                        ),
                    ],
                    source_payload_example={
                        "coin_symbol": "ETHUSD_EVT",
                        "timeframe": 15,
                        "display_name": "ETH Binance USD-M",
                    },
                ),
                MarketStructureOnboardingPresetRead(
                    id="bybit_derivatives",
                    plugin_name=MARKET_STRUCTURE_PLUGIN_BYBIT_DERIVATIVES,
                    title="Bybit Derivatives",
                    description="Create a public polling source for mark price, index price, funding and open interest from Bybit derivatives.",
                    endpoint="/market-structure/onboarding/sources/bybit-derivatives",
                    method="POST",
                    fields=[
                        MarketStructureOnboardingFieldRead(
                            id="coin_symbol",
                            label="Coin Symbol",
                            type="text",
                            required=True,
                            description="Internal IRIS coin symbol, e.g. ETHUSD_EVT.",
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="timeframe", label="Timeframe", type="number", required=True, default=15
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="display_name", label="Display Name", type="text", required=False
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="market_symbol", label="Exchange Symbol", type="text", required=False
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="category", label="Category", type="text", required=False, default="linear"
                        ),
                    ],
                    source_payload_example={
                        "coin_symbol": "ETHUSD_EVT",
                        "timeframe": 15,
                        "display_name": "ETH Bybit Derivatives",
                        "category": "linear",
                    },
                ),
                MarketStructureOnboardingPresetRead(
                    id="manual_push",
                    plugin_name=MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH,
                    title="Manual Push Feed",
                    description="Create a source for external collectors that push liquidation or derivatives snapshots directly into IRIS.",
                    endpoint="/market-structure/onboarding/sources/manual-push",
                    method="POST",
                    fields=[
                        MarketStructureOnboardingFieldRead(
                            id="coin_symbol", label="Coin Symbol", type="text", required=True
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="timeframe", label="Timeframe", type="number", required=True, default=15
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="venue",
                            label="Venue",
                            type="text",
                            required=True,
                            description="Logical source name, e.g. liqscope or liquidation_api.",
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="display_name", label="Display Name", type="text", required=False
                        ),
                    ],
                    source_payload_example={
                        "coin_symbol": "ETHUSD_EVT",
                        "timeframe": 15,
                        "venue": "liqscope",
                        "display_name": "ETH Liquidation Feed",
                    },
                ),
                MarketStructureOnboardingPresetRead(
                    id="liqscope_webhook",
                    plugin_name=MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH,
                    title="Liqscope Webhook",
                    description="Register a write-only manual push source for Liqscope-style liquidation collectors and return a webhook token.",
                    endpoint="/market-structure/onboarding/sources/liqscope-webhook",
                    method="POST",
                    fields=[
                        MarketStructureOnboardingFieldRead(
                            id="coin_symbol", label="Coin Symbol", type="text", required=True
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="timeframe", label="Timeframe", type="number", required=True, default=15
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="display_name", label="Display Name", type="text", required=False
                        ),
                    ],
                    source_payload_example={
                        "coin_symbol": "ETHUSD_EVT",
                        "timeframe": 15,
                        "display_name": "ETH Liqscope Webhook",
                    },
                ),
                MarketStructureOnboardingPresetRead(
                    id="liquidation_webhook",
                    plugin_name=MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH,
                    title="Liquidation Collector Webhook",
                    description="Register a token-protected webhook for generic liquidation collectors that post snapshots into IRIS.",
                    endpoint="/market-structure/onboarding/sources/liquidation-webhook",
                    method="POST",
                    fields=[
                        MarketStructureOnboardingFieldRead(
                            id="coin_symbol", label="Coin Symbol", type="text", required=True
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="timeframe", label="Timeframe", type="number", required=True, default=15
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="display_name", label="Display Name", type="text", required=False
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="venue", label="Venue", type="text", required=False, default="liquidations_api"
                        ),
                    ],
                    source_payload_example={
                        "coin_symbol": "BTCUSD_EVT",
                        "timeframe": 15,
                        "venue": "liquidations_api",
                        "display_name": "BTC Liquidation Webhook",
                    },
                ),
                MarketStructureOnboardingPresetRead(
                    id="derivatives_webhook",
                    plugin_name=MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH,
                    title="Derivatives Snapshot Webhook",
                    description="Register a token-protected webhook for external derivatives collectors that push funding, OI and liquidation snapshots.",
                    endpoint="/market-structure/onboarding/sources/derivatives-webhook",
                    method="POST",
                    fields=[
                        MarketStructureOnboardingFieldRead(
                            id="coin_symbol", label="Coin Symbol", type="text", required=True
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="timeframe", label="Timeframe", type="number", required=True, default=15
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="display_name", label="Display Name", type="text", required=False
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="venue", label="Venue", type="text", required=False, default="derivatives_webhook"
                        ),
                    ],
                    source_payload_example={
                        "coin_symbol": "SOLUSD_EVT",
                        "timeframe": 15,
                        "venue": "derivatives_webhook",
                        "display_name": "SOL Derivatives Webhook",
                    },
                ),
                MarketStructureOnboardingPresetRead(
                    id="coinglass_webhook",
                    plugin_name=MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH,
                    title="Coinglass Webhook",
                    description="Register a token-protected webhook for Coinglass-style liquidation collectors.",
                    endpoint="/market-structure/onboarding/sources/coinglass-webhook",
                    method="POST",
                    fields=[
                        MarketStructureOnboardingFieldRead(
                            id="coin_symbol", label="Coin Symbol", type="text", required=True
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="timeframe", label="Timeframe", type="number", required=True, default=15
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="display_name", label="Display Name", type="text", required=False
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="venue", label="Venue", type="text", required=False, default="coinglass"
                        ),
                    ],
                    source_payload_example={
                        "coin_symbol": "ETHUSD_EVT",
                        "timeframe": 15,
                        "venue": "coinglass",
                        "display_name": "ETH Coinglass Webhook",
                    },
                ),
                MarketStructureOnboardingPresetRead(
                    id="hyblock_webhook",
                    plugin_name=MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH,
                    title="Hyblock Webhook",
                    description="Register a token-protected webhook for Hyblock-style liquidation collectors.",
                    endpoint="/market-structure/onboarding/sources/hyblock-webhook",
                    method="POST",
                    fields=[
                        MarketStructureOnboardingFieldRead(
                            id="coin_symbol", label="Coin Symbol", type="text", required=True
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="timeframe", label="Timeframe", type="number", required=True, default=15
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="display_name", label="Display Name", type="text", required=False
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="venue", label="Venue", type="text", required=False, default="hyblock"
                        ),
                    ],
                    source_payload_example={
                        "coin_symbol": "BTCUSD_EVT",
                        "timeframe": 15,
                        "venue": "hyblock",
                        "display_name": "BTC Hyblock Webhook",
                    },
                ),
                MarketStructureOnboardingPresetRead(
                    id="coinalyze_webhook",
                    plugin_name=MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH,
                    title="Coinalyze Webhook",
                    description="Register a token-protected webhook for Coinalyze-style derivatives collectors.",
                    endpoint="/market-structure/onboarding/sources/coinalyze-webhook",
                    method="POST",
                    fields=[
                        MarketStructureOnboardingFieldRead(
                            id="coin_symbol", label="Coin Symbol", type="text", required=True
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="timeframe", label="Timeframe", type="number", required=True, default=15
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="display_name", label="Display Name", type="text", required=False
                        ),
                        MarketStructureOnboardingFieldRead(
                            id="venue", label="Venue", type="text", required=False, default="coinalyze"
                        ),
                    ],
                    source_payload_example={
                        "coin_symbol": "SOLUSD_EVT",
                        "timeframe": 15,
                        "venue": "coinalyze",
                        "display_name": "SOL Coinalyze Webhook",
                    },
                ),
            ],
            notes=[
                "Frontend can create polling sources without constructing low-level plugin settings manually.",
                "If exchange symbol is omitted, IRIS derives a default USDT perpetual symbol from the internal coin symbol.",
                "Manual push feeds are intended for external collectors and webhooks that already aggregate liquidation or derivatives data.",
                "Webhook onboarding presets create a manual_push source and return a source-level ingest token for external collectors.",
                "Webhook tokens can be rotated from the frontend without editing raw credentials.",
            ],
        )

    @staticmethod
    def _resolve_market_symbol(coin_symbol: str, market_symbol: str | None) -> str:
        if market_symbol not in (None, ""):
            return market_symbol.strip().upper()
        normalized = coin_symbol.strip().upper()
        if normalized.endswith("_EVT"):
            normalized = normalized[:-4]
        if normalized.endswith("USDT"):
            return normalized
        if normalized.endswith("USD"):
            return f"{normalized[:-3]}USDT"
        return normalized

    async def _create_webhook_source(
        self,
        *,
        payload: ManualWebhookMarketStructureSourceCreateRequest | dict[str, Any],
        provider: str,
        venue_default: str,
        display_suffix: str,
    ) -> MarketStructureWebhookRegistrationRead:
        payload = ManualWebhookMarketStructureSourceCreateRequest.model_validate(payload)
        source = await self._service.create_source(
            MarketStructureSourceCreate(
                plugin_name=MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH,
                display_name=(payload.display_name or f"{payload.coin_symbol.upper()} {display_suffix}").strip(),
                enabled=bool(payload.enabled),
                credentials={"ingest_token": self._issue_ingest_token()},
                settings={
                    "coin_symbol": payload.coin_symbol.upper(),
                    "timeframe": int(payload.timeframe),
                    "venue": (payload.venue or venue_default).strip().lower(),
                    "provider": provider,
                    "ingest_mode": MARKET_STRUCTURE_MANUAL_INGEST_MODE_WEBHOOK,
                },
            )
        )
        item = await self._queries.get_webhook_registration_read_by_id(int(source.id), include_token=True)
        if item is None:
            raise InvalidMarketStructureSourceConfigurationError("Webhook source could not be reloaded after creation.")
        return _webhook_registration_schema_from_read_model(item)

    @staticmethod
    def _issue_ingest_token() -> str:
        return secrets.token_urlsafe(24)

    @staticmethod
    def _ensure_webhook_capable_source(source: MarketStructureSource) -> None:
        if source.plugin_name != MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH:
            raise InvalidMarketStructureSourceConfigurationError(
                "Webhook registration is only available for manual_push sources."
            )

    @staticmethod
    def _build_webhook_registration(
        source: MarketStructureSource,
        *,
        include_token: bool,
    ) -> MarketStructureWebhookRegistrationRead:
        return _webhook_registration_schema_from_read_model(
            market_structure_webhook_registration_read_model_from_orm(source, include_token=include_token)
        )
