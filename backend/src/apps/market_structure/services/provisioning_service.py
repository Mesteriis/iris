from __future__ import annotations

import secrets
from typing import Any

from src.apps.market_structure.constants import (
    MARKET_STRUCTURE_MANUAL_INGEST_MODE_WEBHOOK,
    MARKET_STRUCTURE_MANUAL_PROVIDER_COINALYZE,
    MARKET_STRUCTURE_MANUAL_PROVIDER_COINGLASS,
    MARKET_STRUCTURE_MANUAL_PROVIDER_DERIVATIVES_WEBHOOK,
    MARKET_STRUCTURE_MANUAL_PROVIDER_HYBLOCK,
    MARKET_STRUCTURE_MANUAL_PROVIDER_LIQSCOPE,
    MARKET_STRUCTURE_MANUAL_PROVIDER_LIQUIDATION_WEBHOOK,
    MARKET_STRUCTURE_PLUGIN_BINANCE_USDM,
    MARKET_STRUCTURE_PLUGIN_BYBIT_DERIVATIVES,
    MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH,
)
from src.apps.market_structure.contracts import (
    BinanceMarketStructureSourceCreateRequest,
    BybitMarketStructureSourceCreateRequest,
    ManualPushMarketStructureSourceCreateRequest,
    ManualWebhookMarketStructureSourceCreateRequest,
    MarketStructureSourceCreate,
    MarketStructureSourceRead,
    MarketStructureWebhookRegistrationRead,
)
from src.apps.market_structure.exceptions import InvalidMarketStructureSourceConfigurationError
from src.apps.market_structure.models import MarketStructureSource
from src.apps.market_structure.query_services import MarketStructureQueryService
from src.apps.market_structure.read_models import market_structure_webhook_registration_read_model_from_orm
from src.apps.market_structure.repositories import MarketStructureSourceRepository
from src.apps.market_structure.services.source_command_service import MarketStructureSourceCommandService
from src.core.db.persistence import thaw_json_value
from src.core.db.uow import BaseAsyncUnitOfWork

_WEBHOOK_SOURCE_PRESETS: dict[str, tuple[str, str, str]] = {
    MARKET_STRUCTURE_MANUAL_PROVIDER_LIQSCOPE: (
        MARKET_STRUCTURE_MANUAL_PROVIDER_LIQSCOPE,
        MARKET_STRUCTURE_MANUAL_PROVIDER_LIQSCOPE,
        "Liqscope Webhook",
    ),
    MARKET_STRUCTURE_MANUAL_PROVIDER_LIQUIDATION_WEBHOOK: (
        MARKET_STRUCTURE_MANUAL_PROVIDER_LIQUIDATION_WEBHOOK,
        "liquidations_api",
        "Liquidation Webhook",
    ),
    MARKET_STRUCTURE_MANUAL_PROVIDER_DERIVATIVES_WEBHOOK: (
        MARKET_STRUCTURE_MANUAL_PROVIDER_DERIVATIVES_WEBHOOK,
        "derivatives_webhook",
        "Derivatives Webhook",
    ),
    MARKET_STRUCTURE_MANUAL_PROVIDER_COINGLASS: (
        MARKET_STRUCTURE_MANUAL_PROVIDER_COINGLASS,
        MARKET_STRUCTURE_MANUAL_PROVIDER_COINGLASS,
        "Coinglass Webhook",
    ),
    MARKET_STRUCTURE_MANUAL_PROVIDER_HYBLOCK: (
        MARKET_STRUCTURE_MANUAL_PROVIDER_HYBLOCK,
        MARKET_STRUCTURE_MANUAL_PROVIDER_HYBLOCK,
        "Hyblock Webhook",
    ),
    MARKET_STRUCTURE_MANUAL_PROVIDER_COINALYZE: (
        MARKET_STRUCTURE_MANUAL_PROVIDER_COINALYZE,
        MARKET_STRUCTURE_MANUAL_PROVIDER_COINALYZE,
        "Coinalyze Webhook",
    ),
}


