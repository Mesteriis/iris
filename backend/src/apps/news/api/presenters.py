from __future__ import annotations

from typing import Any

from src.apps.news.api.contracts import (
    NewsItemRead,
    NewsPluginRead,
    NewsSourceJobAcceptedRead,
    NewsSourceRead,
    TelegramBulkSubscribeRead,
)
from src.core.http.operations import OperationStatusResponse
from src.core.db.persistence import thaw_json_value


def news_plugin_read(item: Any) -> NewsPluginRead:
    return NewsPluginRead.model_validate(
        {
            "name": item.name,
            "display_name": item.display_name,
            "description": item.description,
            "auth_mode": item.auth_mode,
            "supported": bool(item.supported),
            "supports_user_identity": bool(item.supports_user_identity),
            "required_credentials": list(item.required_credentials),
            "required_settings": list(item.required_settings),
            "runtime_dependencies": list(item.runtime_dependencies),
            "unsupported_reason": item.unsupported_reason,
        }
    )


def news_source_read(item: Any) -> NewsSourceRead:
    if isinstance(item, NewsSourceRead):
        return item
    return NewsSourceRead.model_validate(
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
            "last_error": item.last_error,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }
    )


def news_item_read(item: Any) -> NewsItemRead:
    return NewsItemRead.model_validate(
        {
            "id": int(item.id),
            "source_id": int(item.source_id),
            "plugin_name": item.plugin_name,
            "external_id": item.external_id,
            "published_at": item.published_at,
            "author_handle": item.author_handle,
            "channel_name": item.channel_name,
            "title": item.title,
            "content_text": item.content_text,
            "url": item.url,
            "symbol_hints": list(item.symbol_hints),
            "payload_json": thaw_json_value(item.payload_json),
            "normalization_status": item.normalization_status,
            "normalized_payload_json": thaw_json_value(item.normalized_payload_json),
            "normalized_at": item.normalized_at,
            "sentiment_score": item.sentiment_score,
            "relevance_score": item.relevance_score,
            "links": [
                {
                    "coin_id": int(link.coin_id),
                    "coin_symbol": link.coin_symbol,
                    "matched_symbol": link.matched_symbol,
                    "link_type": link.link_type,
                    "confidence": link.confidence,
                }
                for link in item.links
            ],
        }
    )


def telegram_bulk_subscribe_read(item: Any) -> TelegramBulkSubscribeRead:
    if isinstance(item, TelegramBulkSubscribeRead):
        return item
    return TelegramBulkSubscribeRead.model_validate(item)


def news_source_job_accepted_read(
    *,
    operation: OperationStatusResponse,
    source_id: int,
    limit: int,
) -> NewsSourceJobAcceptedRead:
    return NewsSourceJobAcceptedRead.model_validate(
        {
            "operation_id": operation.operation_id,
            "accepted_at": operation.accepted_at,
            "correlation_id": operation.correlation_id,
            "source_id": int(source_id),
            "limit": int(limit),
        }
    )


__all__ = [
    "news_item_read",
    "news_plugin_read",
    "news_source_job_accepted_read",
    "news_source_read",
    "telegram_bulk_subscribe_read",
]
