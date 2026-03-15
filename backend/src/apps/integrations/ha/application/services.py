from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from secrets import token_hex
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.apps.indicators.models import CoinMetrics
from src.apps.integrations.ha.application.control_state import HA_TIMEFRAME_OPTIONS, HAControlStateStore
from src.apps.integrations.ha.schemas import (
    HAAvailabilityRead,
    HABootstrapRead,
    HACapabilitiesRead,
    HACatalogRead,
    HACollectionDefinitionRead,
    HACollectionPatchMessage,
    HACollectionSnapshotMessage,
    HACommandDefinitionRead,
    HADashboardRead,
    HADashboardSectionRead,
    HADashboardViewRead,
    HADashboardWidgetRead,
    HAEntityDefinitionRead,
    HAEntityStateChangedMessage,
    HAEntityStateRead,
    HAEventEmittedMessage,
    HAHealthRead,
    HAInstanceRead,
    HAOperationRead,
    HAOperationUpdateMessage,
    HAResyncRequiredMessage,
    HAStatePatchMessage,
    HAStateSnapshotRead,
)
from src.apps.market_data.models import Coin
from src.apps.notifications.query_services import NotificationQueryService
from src.apps.portfolio.models import PortfolioPosition
from src.apps.portfolio.query_services import PortfolioQueryService
from src.apps.predictions.models import MarketPrediction
from src.core.ai import notification_humanization_runtime_enabled
from src.core.db.session import AsyncSessionLocal
from src.core.http.operation_store import OperationDispatchResult, OperationStore, dispatch_background_operation
from src.core.http.operations import OperationStatus
from src.core.settings import Settings, get_settings
from src.runtime.streams.types import IrisEvent


@dataclass(slots=True, frozen=True)
class ProjectionVersion:
    epoch: str
    sequence: int


class ProjectionClock:
    def __init__(self) -> None:
        self._epoch = f"{_utc_now().strftime('%Y%m%dT%H%M%SZ')}-{token_hex(4)}"
        self._sequence = 0

    def current(self) -> ProjectionVersion:
        return ProjectionVersion(epoch=self._epoch, sequence=self._sequence)

    def advance(self) -> ProjectionVersion:
        self._sequence += 1
        return ProjectionVersion(epoch=self._epoch, sequence=self._sequence)


@dataclass(slots=True, frozen=True)
class RuntimeSnapshot:
    entities: dict[str, HAEntityStateRead]
    collections: dict[str, Any]


@dataclass(slots=True, frozen=True)
class HACommandDispatch:
    command: str
    operation_id: str
    operation_type: str
    outbound_messages: tuple[dict[str, Any], ...] = ()


class HACommandDispatchError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.retryable = retryable


