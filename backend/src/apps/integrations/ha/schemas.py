from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

HAMode = Literal["full", "local", "ha_addon"]
HAOperationStatus = Literal["accepted", "queued", "in_progress", "completed", "failed", "cancelled"]
HAPlatform = Literal["sensor", "binary_sensor", "switch", "button", "select", "number", "event"]
HACollectionKind = Literal["mapping", "list", "table", "timeline", "summary"]
HACommandKind = Literal["action", "flow", "toggle", "selection", "refresh", "admin"]


class HAErrorRead(BaseModel):
    code: str
    message: str
    message_key: str | None = None
    message_params: dict[str, Any] = Field(default_factory=dict)
    locale: str | None = None
    details: dict[str, Any] | None = None


class HACapabilitiesRead(BaseModel):
    dashboard: bool
    commands: bool
    collections: bool
    promoted_entities: bool = False


class HAInstanceRead(BaseModel):
    instance_id: str
    display_name: str
    version: str
    protocol_version: int
    catalog_version: str
    mode: HAMode
    minimum_ha_integration_version: str
    recommended_ha_integration_version: str


class HAHealthRead(BaseModel):
    status: Literal["ok"]
    instance_id: str
    version: str
    protocol_version: int
    catalog_version: str
    mode: HAMode
    websocket_supported: bool
    dashboard_supported: bool
    commands_supported: bool
    collections_supported: bool


class HABootstrapRead(BaseModel):
    instance: HAInstanceRead
    capabilities: HACapabilitiesRead
    catalog_url: str
    dashboard_url: str
    ws_url: str
    state_url: str


class HAAvailabilityRead(BaseModel):
    modes: list[HAMode]
    requires_features: list[str] = Field(default_factory=list)
    status: Literal["active", "deprecated", "hidden", "removed"] = "active"


class HAEntityDefinitionRead(BaseModel):
    entity_key: str
    platform: HAPlatform
    name: str
    state_source: str
    command_key: str | None = None
    icon: str | None = None
    category: str | None = None
    default_enabled: bool = True
    availability: HAAvailabilityRead
    since_version: str
    deprecated_since: str | None = None
    replacement: str | None = None
    entity_registry_enabled_default: bool = True
    device_class: str | None = None
    unit_of_measurement: str | None = None


class HACollectionDefinitionRead(BaseModel):
    collection_key: str
    kind: HACollectionKind
    transport: Literal["websocket", "http"]
    dashboard_only: bool = False
    since_version: str


class HACommandDefinitionRead(BaseModel):
    command_key: str
    name: str
    kind: HACommandKind
    input_schema: dict[str, Any] | None = None
    returns: str | None = None
    availability: HAAvailabilityRead | None = None
    since_version: str
    deprecated_since: str | None = None
    replacement: str | None = None


class HADashboardWidgetRead(BaseModel):
    widget_key: str
    title: str
    kind: Literal["summary", "table", "timeline", "status", "actions", "chart_placeholder", "list"]
    source: str
    entity_keys: list[str] = Field(default_factory=list)
    command_keys: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class HADashboardSectionRead(BaseModel):
    section_key: str
    title: str
    widgets: list[HADashboardWidgetRead]


class HADashboardViewRead(BaseModel):
    view_key: str
    title: str
    kind: Literal["dashboard_view"] = "dashboard_view"
    sections: list[HADashboardSectionRead]


class HACatalogRead(BaseModel):
    catalog_version: str
    protocol_version: int
    mode: HAMode
    entities: list[HAEntityDefinitionRead]
    collections: list[HACollectionDefinitionRead]
    commands: list[HACommandDefinitionRead]
    views: list[HADashboardViewRead]


class HADashboardRead(BaseModel):
    version: int
    slug: str
    title: str
    views: list[HADashboardViewRead]


class HAEntityStateRead(BaseModel):
    state: Any
    attributes: dict[str, Any] = Field(default_factory=dict)


