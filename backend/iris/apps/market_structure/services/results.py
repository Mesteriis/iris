from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class MarketStructureRefreshHealthResult:
    status: str
    sources: int
    changed: int


@dataclass(slots=True, frozen=True)
class MarketStructurePollSourceResult:
    status: str
    source_id: int
    plugin_name: str | None = None
    reason: str | None = None
    fetched: int = 0
    created: int = 0
    cursor: dict[str, Any] | None = None
    error: str | None = None
    consecutive_failures: int = 0
    backoff_until: str | None = None
    quarantined: bool = False
    quarantined_at: str | None = None
    quarantine_reason: str | None = None


@dataclass(slots=True, frozen=True)
class MarketStructurePollBatchResult:
    status: str
    sources: int
    items: tuple[MarketStructurePollSourceResult, ...]
    created: int


@dataclass(slots=True, frozen=True)
class MarketStructureIngestResult:
    status: str
    source_id: int
    plugin_name: str | None = None
    created: int = 0
    reason: str | None = None


def serialize_market_structure_refresh_result(result: MarketStructureRefreshHealthResult) -> dict[str, object]:
    return {
        "status": result.status,
        "sources": result.sources,
        "changed": result.changed,
    }


def serialize_market_structure_poll_source_result(result: MarketStructurePollSourceResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": result.status,
        "source_id": result.source_id,
    }
    if result.plugin_name is not None:
        payload["plugin_name"] = result.plugin_name
    if result.reason is not None:
        payload["reason"] = result.reason
    if result.status == "ok":
        payload["fetched"] = result.fetched
        payload["created"] = result.created
        payload["cursor"] = dict(result.cursor or {})
    if result.error is not None:
        payload["error"] = result.error
    if result.consecutive_failures:
        payload["consecutive_failures"] = result.consecutive_failures
    if result.backoff_until is not None:
        payload["backoff_until"] = result.backoff_until
    if result.quarantined:
        payload["quarantined"] = True
    if result.quarantined_at is not None:
        payload["quarantined_at"] = result.quarantined_at
    if result.quarantine_reason is not None:
        payload["quarantine_reason"] = result.quarantine_reason
    return payload


def serialize_market_structure_poll_batch_result(result: MarketStructurePollBatchResult) -> dict[str, object]:
    return {
        "status": result.status,
        "sources": result.sources,
        "items": [serialize_market_structure_poll_source_result(item) for item in result.items],
        "created": result.created,
    }


def serialize_market_structure_ingest_result(result: MarketStructureIngestResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": result.status,
        "source_id": result.source_id,
    }
    if result.plugin_name is not None:
        payload["plugin_name"] = result.plugin_name
    if result.created:
        payload["created"] = result.created
    if result.reason is not None:
        payload["reason"] = result.reason
    return payload


__all__ = [
    "MarketStructureIngestResult",
    "MarketStructurePollBatchResult",
    "MarketStructurePollSourceResult",
    "MarketStructureRefreshHealthResult",
    "serialize_market_structure_ingest_result",
    "serialize_market_structure_poll_batch_result",
    "serialize_market_structure_poll_source_result",
    "serialize_market_structure_refresh_result",
]
