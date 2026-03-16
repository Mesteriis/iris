from iris.apps.market_data.domain import utc_now
from iris.apps.market_structure.contracts import (
    MarketStructureSourceCreate,
    MarketStructureSourceRead,
    MarketStructureSourceUpdate,
)
from iris.apps.market_structure.engines.health_engine import (
    apply_market_structure_alert_transition,
    clear_market_structure_failure_state,
    merge_market_structure_mapping,
    sync_market_structure_source_health_fields,
)
from iris.apps.market_structure.exceptions import InvalidMarketStructureSourceConfigurationError
from iris.apps.market_structure.models import MarketStructureSource
from iris.apps.market_structure.plugins import get_market_structure_plugin
from iris.apps.market_structure.read_models import market_structure_source_read_model_from_orm
from iris.apps.market_structure.services._shared import MarketStructureServiceSupport


class MarketStructureSourceCommandService(MarketStructureServiceSupport):
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
        now = utc_now()
        sync_market_structure_source_health_fields(source, now=now)
        await self._publish_source_health_dispatch(source, now=now)
        item = await self._queries.get_source_read_by_id(int(source.id))
        return MarketStructureSourceRead.model_validate(
            item if item is not None else market_structure_source_read_model_from_orm(source, now=now)
        )

    async def update_source(
        self,
        source_id: int,
        payload: MarketStructureSourceUpdate,
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
        merged_credentials = merge_market_structure_mapping(dict(source.credentials_json or {}), payload.credentials)
        merged_settings = merge_market_structure_mapping(dict(source.settings_json or {}), payload.settings)
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
            clear_market_structure_failure_state(source)
            source.last_error = None
        if payload.release_quarantine:
            source.quarantined_at = None
            source.quarantine_reason = None
            clear_market_structure_failure_state(source)

        now = utc_now()
        previous_health_status = source.health_status
        sync_market_structure_source_health_fields(source, now=now)
        alert_kind = apply_market_structure_alert_transition(
            source,
            previous_health_status=previous_health_status,
            now=now,
        )
        await self._publish_source_health_dispatch(source, alert_kind=alert_kind, now=now)
        item = await self._queries.get_source_read_by_id(int(source.id))
        return MarketStructureSourceRead.model_validate(
            item if item is not None else market_structure_source_read_model_from_orm(source, now=now)
        )

    async def delete_source(self, source_id: int) -> bool:
        source = await self._sources.get_for_update(source_id)
        if source is None:
            return False
        await self._publish_source_deleted(source, now=utc_now())
        await self._sources.delete(source)
        return True


__all__ = ["MarketStructureSourceCommandService"]
