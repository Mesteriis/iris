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
from src.core.http.contracts import HttpContract


class NativeWebhookPayloadWrite(RootModel[dict[str, Any]]):
    root: dict[str, Any]


class MarketStructureSourceJobQueuedRead(HttpContract):
    status: Literal["queued"] = "queued"
    source_id: int
    limit: int


class MarketStructureHealthJobQueuedRead(HttpContract):
    status: Literal["queued"] = "queued"


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
    "MarketStructureHealthJobQueuedRead",
    "MarketStructureIngestResultRead",
    "MarketStructureOnboardingRead",
    "MarketStructurePluginRead",
    "MarketStructureSnapshotRead",
    "MarketStructureSourceCreate",
    "MarketStructureSourceHealthRead",
    "MarketStructureSourceJobQueuedRead",
    "MarketStructureSourceRead",
    "MarketStructureSourceUpdate",
    "MarketStructureWebhookRegistrationRead",
    "NativeWebhookPayloadWrite",
]
