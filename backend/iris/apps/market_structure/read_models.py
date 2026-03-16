from dataclasses import dataclass
from datetime import datetime
from typing import Any

from iris.apps.anomalies.models import MarketStructureSnapshot
from iris.apps.market_structure.constants import (
    MARKET_STRUCTURE_INGEST_TOKEN_HEADER,
    MARKET_STRUCTURE_INGEST_TOKEN_QUERY_PARAMETER,
    MARKET_STRUCTURE_MANUAL_PROVIDER_COINALYZE,
    MARKET_STRUCTURE_MANUAL_PROVIDER_COINGLASS,
    MARKET_STRUCTURE_MANUAL_PROVIDER_DERIVATIVES_WEBHOOK,
    MARKET_STRUCTURE_MANUAL_PROVIDER_HYBLOCK,
    MARKET_STRUCTURE_MANUAL_PROVIDER_LIQSCOPE,
    MARKET_STRUCTURE_MANUAL_PROVIDER_LIQUIDATION_WEBHOOK,
)
from iris.apps.market_structure.engines.health_engine import (
    build_market_structure_source_health,
)
from iris.apps.market_structure.engines.health_engine import (
    market_structure_credential_fields_present as engine_market_structure_credential_fields_present,
)
from iris.apps.market_structure.engines.health_engine import (
    market_structure_source_ingest_mode as engine_market_structure_source_ingest_mode,
)
from iris.apps.market_structure.engines.health_engine import (
    market_structure_source_provider as engine_market_structure_source_provider,
)
from iris.apps.market_structure.engines.health_engine import (
    market_structure_source_status as engine_market_structure_source_status,
)
from iris.apps.market_structure.engines.health_engine import (
    market_structure_stale_after_seconds as engine_market_structure_stale_after_seconds,
)
from iris.apps.market_structure.models import MarketStructureSource
from iris.apps.market_structure.normalizers import get_market_structure_webhook_normalizer_class
from iris.apps.market_structure.plugins import MarketStructurePluginDescriptor
from iris.core.db.persistence import freeze_json_value
from iris.core.http.router_policy import api_path


def market_structure_source_status_from_orm(source: MarketStructureSource) -> str:
    return engine_market_structure_source_status(source)


def market_structure_credential_fields_present(credentials: dict[str, Any]) -> tuple[str, ...]:
    return tuple(engine_market_structure_credential_fields_present(credentials))


def market_structure_source_provider_from_orm(source: MarketStructureSource) -> str:
    return engine_market_structure_source_provider(source)


def market_structure_source_ingest_mode_from_orm(source: MarketStructureSource) -> str:
    return engine_market_structure_source_ingest_mode(source)


def market_structure_stale_after_seconds_from_orm(source: MarketStructureSource) -> int | None:
    return engine_market_structure_stale_after_seconds(source)


@dataclass(slots=True, frozen=True)
class MarketStructurePluginReadModel:
    name: str
    display_name: str
    description: str
    auth_mode: str
    supported: bool
    supports_polling: bool
    supports_manual_ingest: bool
    required_credentials: tuple[str, ...]
    required_settings: tuple[str, ...]
    runtime_dependencies: tuple[str, ...]
    unsupported_reason: str | None


@dataclass(slots=True, frozen=True)
class MarketStructureSourceHealthReadModel:
    status: str
    severity: str
    ingest_mode: str
    stale: bool
    stale_after_seconds: int | None
    last_activity_at: datetime | None
    last_success_at: datetime | None
    last_snapshot_at: datetime | None
    last_error: str | None
    health_changed_at: datetime | None
    consecutive_failures: int
    backoff_until: datetime | None
    backoff_active: bool
    quarantined: bool
    quarantined_at: datetime | None
    quarantine_reason: str | None
    last_alerted_at: datetime | None
    last_alert_kind: str | None
    message: str


