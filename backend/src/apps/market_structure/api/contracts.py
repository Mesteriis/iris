from __future__ import annotations

from typing import Any, Literal

from pydantic import RootModel

from src.apps.market_structure.schemas import (
    BinanceMarketStructureSourceCreateRequest,
    BybitMarketStructureSourceCreateRequest,
    ManualMarketStructureIngestRequest,
    ManualPushMarketStructureSourceCreateRequest,
    ManualWebhookMarketStructureSourceCreateRequest,
    MarketStructureOnboardingRead,
    MarketStructurePluginRead,
    MarketStructureSnapshotRead,
    MarketStructureSourceCreate,
    MarketStructureSourceHealthRead,
    MarketStructureSourceRead,
    MarketStructureSourceUpdate,
    MarketStructureWebhookRegistrationRead,
)
from src.core.http.contracts import AcceptedResponse, HttpContract


class NativeWebhookPayloadWrite(RootModel[dict[str, Any]]):
    root: dict[str, Any]


class MarketStructureSourceJobAcceptedRead(AcceptedResponse):
    operation_type: Literal["market_structure.source.poll"] = "market_structure.source.poll"
    source_id: int
    limit: int


class MarketStructureHealthJobAcceptedRead(AcceptedResponse):
    operation_type: Literal["market_structure.health.refresh"] = "market_structure.health.refresh"


class MarketStructureIngestResultRead(HttpContract):
    status: Literal["ok"] = "ok"
    source_id: int
    plugin_name: str
    created: int


__all__ = [
    "BinanceMarketStructureSourceCreateRequest",
    "BybitMarketStructureSourceCreateRequest",
    "ManualMarketStructureIngestRequest",
    "ManualPushMarketStructureSourceCreateRequest",
    "ManualWebhookMarketStructureSourceCreateRequest",
    "MarketStructureHealthJobAcceptedRead",
    "MarketStructureIngestResultRead",
    "MarketStructureOnboardingRead",
    "MarketStructurePluginRead",
    "MarketStructureSnapshotRead",
    "MarketStructureSourceCreate",
    "MarketStructureSourceHealthRead",
    "MarketStructureSourceJobAcceptedRead",
    "MarketStructureSourceRead",
    "MarketStructureSourceUpdate",
    "MarketStructureWebhookRegistrationRead",
    "NativeWebhookPayloadWrite",
]
