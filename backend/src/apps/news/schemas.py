from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class NewsPluginRead(BaseModel):
    name: str
    display_name: str
    description: str
    auth_mode: str
    supported: bool
    supports_user_identity: bool = False
    required_credentials: list[str] = Field(default_factory=list)
    required_settings: list[str] = Field(default_factory=list)
    runtime_dependencies: list[str] = Field(default_factory=list)
    unsupported_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class NewsSourceCreate(BaseModel):
    plugin_name: str
    display_name: str
    enabled: bool = True
    credentials: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)


class NewsSourceUpdate(BaseModel):
    display_name: str | None = None
    enabled: bool | None = None
    credentials: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None
    reset_cursor: bool = False
    clear_error: bool = False


class NewsSourceRead(BaseModel):
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
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NewsItemLinkRead(BaseModel):
    coin_id: int
    coin_symbol: str
    matched_symbol: str
    link_type: str
    confidence: float

    model_config = ConfigDict(from_attributes=True)


class NewsItemRead(BaseModel):
    id: int
    source_id: int
    plugin_name: str
    external_id: str
    published_at: datetime
    author_handle: str | None = None
    channel_name: str | None = None
    title: str | None = None
    content_text: str
    url: str | None = None
    symbol_hints: list[str] = Field(default_factory=list)
    payload_json: dict[str, Any] = Field(default_factory=dict)
    normalization_status: str
    normalized_payload_json: dict[str, Any] = Field(default_factory=dict)
    normalized_at: datetime | None = None
    sentiment_score: float | None = None
    relevance_score: float | None = None
    links: list[NewsItemLinkRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class TelegramSessionCodeRequest(BaseModel):
    api_id: int
    api_hash: str
    phone_number: str


class TelegramSessionCodeRequestRead(BaseModel):
    status: str
    phone_number: str
    phone_code_hash: str


class TelegramSessionConfirmRequest(BaseModel):
    api_id: int
    api_hash: str
    phone_number: str
    phone_code_hash: str
    code: str
    password: str | None = None


class TelegramSessionConfirmRead(BaseModel):
    status: str
    session_string: str | None = None
    user_id: int | None = None
    username: str | None = None
    display_name: str | None = None


class TelegramDialogsRequest(BaseModel):
    api_id: int
    api_hash: str
    session_string: str
    limit: int = Field(default=100, ge=1, le=500)
    include_users: bool = False


class TelegramDialogRead(BaseModel):
    entity_id: int
    entity_type: str
    title: str
    username: str | None = None
    access_hash: str | None = None
    selectable: bool = True
    settings_hint: dict[str, Any] = Field(default_factory=dict)


class TelegramDialogSelection(BaseModel):
    entity_id: int
    entity_type: str
    title: str
    username: str | None = None
    access_hash: str | None = None
    display_name: str | None = None
    enabled: bool = True
    max_items_per_poll: int | None = Field(default=None, ge=1, le=100)


class TelegramSourceFromDialogCreate(BaseModel):
    api_id: int
    api_hash: str
    session_string: str
    dialog: TelegramDialogSelection


class TelegramBulkSubscribeRequest(BaseModel):
    api_id: int
    api_hash: str
    session_string: str
    dialogs: list[TelegramDialogSelection] = Field(default_factory=list, min_length=1, max_length=100)


class TelegramDialogSubscribeResult(BaseModel):
    title: str
    status: str
    display_name: str | None = None
    source_id: int | None = None
    reason: str | None = None


class TelegramBulkSubscribeRead(BaseModel):
    created_count: int
    skipped_count: int
    created: list[NewsSourceRead] = Field(default_factory=list)
    results: list[TelegramDialogSubscribeResult] = Field(default_factory=list)


class TelegramWizardFieldRead(BaseModel):
    id: str
    label: str
    type: str
    required: bool
    secret: bool = False
    description: str | None = None


class TelegramWizardStepRead(BaseModel):
    id: str
    title: str
    description: str
    endpoint: str
    method: str
    fields: list[TelegramWizardFieldRead] = Field(default_factory=list)


class TelegramWizardRead(BaseModel):
    plugin_name: str
    title: str
    supported_dialog_types: list[str] = Field(default_factory=list)
    private_dialog_support: bool = True
    steps: list[TelegramWizardStepRead] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    source_payload_example: dict[str, Any] = Field(default_factory=dict)
