from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MarketStructurePluginRead(BaseModel):
    name: str
    display_name: str
    description: str
    auth_mode: str
    supported: bool
    supports_polling: bool = True
    supports_manual_ingest: bool = False
    required_credentials: list[str] = Field(default_factory=list)
    required_settings: list[str] = Field(default_factory=list)
    runtime_dependencies: list[str] = Field(default_factory=list)
    unsupported_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class MarketStructureSourceCreate(BaseModel):
    plugin_name: str
    display_name: str
    enabled: bool = True
    credentials: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)


class MarketStructureSourceUpdate(BaseModel):
    display_name: str | None = None
    enabled: bool | None = None
    credentials: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None
    reset_cursor: bool = False
    clear_error: bool = False
    release_quarantine: bool = False


class MarketStructureSourceRead(BaseModel):
    id: int
    plugin_name: str
    display_name: str
    enabled: bool
    status: str
    auth_mode: str
    credential_fields_present: list[str]
    settings: dict[str, Any]
    cursor: dict[str, Any]
    last_polled_at: datetime | None = None
    last_success_at: datetime | None = None
    last_snapshot_at: datetime | None = None
    last_error: str | None = None
    health_status: str
    health_changed_at: datetime | None = None
    consecutive_failures: int = 0
    backoff_until: datetime | None = None
    quarantined_at: datetime | None = None
    quarantine_reason: str | None = None
    last_alerted_at: datetime | None = None
    last_alert_kind: str | None = None
    health: "MarketStructureSourceHealthRead"
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MarketStructureSourceHealthRead(BaseModel):
    status: str
    severity: str
    ingest_mode: str
    stale: bool
    stale_after_seconds: int | None = None
    last_activity_at: datetime | None = None
    last_success_at: datetime | None = None
    last_snapshot_at: datetime | None = None
    last_error: str | None = None
    health_changed_at: datetime | None = None
    consecutive_failures: int = 0
    backoff_until: datetime | None = None
    backoff_active: bool = False
    quarantined: bool = False
    quarantined_at: datetime | None = None
    quarantine_reason: str | None = None
    last_alerted_at: datetime | None = None
    last_alert_kind: str | None = None
    message: str

    model_config = ConfigDict(from_attributes=True)


class MarketStructureSnapshotRead(BaseModel):
    id: int
    coin_id: int
    symbol: str
    timeframe: int
    venue: str
    timestamp: datetime
    last_price: float | None = None
    mark_price: float | None = None
    index_price: float | None = None
    funding_rate: float | None = None
    open_interest: float | None = None
    basis: float | None = None
    liquidations_long: float | None = None
    liquidations_short: float | None = None
    volume: float | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class MarketStructureSnapshotCreate(BaseModel):
    timestamp: datetime
    venue: str | None = None
    last_price: float | None = None
    mark_price: float | None = None
    index_price: float | None = None
    funding_rate: float | None = None
    open_interest: float | None = None
    basis: float | None = None
    liquidations_long: float | None = None
    liquidations_short: float | None = None
    volume: float | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict)


class ManualMarketStructureIngestRequest(BaseModel):
    snapshots: list[MarketStructureSnapshotCreate] = Field(default_factory=list, min_length=1, max_length=250)


class MarketStructureOnboardingFieldRead(BaseModel):
    id: str
    label: str
    type: str
    required: bool
    description: str | None = None
    default: Any | None = None


class MarketStructureOnboardingPresetRead(BaseModel):
    id: str
    plugin_name: str
    title: str
    description: str
    endpoint: str
    method: str
    fields: list[MarketStructureOnboardingFieldRead] = Field(default_factory=list)
    source_payload_example: dict[str, Any] = Field(default_factory=dict)


class MarketStructureOnboardingRead(BaseModel):
    title: str
    presets: list[MarketStructureOnboardingPresetRead] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class BinanceMarketStructureSourceCreateRequest(BaseModel):
    coin_symbol: str
    timeframe: int = Field(default=15, ge=1)
    display_name: str | None = None
    market_symbol: str | None = None
    venue: str | None = None
    enabled: bool = True


class BybitMarketStructureSourceCreateRequest(BaseModel):
    coin_symbol: str
    timeframe: int = Field(default=15, ge=1)
    display_name: str | None = None
    market_symbol: str | None = None
    venue: str | None = None
    category: str = "linear"
    enabled: bool = True


class ManualPushMarketStructureSourceCreateRequest(BaseModel):
    coin_symbol: str
    timeframe: int = Field(default=15, ge=1)
    venue: str
    display_name: str | None = None
    enabled: bool = True


class ManualWebhookMarketStructureSourceCreateRequest(BaseModel):
    coin_symbol: str
    timeframe: int = Field(default=15, ge=1)
    display_name: str | None = None
    venue: str | None = None
    enabled: bool = True


class MarketStructureWebhookRegistrationRead(BaseModel):
    source: MarketStructureSourceRead
    provider: str
    venue: str
    ingest_path: str
    native_ingest_path: str | None = None
    method: str
    token_header: str
    token_query_parameter: str
    token_required: bool = True
    token: str | None = None
    sample_payload: dict[str, Any] = Field(default_factory=dict)
    native_payload_example: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