@dataclass(slots=True, frozen=True)
class MarketStructureSourceReadModel:
    id: int
    plugin_name: str
    display_name: str
    enabled: bool
    status: str
    auth_mode: str
    credential_fields_present: tuple[str, ...]
    settings: Any
    cursor: Any
    last_polled_at: datetime | None
    last_success_at: datetime | None
    last_snapshot_at: datetime | None
    last_error: str | None
    health_status: str
    health_changed_at: datetime | None
    consecutive_failures: int
    backoff_until: datetime | None
    quarantined_at: datetime | None
    quarantine_reason: str | None
    last_alerted_at: datetime | None
    last_alert_kind: str | None
    health: MarketStructureSourceHealthReadModel
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class MarketStructureSnapshotReadModel:
    id: int
    coin_id: int
    symbol: str
    timeframe: int
    venue: str
    timestamp: datetime
    last_price: float | None
    mark_price: float | None
    index_price: float | None
    funding_rate: float | None
    open_interest: float | None
    basis: float | None
    liquidations_long: float | None
    liquidations_short: float | None
    volume: float | None
    payload_json: Any


@dataclass(slots=True, frozen=True)
class MarketStructureWebhookRegistrationReadModel:
    source: MarketStructureSourceReadModel
    provider: str
    venue: str
    ingest_path: str
    native_ingest_path: str | None
    method: str
    token_header: str
    token_query_parameter: str
    token_required: bool
    token: str | None
    sample_payload: Any
    native_payload_example: Any
    notes: tuple[str, ...]


def market_structure_plugin_read_model_from_descriptor(
    descriptor: MarketStructurePluginDescriptor,
) -> MarketStructurePluginReadModel:
    return MarketStructurePluginReadModel(
        name=str(descriptor.name),
        display_name=str(descriptor.display_name),
        description=str(descriptor.description),
        auth_mode=str(descriptor.auth_mode),
        supported=bool(descriptor.supported),
        supports_polling=bool(descriptor.supports_polling),
        supports_manual_ingest=bool(descriptor.supports_manual_ingest),
        required_credentials=tuple(str(value) for value in descriptor.required_credentials),
        required_settings=tuple(str(value) for value in descriptor.required_settings),
        runtime_dependencies=tuple(str(value) for value in descriptor.runtime_dependencies),
        unsupported_reason=str(descriptor.unsupported_reason) if descriptor.unsupported_reason is not None else None,
    )


def build_market_structure_source_health_read_model(
    source: MarketStructureSource,
    *,
    now: datetime | None = None,
) -> MarketStructureSourceHealthReadModel:
    health = build_market_structure_source_health(source, now=now)
    return MarketStructureSourceHealthReadModel(
        status=health.status,
        severity=health.severity,
        ingest_mode=health.ingest_mode,
        stale=health.stale,
        stale_after_seconds=health.stale_after_seconds,
        last_activity_at=health.last_activity_at,
        last_success_at=health.last_success_at,
        last_snapshot_at=health.last_snapshot_at,
        last_error=health.last_error,
        health_changed_at=health.health_changed_at,
        consecutive_failures=int(health.consecutive_failures),
        backoff_until=health.backoff_until,
        backoff_active=health.backoff_active,
        quarantined=health.quarantined,
        quarantined_at=health.quarantined_at,
        quarantine_reason=health.quarantine_reason,
        last_alerted_at=health.last_alerted_at,
        last_alert_kind=health.last_alert_kind,
        message=health.message,
    )


