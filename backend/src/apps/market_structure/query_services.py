from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.anomalies.models import MarketStructureSnapshot
from src.apps.market_structure.constants import MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH
from src.apps.market_structure.exceptions import InvalidMarketStructureSourceConfigurationError
from src.apps.market_structure.models import MarketStructureSource
from src.apps.market_structure.plugins import list_registered_market_structure_plugins
from src.apps.market_structure.read_models import (
    MarketStructurePluginReadModel,
    MarketStructureSnapshotReadModel,
    MarketStructureSourceHealthReadModel,
    MarketStructureSourceReadModel,
    MarketStructureWebhookRegistrationReadModel,
    build_market_structure_source_health_read_model,
    market_structure_plugin_read_model_from_descriptor,
    market_structure_snapshot_read_model_from_orm,
    market_structure_source_read_model_from_orm,
    market_structure_webhook_registration_read_model_from_orm,
)
from src.core.db.persistence import AsyncQueryService


class MarketStructureQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="market_structure", service_name="MarketStructureQueryService")

    async def list_plugins(self) -> tuple[MarketStructurePluginReadModel, ...]:
        self._log_debug("query.list_market_structure_plugins", mode="read")
        items = tuple(
            market_structure_plugin_read_model_from_descriptor(plugin_cls.descriptor)
            for _, plugin_cls in sorted(list_registered_market_structure_plugins().items(), key=lambda item: item[0])
        )
        self._log_debug("query.list_market_structure_plugins.result", mode="read", count=len(items))
        return items

    async def list_sources(self) -> tuple[MarketStructureSourceReadModel, ...]:
        self._log_debug("query.list_market_structure_sources", mode="read")
        rows = (
            (
                await self.session.execute(
                    select(MarketStructureSource).order_by(
                        MarketStructureSource.plugin_name.asc(),
                        MarketStructureSource.display_name.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        items = tuple(market_structure_source_read_model_from_orm(item) for item in rows)
        self._log_debug("query.list_market_structure_sources.result", mode="read", count=len(items))
        return items

    async def list_enabled_source_ids(self) -> tuple[int, ...]:
        self._log_debug("query.list_enabled_market_structure_source_ids", mode="read")
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
        self._log_debug("query.list_enabled_market_structure_source_ids.result", mode="read", count=len(items))
        return items

    async def get_source_read_by_id(self, source_id: int) -> MarketStructureSourceReadModel | None:
        self._log_debug("query.get_market_structure_source_read_by_id", mode="read", source_id=source_id)
        source = await self.session.get(MarketStructureSource, source_id)
        if source is None:
            self._log_debug("query.get_market_structure_source_read_by_id.result", mode="read", found=False)
            return None
        item = market_structure_source_read_model_from_orm(source)
        self._log_debug("query.get_market_structure_source_read_by_id.result", mode="read", found=True)
        return item

    async def get_source_health_read_by_id(self, source_id: int) -> MarketStructureSourceHealthReadModel | None:
        self._log_debug("query.get_market_structure_source_health_read_by_id", mode="read", source_id=source_id)
        source = await self.session.get(MarketStructureSource, source_id)
        if source is None:
            self._log_debug("query.get_market_structure_source_health_read_by_id.result", mode="read", found=False)
            return None
        item = build_market_structure_source_health_read_model(source)
        self._log_debug("query.get_market_structure_source_health_read_by_id.result", mode="read", found=True)
        return item

    async def list_snapshots(
        self,
        *,
        coin_symbol: str | None = None,
        venue: str | None = None,
        limit: int = 50,
    ) -> tuple[MarketStructureSnapshotReadModel, ...]:
        self._log_debug(
            "query.list_market_structure_snapshots",
            mode="read",
            coin_symbol=coin_symbol,
            venue=venue,
            limit=limit,
        )
        stmt = select(MarketStructureSnapshot).order_by(MarketStructureSnapshot.timestamp.desc()).limit(limit)
        if coin_symbol is not None:
            stmt = stmt.where(MarketStructureSnapshot.symbol == coin_symbol.upper())
        if venue is not None:
            stmt = stmt.where(MarketStructureSnapshot.venue == venue.lower())
        rows = (await self.session.execute(stmt)).scalars().all()
        items = tuple(market_structure_snapshot_read_model_from_orm(item) for item in rows)
        self._log_debug("query.list_market_structure_snapshots.result", mode="read", count=len(items))
        return items

    async def get_webhook_registration_read_by_id(
        self,
        source_id: int,
        *,
        include_token: bool = False,
    ) -> MarketStructureWebhookRegistrationReadModel | None:
        self._log_debug(
            "query.get_market_structure_webhook_registration_read_by_id",
            mode="read",
            source_id=source_id,
            include_token=include_token,
            loading_profile="full",
        )
        source = await self.session.get(MarketStructureSource, source_id)
        if source is None:
            self._log_debug(
                "query.get_market_structure_webhook_registration_read_by_id.result",
                mode="read",
                found=False,
            )
            return None
        if source.plugin_name != MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH:
            raise InvalidMarketStructureSourceConfigurationError(
                "Webhook registration is only available for manual_push sources."
            )
        item = market_structure_webhook_registration_read_model_from_orm(source, include_token=include_token)
        self._log_debug(
            "query.get_market_structure_webhook_registration_read_by_id.result",
            mode="read",
            found=True,
        )
        return item


__all__ = ["MarketStructureQueryService"]