def _webhook_registration_schema_from_read_model(item) -> MarketStructureWebhookRegistrationRead:
    return MarketStructureWebhookRegistrationRead.model_validate(
        {
            "source": item.source,
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


class MarketStructureSourceProvisioningService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._queries = MarketStructureQueryService(uow.session)
        self._sources = MarketStructureSourceRepository(uow.session)
        self._commands = MarketStructureSourceCommandService(uow)

    async def create_binance_source(
        self,
        payload: BinanceMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureSourceRead:
        payload = BinanceMarketStructureSourceCreateRequest.model_validate(payload)
        return await self._commands.create_source(
            MarketStructureSourceCreate(
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
        )

    async def create_bybit_source(
        self,
        payload: BybitMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureSourceRead:
        payload = BybitMarketStructureSourceCreateRequest.model_validate(payload)
        return await self._commands.create_source(
            MarketStructureSourceCreate(
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
        )

    async def create_manual_source(
        self,
        payload: ManualPushMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureSourceRead:
        payload = ManualPushMarketStructureSourceCreateRequest.model_validate(payload)
        return await self._commands.create_source(
            MarketStructureSourceCreate(
                plugin_name=MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH,
                display_name=(payload.display_name or f"{payload.coin_symbol.upper()} {payload.venue.strip()} Feed").strip(),
                enabled=bool(payload.enabled),
                settings={
                    "coin_symbol": payload.coin_symbol.upper(),
                    "timeframe": int(payload.timeframe),
                    "venue": payload.venue.strip().lower(),
                },
            )
        )

    async def create_liqscope_webhook_source(
        self,
        payload: ManualWebhookMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureWebhookRegistrationRead:
        return await self._create_webhook_source(payload, provider=MARKET_STRUCTURE_MANUAL_PROVIDER_LIQSCOPE)

    async def create_liquidation_webhook_source(
        self,
        payload: ManualWebhookMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureWebhookRegistrationRead:
        return await self._create_webhook_source(payload, provider=MARKET_STRUCTURE_MANUAL_PROVIDER_LIQUIDATION_WEBHOOK)

    async def create_derivatives_webhook_source(
        self,
        payload: ManualWebhookMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureWebhookRegistrationRead:
        return await self._create_webhook_source(payload, provider=MARKET_STRUCTURE_MANUAL_PROVIDER_DERIVATIVES_WEBHOOK)

    async def create_coinglass_webhook_source(
        self,
        payload: ManualWebhookMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureWebhookRegistrationRead:
        return await self._create_webhook_source(payload, provider=MARKET_STRUCTURE_MANUAL_PROVIDER_COINGLASS)

    async def create_hyblock_webhook_source(
        self,
        payload: ManualWebhookMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureWebhookRegistrationRead:
        return await self._create_webhook_source(payload, provider=MARKET_STRUCTURE_MANUAL_PROVIDER_HYBLOCK)

    async def create_coinalyze_webhook_source(
        self,
        payload: ManualWebhookMarketStructureSourceCreateRequest | dict[str, Any],
    ) -> MarketStructureWebhookRegistrationRead:
        return await self._create_webhook_source(payload, provider=MARKET_STRUCTURE_MANUAL_PROVIDER_COINALYZE)

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
        item = await self._queries.get_webhook_registration_read_by_id(source_id, include_token=True)
        return _webhook_registration_schema_from_read_model(
            item
            if item is not None
            else market_structure_webhook_registration_read_model_from_orm(source, include_token=True)
        )

    async def _create_webhook_source(
        self,
        payload: ManualWebhookMarketStructureSourceCreateRequest | dict[str, Any],
        *,
        provider: str,
    ) -> MarketStructureWebhookRegistrationRead:
        provider_name, venue_default, display_suffix = _WEBHOOK_SOURCE_PRESETS[provider]
        payload = ManualWebhookMarketStructureSourceCreateRequest.model_validate(payload)
        source = await self._commands.create_source(
            MarketStructureSourceCreate(
                plugin_name=MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH,
                display_name=(payload.display_name or f"{payload.coin_symbol.upper()} {display_suffix}").strip(),
                enabled=bool(payload.enabled),
                credentials={"ingest_token": self._issue_ingest_token()},
                settings={
                    "coin_symbol": payload.coin_symbol.upper(),
                    "timeframe": int(payload.timeframe),
                    "venue": (payload.venue or venue_default).strip().lower(),
                    "provider": provider_name,
                    "ingest_mode": MARKET_STRUCTURE_MANUAL_INGEST_MODE_WEBHOOK,
                },
            )
        )
        item = await self._queries.get_webhook_registration_read_by_id(int(source.id), include_token=True)
        if item is None:
            raise InvalidMarketStructureSourceConfigurationError("Webhook source could not be reloaded after creation.")
        return _webhook_registration_schema_from_read_model(item)

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

    @staticmethod
    def _issue_ingest_token() -> str:
        return secrets.token_urlsafe(24)

    @staticmethod
    def _ensure_webhook_capable_source(source: MarketStructureSource) -> None:
        if source.plugin_name != MARKET_STRUCTURE_PLUGIN_MANUAL_PUSH:
            raise InvalidMarketStructureSourceConfigurationError(
                "Webhook registration is only available for manual_push sources."
            )


__all__ = ["MarketStructureSourceProvisioningService"]
