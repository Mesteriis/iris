from typing import Any

from iris.apps.market_structure.api.contracts import (
    MarketStructureHealthJobAcceptedRead,
    MarketStructureIngestResultRead,
    MarketStructurePluginRead,
    MarketStructureSnapshotRead,
    MarketStructureSourceHealthRead,
    MarketStructureSourceJobAcceptedRead,
    MarketStructureSourceRead,
    MarketStructureWebhookRegistrationRead,
)
from iris.apps.market_structure.services.results import (
    MarketStructureIngestResult,
    serialize_market_structure_ingest_result,
)
from iris.core.db.persistence import thaw_json_value
from iris.core.http.operation_localization import dispatch_result_message_fields
from iris.core.http.operation_store import OperationDispatchResult


def market_structure_plugin_read(item: Any) -> MarketStructurePluginRead:
    return MarketStructurePluginRead.model_validate(
        {
            "name": item.name,
            "display_name": item.display_name,
            "description": item.description,
            "auth_mode": item.auth_mode,
            "supported": bool(item.supported),
            "supports_polling": bool(item.supports_polling),
            "supports_manual_ingest": bool(item.supports_manual_ingest),
            "required_credentials": list(item.required_credentials),
            "required_settings": list(item.required_settings),
            "runtime_dependencies": list(item.runtime_dependencies),
            "unsupported_reason": item.unsupported_reason,
        }
    )


def market_structure_source_health_read(item: Any) -> MarketStructureSourceHealthRead:
    return MarketStructureSourceHealthRead.model_validate(item)


def market_structure_source_read(item: Any) -> MarketStructureSourceRead:
    return MarketStructureSourceRead.model_validate(
        {
            "id": int(item.id),
            "plugin_name": item.plugin_name,
            "display_name": item.display_name,
            "enabled": bool(item.enabled),
            "status": item.status,
            "auth_mode": item.auth_mode,
            "credential_fields_present": list(item.credential_fields_present),
            "settings": thaw_json_value(item.settings),
            "cursor": thaw_json_value(item.cursor),
            "last_polled_at": item.last_polled_at,
            "last_success_at": item.last_success_at,
            "last_snapshot_at": item.last_snapshot_at,
            "last_error": item.last_error,
            "health_status": item.health_status,
            "health_changed_at": item.health_changed_at,
            "consecutive_failures": int(item.consecutive_failures),
            "backoff_until": item.backoff_until,
            "quarantined_at": item.quarantined_at,
            "quarantine_reason": item.quarantine_reason,
            "last_alerted_at": item.last_alerted_at,
            "last_alert_kind": item.last_alert_kind,
            "health": market_structure_source_health_read(item.health),
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
    )


def market_structure_snapshot_read(item: Any) -> MarketStructureSnapshotRead:
    return MarketStructureSnapshotRead.model_validate(
        {
            "id": int(item.id),
            "coin_id": int(item.coin_id),
            "symbol": item.symbol,
            "timeframe": int(item.timeframe),
            "venue": item.venue,
            "timestamp": item.timestamp,
            "last_price": item.last_price,
            "mark_price": item.mark_price,
            "index_price": item.index_price,
            "funding_rate": item.funding_rate,
            "open_interest": item.open_interest,
            "basis": item.basis,
            "liquidations_long": item.liquidations_long,
            "liquidations_short": item.liquidations_short,
            "volume": item.volume,
            "payload_json": thaw_json_value(item.payload_json),
        }
    )


def market_structure_webhook_registration_read(item: Any) -> MarketStructureWebhookRegistrationRead:
    return MarketStructureWebhookRegistrationRead.model_validate(
        {
            "source": market_structure_source_read(item.source),
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


def market_structure_source_job_accepted_read(
    *,
    dispatch_result: OperationDispatchResult,
    source_id: int,
    limit: int,
    locale: str | None = None,
) -> MarketStructureSourceJobAcceptedRead:
    operation = dispatch_result.operation
    return MarketStructureSourceJobAcceptedRead.model_validate(
        {
            "operation_id": operation.operation_id,
            "accepted_at": operation.accepted_at,
            "correlation_id": operation.correlation_id,
            "deduplicated": dispatch_result.deduplicated,
            **dispatch_result_message_fields(dispatch_result, locale=locale),
            "source_id": int(source_id),
            "limit": int(limit),
        }
    )


def market_structure_health_job_accepted_read(
    *,
    dispatch_result: OperationDispatchResult,
    locale: str | None = None,
) -> MarketStructureHealthJobAcceptedRead:
    operation = dispatch_result.operation
    return MarketStructureHealthJobAcceptedRead.model_validate(
        {
            "operation_id": operation.operation_id,
            "accepted_at": operation.accepted_at,
            "correlation_id": operation.correlation_id,
            "deduplicated": dispatch_result.deduplicated,
            **dispatch_result_message_fields(dispatch_result, locale=locale),
        }
    )


def market_structure_ingest_result_read(result: MarketStructureIngestResult) -> MarketStructureIngestResultRead:
    return MarketStructureIngestResultRead.model_validate(serialize_market_structure_ingest_result(result))


__all__ = [
    "market_structure_health_job_accepted_read",
    "market_structure_ingest_result_read",
    "market_structure_plugin_read",
    "market_structure_snapshot_read",
    "market_structure_source_health_read",
    "market_structure_source_job_accepted_read",
    "market_structure_source_read",
    "market_structure_webhook_registration_read",
]