class HABridgeService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
        operation_store_factory: type[OperationStore] = OperationStore,
        projection_clock: ProjectionClock | None = None,
        control_state_store_factory: type[HAControlStateStore] = HAControlStateStore,
    ) -> None:
        self._settings = settings or get_settings()
        self._session_factory = session_factory
        self._operation_store_factory = operation_store_factory
        self._projection_clock = projection_clock or ProjectionClock()
        self._control_state_store = control_state_store_factory(settings=self._settings)
        self._runtime_lock = asyncio.Lock()
        self._projected_runtime: RuntimeSnapshot | None = None
        self._coin_symbol_cache: dict[int, str] = {}

    @property
    def projection_clock(self) -> ProjectionClock:
        return self._projection_clock

    def capabilities(self) -> HACapabilitiesRead:
        return HACapabilitiesRead(
            dashboard=True,
            commands=True,
            collections=True,
            promoted_entities=False,
        )

    def instance(self) -> HAInstanceRead:
        return HAInstanceRead(
            instance_id=self._settings.ha_instance_id,
            display_name=self._settings.ha_display_name,
            version=self._settings.app_version,
            protocol_version=self._settings.ha_protocol_version,
            catalog_version=self.catalog_version(),
            mode=self._settings.api_launch_mode,  # type: ignore[arg-type]
            minimum_ha_integration_version=self._settings.ha_minimum_integration_version,
            recommended_ha_integration_version=self._settings.ha_recommended_integration_version,
        )

    def health(self) -> HAHealthRead:
        return HAHealthRead(
            status="ok",
            instance_id=self._settings.ha_instance_id,
            version=self._settings.app_version,
            protocol_version=self._settings.ha_protocol_version,
            catalog_version=self.catalog_version(),
            mode=self._settings.api_launch_mode,  # type: ignore[arg-type]
            websocket_supported=True,
            dashboard_supported=True,
            commands_supported=True,
            collections_supported=True,
        )

    def bootstrap(self) -> HABootstrapRead:
        return HABootstrapRead(
            instance=self.instance(),
            capabilities=self.capabilities(),
            catalog_url=self._ha_api_path("/catalog"),
            dashboard_url=self._ha_api_path("/dashboard"),
            ws_url=self._ha_api_path("/ws"),
            state_url=self._ha_api_path("/state"),
        )

    def catalog(self) -> HACatalogRead:
        views = self.dashboard().views
        catalog = HACatalogRead(
            catalog_version="pending",
            protocol_version=self._settings.ha_protocol_version,
            mode=self._settings.api_launch_mode,  # type: ignore[arg-type]
            entities=self._catalog_entities(),
            collections=self._catalog_collections(),
            commands=self._catalog_commands(),
            views=views,
        )
        return catalog.model_copy(update={"catalog_version": self.catalog_version(catalog)})

    def dashboard(self) -> HADashboardRead:
        return HADashboardRead(
            version=1,
            slug="iris",
            title=self._settings.ha_display_name,
            views=[
                HADashboardViewRead(
                    view_key="overview",
                    title="Overview",
                    sections=[
                        HADashboardSectionRead(
                            section_key="system",
                            title="System",
                            widgets=[
                                HADashboardWidgetRead(
                                    widget_key="system_status",
                                    title="Connection",
                                    kind="status",
                                    source="system.connection",
                                    entity_keys=["system.connection", "system.mode"],
                                ),
                                HADashboardWidgetRead(
                                    widget_key="market_summary",
                                    title="Market Summary",
                                    kind="summary",
                                    source="market.summary",
                                    entity_keys=[
                                        "market.summary.active_assets_count",
                                        "market.summary.hot_assets_count",
                                    ],
                                ),
                            ],
                        ),
                        HADashboardSectionRead(
                            section_key="portfolio",
                            title="Portfolio",
                            widgets=[
                                HADashboardWidgetRead(
                                    widget_key="portfolio_summary",
                                    title="Portfolio",
                                    kind="summary",
                                    source="portfolio.snapshot",
                                    entity_keys=[
                                        "portfolio.summary.portfolio_value",
                                        "portfolio.summary.open_positions",
                                        "notifications.enabled",
                                    ],
                                ),
                                HADashboardWidgetRead(
                                    widget_key="portfolio_actions",
                                    title="Portfolio Actions",
                                    kind="actions",
                                    source="portfolio.actions",
                                    command_keys=["portfolio.sync"],
                                ),
                                HADashboardWidgetRead(
                                    widget_key="market_actions",
                                    title="Market Actions",
                                    kind="actions",
                                    source="market.actions",
                                    command_keys=["market.refresh"],
                                ),
                            ],
                        ),
                    ],
                ),
                HADashboardViewRead(
                    view_key="assets",
                    title="Assets",
                    sections=[
                        HADashboardSectionRead(
                            section_key="assets_snapshot",
                            title="Tracked Assets",
                            widgets=[
                                HADashboardWidgetRead(
                                    widget_key="assets_table",
                                    title="Assets Snapshot",
                                    kind="table",
                                    source="assets.snapshot",
                                    config={
                                        "columns": [
                                            "symbol",
                                            "market_regime",
                                            "decision",
                                            "activity_bucket",
                                            "pattern_state",
                                        ],
                                        "max_items": 8,
                                    },
                                ),
                                HADashboardWidgetRead(
                                    widget_key="market_activity",
                                    title="Market Activity",
                                    kind="summary",
                                    source="market.summary",
                                    entity_keys=[
                                        "market.summary.active_assets_count",
                                        "market.summary.hot_assets_count",
                                    ],
                                ),
                            ],
                        )
                    ],
                ),
                HADashboardViewRead(
                    view_key="signals",
                    title="Signals",
                    sections=[
                        HADashboardSectionRead(
                            section_key="signals_snapshot",
                            title="Signals",
                            widgets=[
                                HADashboardWidgetRead(
                                    widget_key="signals_table",
                                    title="Latest Signals",
                                    kind="table",
                                    source="assets.snapshot",
                                    config={
                                        "columns": [
                                            "symbol",
                                            "decision",
                                            "confidence",
                                            "market_regime",
                                            "pattern_state",
                                        ],
                                        "max_items": 8,
                                    },
                                ),
                            ],
                        )
                    ],
                ),
                HADashboardViewRead(
                    view_key="predictions",
                    title="Predictions",
                    sections=[
                        HADashboardSectionRead(
                            section_key="predictions_snapshot",
                            title="Predictions",
                            widgets=[
                                HADashboardWidgetRead(
                                    widget_key="predictions_table",
                                    title="Prediction Journal",
                                    kind="table",
                                    source="predictions.snapshot",
                                    config={
                                        "columns": [
                                            "symbol",
                                            "prediction_event",
                                            "expected_move",
                                            "status",
                                            "confidence",
                                        ],
                                        "max_items": 8,
                                    },
                                ),
                            ],
                        )
                    ],
                ),
                HADashboardViewRead(
                    view_key="portfolio",
                    title="Portfolio",
                    sections=[
                        HADashboardSectionRead(
                            section_key="portfolio_summary",
                            title="Portfolio Summary",
                            widgets=[
                                HADashboardWidgetRead(
                                    widget_key="portfolio_summary_detail",
                                    title="Portfolio Totals",
                                    kind="summary",
                                    source="portfolio.snapshot",
                                    entity_keys=[
                                        "portfolio.summary.portfolio_value",
                                        "portfolio.summary.open_positions",
                                    ],
                                ),
                                HADashboardWidgetRead(
                                    widget_key="portfolio_positions",
                                    title="Open Positions",
                                    kind="list",
                                    source="portfolio.snapshot",
                                    config={
                                        "path": "positions",
                                        "fields": [
                                            "symbol",
                                            "position_value",
                                            "status",
                                            "timeframe",
                                        ],
                                        "max_items": 6,
                                    },
                                ),
                                HADashboardWidgetRead(
                                    widget_key="portfolio_actions_full",
                                    title="Portfolio Actions",
                                    kind="actions",
                                    source="portfolio.actions",
                                    command_keys=["portfolio.sync"],
                                ),
                            ],
                        )
                    ],
                ),
                HADashboardViewRead(
                    view_key="integrations",
                    title="Integrations",
                    sections=[
                        HADashboardSectionRead(
                            section_key="notifications",
                            title="Notifications",
                            widgets=[
                                HADashboardWidgetRead(
                                    widget_key="notifications_status",
                                    title="Notifications",
                                    kind="summary",
                                    source="integrations.snapshot",
                                    entity_keys=[
                                        "notifications.enabled",
                                        "settings.notifications_enabled",
                                        "settings.default_timeframe",
                                    ],
                                ),
                                HADashboardWidgetRead(
                                    widget_key="integrations_snapshot",
                                    title="Integrations Snapshot",
                                    kind="list",
                                    source="integrations.snapshot",
                                    config={
                                        "fields": [
                                            "enabled",
                                            "last_notification_at",
                                            "auth_status",
                                        ],
                                        "max_items": 4,
                                    },
                                ),
                            ],
                        )
                    ],
                ),
                HADashboardViewRead(
                    view_key="system",
                    title="System",
                    sections=[
                        HADashboardSectionRead(
                            section_key="system_runtime",
                            title="Runtime",
                            widgets=[
                                HADashboardWidgetRead(
                                    widget_key="system_runtime_status",
                                    title="Runtime Status",
                                    kind="status",
                                    source="system.connection",
                                    entity_keys=[
                                        "system.connection",
                                        "system.mode",
                                        "notifications.enabled",
                                    ],
                                ),
                                HADashboardWidgetRead(
                                    widget_key="system_controls",
                                    title="System Controls",
                                    kind="actions",
                                    source="system.actions",
                                    command_keys=[
                                        "portfolio.sync",
                                        "market.refresh",
                                    ],
                                ),
                            ],
                        )
                    ],
                ),
            ],
        )

    async def state_snapshot(self) -> HAStateSnapshotRead:
        runtime = await self.projected_runtime_snapshot()
        version = self._projection_clock.current()
        return HAStateSnapshotRead(
            projection_epoch=version.epoch,
            sequence=version.sequence,
            entities=runtime.entities,
            collections=runtime.collections,
        )

    async def operation_status(self, operation_id: str) -> HAOperationRead | None:
        store = self._operation_store_factory()
        status = await store.get_status(operation_id)
        if status is None:
            return None
        result = await store.get_result(operation_id)
        error = None
        if status.error_code is not None and status.error_message is not None:
            from src.apps.integrations.ha.schemas import HAErrorRead

            error = HAErrorRead(code=status.error_code, message=status.error_message)
        return HAOperationRead(
            operation_id=operation_id,
            status=_operation_status(status.status),
            result=result.result if result is not None else None,
            error=error,
        )

    async def entity_state_messages(self, entity_keys: list[str]) -> list[dict[str, Any]]:
        runtime = await self.projected_runtime_snapshot()
        keys = set(entity_keys)
        if "*" in keys:
            keys = set(runtime.entities)
        messages: list[dict[str, Any]] = []
        timestamp = _utc_now()
        for entity_key in sorted(keys):
            state = runtime.entities.get(entity_key)
            if state is None:
                continue
            version = self._projection_clock.advance()
            messages.append(
                HAEntityStateChangedMessage(
                    projection_epoch=version.epoch,
                    sequence=version.sequence,
                    entity_key=entity_key,
                    state=state.state,
                    attributes=state.attributes,
                    timestamp=timestamp,
                ).model_dump(mode="json")
            )
        return messages

    async def collection_snapshot_messages(self, collection_keys: list[str]) -> list[dict[str, Any]]:
        runtime = await self.projected_runtime_snapshot()
        messages: list[dict[str, Any]] = []
        timestamp = _utc_now()
        for collection_key in sorted(set(collection_keys)):
            data = runtime.collections.get(collection_key)
            if data is None:
                continue
            version = self._projection_clock.advance()
            messages.append(
                HACollectionSnapshotMessage(
                    projection_epoch=version.epoch,
                    sequence=version.sequence,
                    collection_key=collection_key,
                    data=data,
                    timestamp=timestamp,
                ).model_dump(mode="json")
            )
        return messages

    async def projected_runtime_snapshot(self) -> RuntimeSnapshot:
        async with self._runtime_lock:
            runtime = await self._ensure_projected_runtime_locked()
            return _clone_runtime(runtime)

    async def apply_event(self, event: IrisEvent) -> list[dict[str, Any]]:
        async with self._runtime_lock:
            runtime = await self._ensure_projected_runtime_locked()
            messages: list[dict[str, Any]] = [self._event_emitted_message(event)]
            if event.event_type in _ASSET_EVENT_TYPES:
                messages.extend(await self._apply_asset_event_locked(runtime, event))
            elif event.event_type in {"prediction_confirmed", "prediction_failed"}:
                messages.extend(await self._apply_prediction_event_locked(runtime, event))
            elif event.event_type in _PORTFOLIO_EVENT_TYPES:
                messages.extend(await self._apply_portfolio_event_locked(runtime))
            return messages

    def system_health_message(self) -> dict[str, Any]:
        from src.apps.integrations.ha.schemas import HASystemHealthMessage

        version = self._projection_clock.advance()
        return HASystemHealthMessage(
            projection_epoch=version.epoch,
            sequence=version.sequence,
            status="ok",
            bridge="ready",
            timestamp=_utc_now(),
        ).model_dump(mode="json")

    async def execute_command(self, *, command: str, payload: dict[str, Any]) -> HACommandDispatch:
        handlers = {
            "portfolio.sync": self._dispatch_portfolio_sync,
            "market.refresh": self._dispatch_market_refresh,
            "settings.notifications_enabled.set": self._dispatch_notifications_enabled_set,
            "settings.default_timeframe.set": self._dispatch_default_timeframe_set,
        }
        handler = handlers.get(command)
        if handler is None:
            raise HACommandDispatchError(
                code="command_not_available",
                message="Command is not available for the current HA bridge stage.",
                details={"command": command, "mode": self._settings.api_launch_mode},
                retryable=False,
            )
        return await handler(payload)

    def command_accepted_ack(self, *, request_id: str, operation_id: str) -> dict[str, Any]:
        from src.apps.integrations.ha.schemas import HACommandAckMessage

        return HACommandAckMessage(
            request_id=request_id,
            accepted=True,
            operation_id=operation_id,
        ).model_dump(mode="json")

    def command_error_ack(
        self,
        *,
        request_id: str,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> dict[str, Any]:
        from src.apps.integrations.ha.schemas import HACommandAckMessage, HAErrorRead

        return HACommandAckMessage(
            request_id=request_id,
            accepted=False,
            error=HAErrorRead(
                code=code,
                message=message,
                details=details,
            ),
            retryable=retryable,
        ).model_dump(mode="json")

    def command_not_available_ack(self, *, request_id: str, command: str) -> dict[str, Any]:
        return self.command_error_ack(
            request_id=request_id,
            code="command_not_available",
            message="Command execution is not enabled for the current HA bridge stage.",
            details={"command": command, "mode": self._settings.api_launch_mode},
            retryable=False,
        )

    async def operation_update_message(
        self,
        *,
        operation_id: str,
        command: str | None = None,
    ) -> dict[str, Any] | None:
        store = self._operation_store_factory()
        status = await store.get_status(operation_id)
        if status is None:
            return None
        result = await store.get_result(operation_id)
        events = await store.list_events(operation_id)
        last_event = events[-1] if events else None
        error = None
        if status.error_code is not None and status.error_message is not None:
            from src.apps.integrations.ha.schemas import HAErrorRead

            error = HAErrorRead(code=status.error_code, message=status.error_message)
        version = self._projection_clock.advance()
        timestamp = (
            last_event.recorded_at
            if last_event is not None
            else status.finished_at or status.started_at or status.accepted_at
        )
        return HAOperationUpdateMessage(
            projection_epoch=version.epoch,
            sequence=version.sequence,
            operation_id=operation_id,
            status=_operation_status(status.status),
            command=command,
            operation_type=status.operation_type,
            message=last_event.message if last_event is not None else None,
            result=result.result if result is not None else None,
            error=error,
            timestamp=timestamp,
        ).model_dump(mode="json")

    def resync_required_message(self, *, reason: str, message: str | None = None) -> dict[str, Any]:
        return HAResyncRequiredMessage(
            reason=reason,
            state_url=self._ha_api_path("/state"),
            message=message,
        ).model_dump(mode="json")

    def catalog_version(self, catalog: HACatalogRead | None = None) -> str:
        payload = (catalog or self.catalog()).model_dump(mode="json", exclude={"catalog_version"})
        digest = hashlib.sha1(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return f"sha1:{digest[:12]}"

    def _catalog_entities(self) -> list[HAEntityDefinitionRead]:
        availability = HAAvailabilityRead(modes=["full", "local", "ha_addon"])
        since_version = self._settings.app_version
        return [
            HAEntityDefinitionRead(
                entity_key="system.connection",
                platform="binary_sensor",
                name="IRIS Connection",
                state_source="system.connection",
                icon="mdi:lan-connect",
                category="diagnostic",
                availability=availability,
                since_version=since_version,
                device_class="connectivity",
            ),
            HAEntityDefinitionRead(
                entity_key="system.mode",
                platform="sensor",
                name="IRIS Mode",
                state_source="system.mode",
                icon="mdi:server-network",
                category="diagnostic",
                availability=availability,
                since_version=since_version,
            ),
            HAEntityDefinitionRead(
                entity_key="market.summary.active_assets_count",
                platform="sensor",
                name="Active Assets",
                state_source="market.summary.active_assets_count",
                icon="mdi:chart-bubble",
                availability=availability,
                since_version=since_version,
                unit_of_measurement="assets",
            ),
            HAEntityDefinitionRead(
                entity_key="market.summary.hot_assets_count",
                platform="sensor",
                name="Hot Assets",
                state_source="market.summary.hot_assets_count",
                icon="mdi:fire",
                availability=availability,
                since_version=since_version,
                unit_of_measurement="assets",
            ),
            HAEntityDefinitionRead(
                entity_key="portfolio.summary.portfolio_value",
                platform="sensor",
                name="Portfolio Value",
                state_source="portfolio.summary.portfolio_value",
                icon="mdi:wallet",
                availability=availability,
                since_version=since_version,
                unit_of_measurement="USD",
            ),
            HAEntityDefinitionRead(
                entity_key="portfolio.summary.open_positions",
                platform="sensor",
                name="Open Positions",
                state_source="portfolio.summary.open_positions",
                icon="mdi:briefcase-outline",
                availability=availability,
                since_version=since_version,
                unit_of_measurement="positions",
            ),
            HAEntityDefinitionRead(
                entity_key="notifications.enabled",
                platform="binary_sensor",
                name="Notifications Enabled",
                state_source="notifications.enabled",
                icon="mdi:bell-ring-outline",
                availability=availability,
                since_version=since_version,
            ),
            HAEntityDefinitionRead(
                entity_key="settings.notifications_enabled",
                platform="switch",
                name="Notifications Enabled",
                state_source="settings.notifications_enabled",
                command_key="settings.notifications_enabled.set",
                icon="mdi:bell-ring-outline",
                category="config",
                availability=availability,
                since_version=since_version,
            ),
            HAEntityDefinitionRead(
                entity_key="settings.default_timeframe",
                platform="select",
                name="Default Timeframe",
                state_source="settings.default_timeframe",
                command_key="settings.default_timeframe.set",
                icon="mdi:timeline-clock-outline",
                category="config",
                availability=availability,
                since_version=since_version,
            ),
            HAEntityDefinitionRead(
                entity_key="actions.portfolio_sync",
                platform="button",
                name="Portfolio Sync",
                state_source="actions.portfolio_sync",
                command_key="portfolio.sync",
                icon="mdi:sync",
                category="config",
                availability=availability,
                since_version=since_version,
            ),
            HAEntityDefinitionRead(
                entity_key="actions.market_refresh",
                platform="button",
                name="Market Refresh",
                state_source="actions.market_refresh",
                command_key="market.refresh",
                icon="mdi:refresh-circle",
                category="config",
                availability=availability,
                since_version=since_version,
            ),
        ]

    def _catalog_collections(self) -> list[HACollectionDefinitionRead]:
        since_version = self._settings.app_version
        return [
            HACollectionDefinitionRead(
                collection_key="assets.snapshot",
                kind="mapping",
                transport="websocket",
                dashboard_only=True,
                since_version=since_version,
            ),
            HACollectionDefinitionRead(
                collection_key="portfolio.snapshot",
                kind="summary",
                transport="websocket",
                dashboard_only=False,
                since_version=since_version,
            ),
            HACollectionDefinitionRead(
                collection_key="predictions.snapshot",
                kind="mapping",
                transport="websocket",
                dashboard_only=True,
                since_version=since_version,
            ),
            HACollectionDefinitionRead(
                collection_key="integrations.snapshot",
                kind="mapping",
                transport="websocket",
                dashboard_only=True,
                since_version=since_version,
            ),
        ]

    def _catalog_commands(self) -> list[HACommandDefinitionRead]:
        availability = HAAvailabilityRead(modes=["full", "local", "ha_addon"])
        since_version = self._settings.app_version
        return [
            HACommandDefinitionRead(
                command_key="portfolio.sync",
                name="Portfolio Sync",
                kind="refresh",
                returns="operation",
                availability=availability,
                since_version=since_version,
            ),
            HACommandDefinitionRead(
                command_key="market.refresh",
                name="Market Refresh",
                kind="refresh",
                returns="operation",
                availability=availability,
                since_version=since_version,
            ),
            HACommandDefinitionRead(
                command_key="settings.notifications_enabled.set",
                name="Set Notifications Enabled",
                kind="toggle",
                input_schema={
                    "type": "object",
                    "properties": {"value": {"type": "boolean"}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
                returns="operation",
                availability=availability,
                since_version=since_version,
            ),
            HACommandDefinitionRead(
                command_key="settings.default_timeframe.set",
                name="Set Default Timeframe",
                kind="selection",
                input_schema={
                    "type": "object",
                    "properties": {
                        "value": {"type": "string", "enum": list(HA_TIMEFRAME_OPTIONS)},
                    },
                    "required": ["value"],
                    "additionalProperties": False,
                },
                returns="operation",
                availability=availability,
                since_version=since_version,
            ),
        ]

    async def _dispatch_portfolio_sync(self, payload: dict[str, Any]) -> HACommandDispatch:
        self._ensure_empty_payload(command="portfolio.sync", payload=payload)
        from src.apps.portfolio.tasks import portfolio_sync_job

        dispatch_result = await dispatch_background_operation(
            store=self._operation_store_factory(),
            operation_type="portfolio.sync",
            deduplication_key="singleton",
            dispatch=lambda operation_id: portfolio_sync_job.kiq(operation_id=operation_id),
        )
        return self._command_dispatch_result(command="portfolio.sync", dispatch_result=dispatch_result)

    async def _dispatch_market_refresh(self, payload: dict[str, Any]) -> HACommandDispatch:
        self._ensure_empty_payload(command="market.refresh", payload=payload)
        from src.apps.market_structure.tasks import refresh_market_structure_source_health_job

        dispatch_result = await dispatch_background_operation(
            store=self._operation_store_factory(),
            operation_type="market.refresh",
            deduplication_key="singleton",
            dispatch=lambda operation_id: refresh_market_structure_source_health_job.kiq(operation_id=operation_id),
        )
        return self._command_dispatch_result(command="market.refresh", dispatch_result=dispatch_result)

    async def _dispatch_notifications_enabled_set(self, payload: dict[str, Any]) -> HACommandDispatch:
        enabled = self._require_bool_payload(command="settings.notifications_enabled.set", payload=payload)

        async def _action(runtime: RuntimeSnapshot) -> tuple[list[dict[str, Any]], dict[str, Any]]:
            await self._control_state_store.set_notifications_enabled(enabled)
            messages = self._apply_notifications_enabled_locked(runtime, enabled=enabled)
            return messages, {
                "entity_key": "settings.notifications_enabled",
                "state": enabled,
            }

        return await self._dispatch_inline_operation(
            command="settings.notifications_enabled.set",
            operation_type="settings.notifications_enabled.set",
            action=_action,
        )

    async def _dispatch_default_timeframe_set(self, payload: dict[str, Any]) -> HACommandDispatch:
        timeframe = self._require_timeframe_payload(command="settings.default_timeframe.set", payload=payload)

        async def _action(runtime: RuntimeSnapshot) -> tuple[list[dict[str, Any]], dict[str, Any]]:
            selected = await self._control_state_store.set_default_timeframe(timeframe)
            messages = self._apply_default_timeframe_locked(runtime, timeframe=selected)
            return messages, {
                "entity_key": "settings.default_timeframe",
                "state": selected,
            }

        return await self._dispatch_inline_operation(
            command="settings.default_timeframe.set",
            operation_type="settings.default_timeframe.set",
            action=_action,
        )

    @staticmethod
    def _command_dispatch_result(*, command: str, dispatch_result: OperationDispatchResult) -> HACommandDispatch:
        operation = dispatch_result.operation
        return HACommandDispatch(
            command=command,
            operation_id=operation.operation_id,
            operation_type=operation.operation_type,
        )

    async def _dispatch_inline_operation(
        self,
        *,
        command: str,
        operation_type: str,
        action,
    ) -> HACommandDispatch:
        store = self._operation_store_factory()
        operation = await store.create_operation(operation_type=operation_type)
        await store.mark_running(operation.operation_id, message=f"Executing {command}.")
        async with self._runtime_lock:
            runtime = await self._ensure_projected_runtime_locked()
            try:
                outbound_messages, result = await action(runtime)
            except Exception as exc:
                await store.mark_failed(
                    operation.operation_id,
                    error_code="command_execution_failed",
                    error_message=str(exc),
                    retryable=False,
                )
                raise
        await store.mark_succeeded(
            operation.operation_id,
            message=f"Completed {command}.",
            result=result,
        )
        return HACommandDispatch(
            command=command,
            operation_id=operation.operation_id,
            operation_type=operation_type,
            outbound_messages=tuple(outbound_messages),
        )

    @staticmethod
    def _ensure_empty_payload(*, command: str, payload: dict[str, Any]) -> None:
        if payload:
            raise HACommandDispatchError(
                code="invalid_payload",
                message="This command does not accept payload fields.",
                details={"command": command, "payload_keys": sorted(payload)},
                retryable=False,
            )

    @staticmethod
    def _require_bool_payload(*, command: str, payload: dict[str, Any]) -> bool:
        if set(payload) != {"value"} or not isinstance(payload.get("value"), bool):
            raise HACommandDispatchError(
                code="invalid_payload",
                message="Command payload must be an object with a boolean 'value'.",
                details={"command": command, "payload": payload},
                retryable=False,
            )
        return bool(payload["value"])

    @staticmethod
    def _require_timeframe_payload(*, command: str, payload: dict[str, Any]) -> str:
        value = payload.get("value")
        if set(payload) != {"value"} or not isinstance(value, str) or value not in HA_TIMEFRAME_OPTIONS:
            raise HACommandDispatchError(
                code="invalid_payload",
                message="Command payload must contain a supported timeframe value.",
                details={
                    "command": command,
                    "payload": payload,
                    "allowed_values": list(HA_TIMEFRAME_OPTIONS),
                },
                retryable=False,
            )
        return value

    async def _runtime_snapshot(self) -> RuntimeSnapshot:
        async with self._session_factory() as session:
            portfolio_state = await PortfolioQueryService(session).get_state()
            notifications = await NotificationQueryService(session).list_notifications(limit=1)
            assets_snapshot = await self._assets_snapshot(session)
            portfolio_snapshot = await self._portfolio_collection_snapshot(session)
            predictions_snapshot = await self._predictions_snapshot(session)

        notifications_enabled = await self._control_state_store.get_notifications_enabled(
            default=notification_humanization_runtime_enabled(self._settings)
        )
        default_timeframe = await self._control_state_store.get_default_timeframe(default=HA_TIMEFRAME_OPTIONS[0])
        portfolio_value = float(portfolio_state.total_capital)
        entities = {
            "system.connection": HAEntityStateRead(
                state=True,
                attributes={
                    "instance_id": self._settings.ha_instance_id,
                    "catalog_version": self.catalog_version(),
                    "protocol_version": self._settings.ha_protocol_version,
                },
            ),
            "system.mode": HAEntityStateRead(state=self._settings.api_launch_mode, attributes={}),
            "market.summary.active_assets_count": HAEntityStateRead(
                state=len(assets_snapshot),
                attributes={},
            ),
            "market.summary.hot_assets_count": HAEntityStateRead(
                state=sum(1 for item in assets_snapshot.values() if item.get("activity_bucket") == "HOT"),
                attributes={},
            ),
            "portfolio.summary.portfolio_value": HAEntityStateRead(
                state=portfolio_value,
                attributes={"available_capital": float(portfolio_state.available_capital)},
            ),
            "portfolio.summary.open_positions": HAEntityStateRead(
                state=int(portfolio_state.open_positions),
                attributes={"max_positions": int(portfolio_state.max_positions)},
            ),
            "notifications.enabled": HAEntityStateRead(
                state=notifications_enabled,
                attributes={"recent_notifications": len(notifications)},
            ),
            "settings.notifications_enabled": HAEntityStateRead(
                state=notifications_enabled,
                attributes={"command_key": "settings.notifications_enabled.set"},
            ),
            "settings.default_timeframe": HAEntityStateRead(
                state=default_timeframe,
                attributes={
                    "command_key": "settings.default_timeframe.set",
                    "options": list(HA_TIMEFRAME_OPTIONS),
                },
            ),
            "actions.portfolio_sync": HAEntityStateRead(
                state="available",
                attributes={"command_key": "portfolio.sync"},
            ),
            "actions.market_refresh": HAEntityStateRead(
                state="available",
                attributes={"command_key": "market.refresh"},
            ),
        }
        collections = {
            "assets.snapshot": assets_snapshot,
            "portfolio.snapshot": portfolio_snapshot,
            "predictions.snapshot": predictions_snapshot,
            "integrations.snapshot": {
                "notifications": {
                    "enabled": notifications_enabled,
                    "last_notification_at": notifications[0].created_at if notifications else None,
                },
                "telegram": {"auth_status": "unknown"},
            },
        }
        return RuntimeSnapshot(entities=entities, collections=collections)

    async def _ensure_projected_runtime_locked(self) -> RuntimeSnapshot:
        if self._projected_runtime is None:
            self._projected_runtime = await self._runtime_snapshot()
        return self._projected_runtime

    async def _assets_snapshot(self, session: AsyncSession) -> dict[str, dict[str, Any]]:
        rows = (
            await session.execute(
                select(
                    Coin.symbol,
                    Coin.name,
                    CoinMetrics.price_current,
                    CoinMetrics.activity_bucket,
                    CoinMetrics.activity_score,
                    CoinMetrics.market_regime,
                    CoinMetrics.updated_at,
                )
                .outerjoin(CoinMetrics, CoinMetrics.coin_id == Coin.id)
                .where(Coin.deleted_at.is_(None), Coin.enabled.is_(True))
                .order_by(CoinMetrics.activity_score.desc().nullslast(), Coin.symbol.asc())
                .limit(25)
            )
        ).all()
        return {
            str(row.symbol): {
                "name": str(row.name),
                "price_current": float(row.price_current) if row.price_current is not None else None,
                "activity_bucket": str(row.activity_bucket) if row.activity_bucket is not None else None,
                "activity_score": float(row.activity_score) if row.activity_score is not None else None,
                "market_regime": str(row.market_regime) if row.market_regime is not None else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at is not None else None,
            }
            for row in rows
        }

    async def _positions_snapshot(self, session: AsyncSession) -> list[dict[str, Any]]:
        rows = (
            await session.execute(
                select(
                    Coin.symbol,
                    PortfolioPosition.position_value,
                    PortfolioPosition.position_size,
                    PortfolioPosition.status,
                    PortfolioPosition.timeframe,
                    PortfolioPosition.source_exchange,
                    PortfolioPosition.opened_at,
                )
                .join(Coin, Coin.id == PortfolioPosition.coin_id)
                .where(PortfolioPosition.status.in_(("open", "partial")))
                .order_by(PortfolioPosition.position_value.desc(), PortfolioPosition.id.desc())
                .limit(25)
            )
        ).all()
        return [
            {
                "symbol": str(row.symbol),
                "position_value": float(row.position_value),
                "position_size": float(row.position_size),
                "status": str(row.status),
                "timeframe": int(row.timeframe),
                "source_exchange": str(row.source_exchange) if row.source_exchange is not None else None,
                "opened_at": row.opened_at.isoformat(),
            }
            for row in rows
        ]

    async def _portfolio_collection_snapshot(self, session: AsyncSession) -> dict[str, Any]:
        portfolio_state = await PortfolioQueryService(session).get_state()
        return {
            "summary": {
                "portfolio_value": float(portfolio_state.total_capital),
                "available_capital": float(portfolio_state.available_capital),
                "allocated_capital": float(portfolio_state.allocated_capital),
                "open_positions": int(portfolio_state.open_positions),
                "max_positions": int(portfolio_state.max_positions),
            },
            "positions": await self._positions_snapshot(session),
        }

    async def _predictions_snapshot(self, session: AsyncSession) -> dict[str, dict[str, Any]]:
        rows = (
            await session.execute(
                select(
                    MarketPrediction.id,
                    MarketPrediction.target_coin_id,
                    MarketPrediction.leader_coin_id,
                    MarketPrediction.prediction_event,
                    MarketPrediction.expected_move,
                    MarketPrediction.confidence,
                    MarketPrediction.status,
                    MarketPrediction.created_at,
                    MarketPrediction.evaluation_time,
                )
                .order_by(MarketPrediction.created_at.desc(), MarketPrediction.id.desc())
                .limit(25)
            )
        ).all()
        snapshot: dict[str, dict[str, Any]] = {}
        for row in rows:
            symbol = await self._resolve_symbol(int(row.target_coin_id), session=session)
            snapshot[str(row.id)] = {
                "prediction_id": int(row.id),
                "symbol": symbol,
                "leader_coin_id": int(row.leader_coin_id),
                "target_coin_id": int(row.target_coin_id),
                "prediction_event": str(row.prediction_event),
                "expected_move": str(row.expected_move),
                "confidence": float(row.confidence),
                "status": str(row.status),
                "created_at": row.created_at.isoformat(),
                "evaluation_time": row.evaluation_time.isoformat(),
            }
        return snapshot

    async def _resolve_symbol(self, coin_id: int, *, session: AsyncSession | None = None) -> str | None:
        cached = self._coin_symbol_cache.get(int(coin_id))
        if cached is not None:
            return cached
        should_close = session is None
        active_session = session
        if active_session is None:
            active_session = self._session_factory()
        try:
            row = await active_session.scalar(select(Coin.symbol).where(Coin.id == int(coin_id)).limit(1))
            if row is None:
                return None
            symbol = str(row)
            self._coin_symbol_cache[int(coin_id)] = symbol
            return symbol
        finally:
            if should_close and active_session is not None:
                await active_session.close()

    async def _apply_asset_event_locked(self, runtime: RuntimeSnapshot, event: IrisEvent) -> list[dict[str, Any]]:
        symbol = event.symbol or await self._resolve_symbol(int(event.coin_id))
        if symbol is None:
            return []
        assets_snapshot = runtime.collections.setdefault("assets.snapshot", {})
        assets = assets_snapshot if isinstance(assets_snapshot, dict) else {}
        existed = symbol in assets
        current = dict(assets.get(symbol, {"symbol": symbol}))
        if event.event_type == "decision_generated":
            current["decision"] = str(event.payload.get("decision") or current.get("decision") or "")
            if event.payload.get("score") is not None:
                current["score"] = float(event.payload["score"])
            if event.payload.get("confidence") is not None:
                current["confidence"] = float(event.payload["confidence"])
            current["decision_timestamp"] = event.occurred_at.isoformat()
        if event.event_type == "market_regime_changed":
            current["market_regime"] = str(event.payload.get("regime") or current.get("market_regime") or "")
            if event.payload.get("confidence") is not None:
                current["regime_confidence"] = float(event.payload["confidence"])
            current["regime_timestamp"] = event.occurred_at.isoformat()
        if event.event_type == "indicator_updated":
            for field in (
                "activity_bucket",
                "analysis_priority",
                "market_regime",
                "feature_source",
            ):
                if event.payload.get(field) is not None:
                    current[field] = str(event.payload[field])
            for field in (
                "activity_score",
                "regime_confidence",
                "price_change_24h",
                "price_change_7d",
                "volatility",
            ):
                if event.payload.get(field) is not None:
                    current[field] = float(event.payload[field])
            current["updated_at"] = event.occurred_at.isoformat()
        if event.event_type in _PATTERN_EVENT_TYPES:
            current["pattern_state"] = event.event_type.removeprefix("pattern_")
            if event.payload.get("pattern_slug") is not None:
                current["pattern_slug"] = str(event.payload["pattern_slug"])
            if event.payload.get("market_regime") is not None:
                current["pattern_market_regime"] = str(event.payload["market_regime"])
            for field in ("confidence", "factor", "success_rate"):
                if event.payload.get(field) is not None:
                    current[f"pattern_{field}"] = float(event.payload[field])
            if event.payload.get("total_signals") is not None:
                current["pattern_total_signals"] = int(event.payload["total_signals"])
            current["pattern_timestamp"] = event.occurred_at.isoformat()
        current.setdefault("symbol", symbol)
        assets[symbol] = current
        runtime.collections["assets.snapshot"] = assets

        messages = [
            self._collection_patch_message(
                collection_key="assets.snapshot",
                path=symbol,
                value=current,
            )
        ]
        if not existed:
            old_count = int(runtime.entities["market.summary.active_assets_count"].state)
            next_count = len(assets)
            if next_count != old_count:
                runtime.entities["market.summary.active_assets_count"] = HAEntityStateRead(state=next_count, attributes={})
                messages.extend(
                    self._state_and_entity_messages(
                        path="market.summary.active_assets_count",
                        entity_key="market.summary.active_assets_count",
                        value=next_count,
                        attributes={},
                    )
                )
        return messages

    async def _apply_prediction_event_locked(self, runtime: RuntimeSnapshot, event: IrisEvent) -> list[dict[str, Any]]:
        prediction_id = str(event.payload.get("prediction_id") or event.event_id)
        target_coin_id = int(event.payload.get("target_coin_id") or event.coin_id)
        symbol = await self._resolve_symbol(target_coin_id)
        predictions_snapshot = runtime.collections.setdefault("predictions.snapshot", {})
        predictions = predictions_snapshot if isinstance(predictions_snapshot, dict) else {}
        item = {
            "prediction_id": int(event.payload.get("prediction_id") or 0),
            "symbol": symbol,
            "leader_coin_id": int(event.payload.get("leader_coin_id") or 0),
            "target_coin_id": target_coin_id,
            "prediction_event": str(event.payload.get("prediction_event") or ""),
            "expected_move": str(event.payload.get("expected_move") or ""),
            "actual_move": event.payload.get("actual_move"),
            "profit": event.payload.get("profit"),
            "status": str(event.payload.get("status") or event.event_type.removeprefix("prediction_")),
            "relation_confidence": event.payload.get("relation_confidence"),
            "updated_at": event.occurred_at.isoformat(),
        }
        predictions[prediction_id] = item
        runtime.collections["predictions.snapshot"] = predictions
        return [
            self._collection_patch_message(
                collection_key="predictions.snapshot",
                path=prediction_id,
                value=item,
            )
        ]

    async def _apply_portfolio_event_locked(self, runtime: RuntimeSnapshot) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            refreshed = await self._portfolio_collection_snapshot(session)
        old_snapshot = copy.deepcopy(runtime.collections.get("portfolio.snapshot", {}))
        runtime.collections["portfolio.snapshot"] = refreshed

        messages = [self._collection_snapshot_message("portfolio.snapshot", refreshed)]
        old_summary = dict(old_snapshot.get("summary", {})) if isinstance(old_snapshot, dict) else {}
        new_summary = dict(refreshed.get("summary", {}))

        messages.extend(
            self._sync_summary_path(
                runtime,
                entity_key="portfolio.summary.portfolio_value",
                path="portfolio.summary.portfolio_value",
                next_state=float(new_summary.get("portfolio_value", 0.0)),
                attributes={"available_capital": float(new_summary.get("available_capital", 0.0))},
            )
        )
        messages.extend(
            self._sync_summary_path(
                runtime,
                entity_key="portfolio.summary.open_positions",
                path="portfolio.summary.open_positions",
                next_state=int(new_summary.get("open_positions", 0)),
                attributes={"max_positions": int(new_summary.get("max_positions", 0))},
            )
        )
        if old_summary.get("available_capital") != new_summary.get("available_capital"):
            messages.append(
                self._state_patch_message(
                    path="portfolio.summary.available_capital",
                    value=float(new_summary.get("available_capital", 0.0)),
                )
            )
        if old_summary.get("allocated_capital") != new_summary.get("allocated_capital"):
            messages.append(
                self._state_patch_message(
                    path="portfolio.summary.allocated_capital",
                    value=float(new_summary.get("allocated_capital", 0.0)),
                )
            )
        return messages

    def _apply_notifications_enabled_locked(self, runtime: RuntimeSnapshot, *, enabled: bool) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        runtime.entities["notifications.enabled"] = HAEntityStateRead(
            state=enabled,
            attributes=runtime.entities.get("notifications.enabled", HAEntityStateRead(state=enabled)).attributes,
        )
        messages.extend(
            self._state_and_entity_messages(
                path="notifications.enabled",
                entity_key="notifications.enabled",
                value=enabled,
                attributes=runtime.entities["notifications.enabled"].attributes,
            )
        )
        runtime.entities["settings.notifications_enabled"] = HAEntityStateRead(
            state=enabled,
            attributes={"command_key": "settings.notifications_enabled.set"},
        )
        messages.extend(
            self._state_and_entity_messages(
                path="settings.notifications_enabled",
                entity_key="settings.notifications_enabled",
                value=enabled,
                attributes=runtime.entities["settings.notifications_enabled"].attributes,
            )
        )
        integrations_snapshot = runtime.collections.get("integrations.snapshot")
        if isinstance(integrations_snapshot, dict):
            notifications_snapshot = dict(integrations_snapshot.get("notifications", {}))
            notifications_snapshot["enabled"] = enabled
            integrations_snapshot["notifications"] = notifications_snapshot
            messages.append(
                self._collection_patch_message(
                    collection_key="integrations.snapshot",
                    path="notifications",
                    value=notifications_snapshot,
                )
            )
        return messages

    def _apply_default_timeframe_locked(self, runtime: RuntimeSnapshot, *, timeframe: str) -> list[dict[str, Any]]:
        attributes = {
            "command_key": "settings.default_timeframe.set",
            "options": list(HA_TIMEFRAME_OPTIONS),
        }
        runtime.entities["settings.default_timeframe"] = HAEntityStateRead(
            state=timeframe,
            attributes=attributes,
        )
        return self._state_and_entity_messages(
            path="settings.default_timeframe",
            entity_key="settings.default_timeframe",
            value=timeframe,
            attributes=attributes,
        )

    def _sync_summary_path(
        self,
        runtime: RuntimeSnapshot,
        *,
        entity_key: str,
        path: str,
        next_state: Any,
        attributes: dict[str, Any],
    ) -> list[dict[str, Any]]:
        current = runtime.entities[entity_key]
        if current.state == next_state and current.attributes == attributes:
            return []
        runtime.entities[entity_key] = HAEntityStateRead(state=next_state, attributes=attributes)
        return self._state_and_entity_messages(
            path=path,
            entity_key=entity_key,
            value=next_state,
            attributes=attributes,
        )

    def _state_and_entity_messages(
        self,
        *,
        path: str,
        entity_key: str,
        value: Any,
        attributes: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            self._state_patch_message(path=path, value=value),
            self._entity_state_changed_message(entity_key=entity_key, state=value, attributes=attributes),
        ]

    def _event_emitted_message(self, event: IrisEvent) -> dict[str, Any]:
        return HAEventEmittedMessage(
            event_type=event.event_type,
            event_id=event.event_id,
            source=event.producer,
            payload=dict(event.payload),
            timestamp=event.occurred_at,
        ).model_dump(mode="json")

    def _state_patch_message(self, *, path: str, value: Any) -> dict[str, Any]:
        version = self._projection_clock.advance()
        return HAStatePatchMessage(
            projection_epoch=version.epoch,
            sequence=version.sequence,
            path=path,
            value=value,
            timestamp=_utc_now(),
        ).model_dump(mode="json")

    def _entity_state_changed_message(
        self,
        *,
        entity_key: str,
        state: Any,
        attributes: dict[str, Any],
    ) -> dict[str, Any]:
        version = self._projection_clock.advance()
        return HAEntityStateChangedMessage(
            projection_epoch=version.epoch,
            sequence=version.sequence,
            entity_key=entity_key,
            state=state,
            attributes=attributes,
            timestamp=_utc_now(),
        ).model_dump(mode="json")

    def _collection_patch_message(
        self,
        *,
        collection_key: str,
        path: str,
        value: Any,
        op: str = "upsert",
    ) -> dict[str, Any]:
        version = self._projection_clock.advance()
        return HACollectionPatchMessage(
            projection_epoch=version.epoch,
            sequence=version.sequence,
            collection_key=collection_key,
            op=op,
            path=path,
            value=value,
            timestamp=_utc_now(),
        ).model_dump(mode="json")

    def _collection_snapshot_message(self, collection_key: str, data: Any) -> dict[str, Any]:
        version = self._projection_clock.advance()
        return HACollectionSnapshotMessage(
            projection_epoch=version.epoch,
            sequence=version.sequence,
            collection_key=collection_key,
            data=data,
            timestamp=_utc_now(),
        ).model_dump(mode="json")

    def _ha_api_path(self, suffix: str) -> str:
        root = self._settings.api_root_prefix.rstrip("/")
        version = self._settings.api_version_prefix.rstrip("/")
        return f"{root}{version}/ha{suffix}"


def _operation_status(status: OperationStatus) -> str:
    mapping = {
        OperationStatus.ACCEPTED: "accepted",
        OperationStatus.QUEUED: "queued",
        OperationStatus.RUNNING: "in_progress",
        OperationStatus.SUCCEEDED: "completed",
        OperationStatus.DEDUPLICATED: "completed",
        OperationStatus.FAILED: "failed",
        OperationStatus.REJECTED: "failed",
        OperationStatus.TIMED_OUT: "failed",
        OperationStatus.CANCELLED: "cancelled",
    }
    return mapping[status]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _clone_runtime(runtime: RuntimeSnapshot) -> RuntimeSnapshot:
    return RuntimeSnapshot(
        entities=copy.deepcopy(runtime.entities),
        collections=copy.deepcopy(runtime.collections),
    )


_PORTFOLIO_EVENT_TYPES = frozenset(
    {
        "portfolio_balance_updated",
        "portfolio_position_changed",
        "portfolio_position_opened",
        "portfolio_position_closed",
        "portfolio_rebalanced",
    }
)

_PATTERN_EVENT_TYPES = frozenset(
    {
        "pattern_boosted",
        "pattern_degraded",
        "pattern_disabled",
    }
)

_ASSET_EVENT_TYPES = frozenset(
    {
        "decision_generated",
        "indicator_updated",
        "market_regime_changed",
        *_PATTERN_EVENT_TYPES,
    }
)