class HAStateSnapshotRead(BaseModel):
    projection_epoch: str
    sequence: int
    entities: dict[str, HAEntityStateRead]
    collections: dict[str, Any]


class HAOperationRead(BaseModel):
    operation_id: str
    status: HAOperationStatus
    result: dict[str, Any] | None = None
    error: HAErrorRead | None = None


class HAClientIdentityRead(BaseModel):
    name: str
    version: str


class HAHelloMessage(BaseModel):
    type: Literal["hello"]
    protocol_version: int
    client: HAClientIdentityRead
    instance_id: str | None = None


class HASubscribeMessage(BaseModel):
    type: Literal["subscribe"]
    entities: list[str] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)
    operations: bool = False
    catalog: bool = False
    dashboard: bool = False


class HAUnsubscribeMessage(BaseModel):
    type: Literal["unsubscribe"]
    entities: list[str] = Field(default_factory=list)
    collections: list[str] = Field(default_factory=list)
    operations: bool = False
    catalog: bool = False
    dashboard: bool = False


class HAPingMessage(BaseModel):
    type: Literal["ping"]
    timestamp: datetime | str | None = None


class HACommandExecuteMessage(BaseModel):
    type: Literal["command_execute"]
    command: str
    payload: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class HAAckEventMessage(BaseModel):
    type: Literal["ack_event"]
    event_id: str


class HAWelcomeMessage(BaseModel):
    type: Literal["welcome"] = "welcome"
    protocol_version: int
    instance: HAInstanceRead
    capabilities: HACapabilitiesRead


class HAPongMessage(BaseModel):
    type: Literal["pong"] = "pong"
    timestamp: datetime | str | None = None


class HAEntityStateChangedMessage(BaseModel):
    type: Literal["entity_state_changed"] = "entity_state_changed"
    projection_epoch: str
    sequence: int
    entity_key: str
    state: Any
    attributes: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime


class HAStatePatchMessage(BaseModel):
    type: Literal["state_patch"] = "state_patch"
    projection_epoch: str
    sequence: int
    path: str
    value: Any
    timestamp: datetime


class HACollectionSnapshotMessage(BaseModel):
    type: Literal["collection_snapshot"] = "collection_snapshot"
    projection_epoch: str
    sequence: int
    collection_key: str
    data: Any
    timestamp: datetime


class HACollectionPatchMessage(BaseModel):
    type: Literal["collection_patch"] = "collection_patch"
    projection_epoch: str
    sequence: int
    collection_key: str
    op: Literal["upsert", "remove", "replace"]
    path: str
    value: Any
    timestamp: datetime


class HAEventEmittedMessage(BaseModel):
    type: Literal["event_emitted"] = "event_emitted"
    event_type: str
    event_id: str
    source: str
    payload: dict[str, Any]
    timestamp: datetime


class HASystemHealthMessage(BaseModel):
    type: Literal["system_health"] = "system_health"
    projection_epoch: str
    sequence: int
    status: Literal["ok"]
    bridge: Literal["ready"]
    timestamp: datetime


class HACommandAckMessage(BaseModel):
    type: Literal["command_ack"] = "command_ack"
    request_id: str
    accepted: bool
    operation_id: str | None = None
    error: HAErrorRead | None = None
    retryable: bool | None = None


class HAOperationUpdateMessage(BaseModel):
    type: Literal["operation_update"] = "operation_update"
    projection_epoch: str
    sequence: int
    operation_id: str
    status: HAOperationStatus
    command: str | None = None
    operation_type: str | None = None
    message: str | None = None
    message_key: str | None = None
    message_params: dict[str, Any] = Field(default_factory=dict)
    locale: str | None = None
    result: dict[str, Any] | None = None
    error: HAErrorRead | None = None
    timestamp: datetime


class HAResyncRequiredMessage(BaseModel):
    type: Literal["resync_required"] = "resync_required"
    reason: str
    state_url: str
    message: str | None = None