def market_structure_source_read_model_from_orm(
    source: MarketStructureSource,
    *,
    now: datetime | None = None,
) -> MarketStructureSourceReadModel:
    credentials = dict(source.credentials_json or {})
    return MarketStructureSourceReadModel(
        id=int(source.id),
        plugin_name=str(source.plugin_name),
        display_name=str(source.display_name),
        enabled=bool(source.enabled),
        status=market_structure_source_status_from_orm(source),
        auth_mode=str(source.auth_mode),
        credential_fields_present=market_structure_credential_fields_present(credentials),
        settings=freeze_json_value(dict(source.settings_json or {})),
        cursor=freeze_json_value(dict(source.cursor_json or {})),
        last_polled_at=source.last_polled_at,
        last_success_at=source.last_success_at,
        last_snapshot_at=source.last_snapshot_at,
        last_error=str(source.last_error) if source.last_error is not None else None,
        health_status=str(source.health_status),
        health_changed_at=source.health_changed_at,
        consecutive_failures=int(source.consecutive_failures or 0),
        backoff_until=source.backoff_until,
        quarantined_at=source.quarantined_at,
        quarantine_reason=str(source.quarantine_reason) if source.quarantine_reason is not None else None,
        last_alerted_at=source.last_alerted_at,
        last_alert_kind=str(source.last_alert_kind) if source.last_alert_kind is not None else None,
        health=build_market_structure_source_health_read_model(source, now=now),
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def market_structure_snapshot_read_model_from_orm(snapshot: MarketStructureSnapshot) -> MarketStructureSnapshotReadModel:
    return MarketStructureSnapshotReadModel(
        id=int(snapshot.id),
        coin_id=int(snapshot.coin_id),
        symbol=str(snapshot.symbol),
        timeframe=int(snapshot.timeframe),
        venue=str(snapshot.venue),
        timestamp=snapshot.timestamp,
        last_price=float(snapshot.last_price) if snapshot.last_price is not None else None,
        mark_price=float(snapshot.mark_price) if snapshot.mark_price is not None else None,
        index_price=float(snapshot.index_price) if snapshot.index_price is not None else None,
        funding_rate=float(snapshot.funding_rate) if snapshot.funding_rate is not None else None,
        open_interest=float(snapshot.open_interest) if snapshot.open_interest is not None else None,
        basis=float(snapshot.basis) if snapshot.basis is not None else None,
        liquidations_long=float(snapshot.liquidations_long) if snapshot.liquidations_long is not None else None,
        liquidations_short=float(snapshot.liquidations_short) if snapshot.liquidations_short is not None else None,
        volume=float(snapshot.volume) if snapshot.volume is not None else None,
        payload_json=freeze_json_value(dict(snapshot.payload_json or {})),
    )


def market_structure_sample_webhook_payload() -> Any:
    return freeze_json_value(
        {
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
    )


def market_structure_webhook_registration_read_model_from_orm(
    source: MarketStructureSource,
    *,
    include_token: bool,
) -> MarketStructureWebhookRegistrationReadModel:
    settings = dict(source.settings_json or {})
    credentials = dict(source.credentials_json or {})
    provider = market_structure_source_provider_from_orm(source)
    normalizer_cls = get_market_structure_webhook_normalizer_class(provider)
    return MarketStructureWebhookRegistrationReadModel(
        source=market_structure_source_read_model_from_orm(source),
        provider=provider,
        venue=str(settings.get("venue") or "manual"),
        ingest_path=api_path(f"/market-structure/sources/{int(source.id)}/snapshots"),
        native_ingest_path=api_path(f"/market-structure/sources/{int(source.id)}/webhook/native"),
        method="POST",
        token_header=MARKET_STRUCTURE_INGEST_TOKEN_HEADER,
        token_query_parameter=MARKET_STRUCTURE_INGEST_TOKEN_QUERY_PARAMETER,
        token_required=bool(credentials.get("ingest_token")),
        token=str(credentials.get("ingest_token")) if include_token else None,
        sample_payload=market_structure_sample_webhook_payload(),
        native_payload_example=freeze_json_value(
            dict(normalizer_cls.descriptor.sample_payload) if normalizer_cls is not None else {}
        ),
        notes=(
            "POST normalized snapshots to the ingest_path or provider-native webhook payloads to the native_ingest_path.",
            "The token is shown only on registration and rotation responses.",
        ),
    )


__all__ = [
    "MarketStructurePluginReadModel",
    "MarketStructureSnapshotReadModel",
    "MarketStructureSourceHealthReadModel",
    "MarketStructureSourceReadModel",
    "MarketStructureWebhookRegistrationReadModel",
    "build_market_structure_source_health_read_model",
    "market_structure_plugin_read_model_from_descriptor",
    "market_structure_snapshot_read_model_from_orm",
    "market_structure_source_ingest_mode_from_orm",
    "market_structure_source_provider_from_orm",
    "market_structure_source_read_model_from_orm",
    "market_structure_source_status_from_orm",
    "market_structure_stale_after_seconds_from_orm",
    "market_structure_webhook_registration_read_model_from_orm",
]
