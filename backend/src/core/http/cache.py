from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from typing import Literal

from fastapi import Request, Response, status
from fastapi.encoders import jsonable_encoder


@dataclass(frozen=True, slots=True)
class CachePolicy:
    visibility: Literal["public", "private"]
    max_age: int
    stale_while_revalidate: int | None = None
    must_revalidate: bool = False


PUBLIC_NEAR_REALTIME_CACHE = CachePolicy(visibility="public", max_age=15, stale_while_revalidate=30)
PRIVATE_NEAR_REALTIME_CACHE = CachePolicy(visibility="private", max_age=5, stale_while_revalidate=10)


def cache_not_modified_responses() -> dict[int, dict[str, object]]:
    return {
        status.HTTP_304_NOT_MODIFIED: {
            "description": "Cached analytical representation is still valid.",
        }
    }


def apply_conditional_cache(
    *,
    request: Request,
    response: Response,
    payload: object,
    policy: CachePolicy,
    generated_at: datetime | str | None,
    staleness_ms: int | None = None,
) -> Response | None:
    etag = _build_etag(payload)
    last_modified = _resolve_last_modified(generated_at=generated_at, staleness_ms=staleness_ms)
    headers = {
        "Cache-Control": _build_cache_control(policy),
        "ETag": etag,
        "Vary": "Accept, If-None-Match",
    }
    if last_modified is not None:
        headers["Last-Modified"] = format_datetime(last_modified, usegmt=True)
    for key, value in headers.items():
        response.headers[key] = value
    if _matches_etag(request.headers.get("if-none-match"), etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return None


def _build_cache_control(policy: CachePolicy) -> str:
    parts = [policy.visibility, f"max-age={int(policy.max_age)}"]
    if policy.stale_while_revalidate is not None:
        parts.append(f"stale-while-revalidate={int(policy.stale_while_revalidate)}")
    if policy.must_revalidate:
        parts.append("must-revalidate")
    return ", ".join(parts)


def _build_etag(payload: object) -> str:
    encoded = json.dumps(_etag_payload(payload), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]
    return f'W/"{digest}"'


def _etag_payload(payload: object) -> object:
    encoded = jsonable_encoder(payload)
    if isinstance(encoded, dict):
        return {
            key: value
            for key, value in encoded.items()
            if key not in {"generated_at", "staleness_ms"}
        }
    return encoded


def _resolve_last_modified(*, generated_at: datetime | str | None, staleness_ms: int | None) -> datetime | None:
    normalized_generated_at = _coerce_datetime(generated_at)
    if normalized_generated_at is None:
        return None
    if staleness_ms is None:
        return normalized_generated_at
    return normalized_generated_at - timedelta(milliseconds=max(int(staleness_ms), 0))


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)


def _matches_etag(header_value: str | None, etag: str) -> bool:
    if header_value is None:
        return False
    candidates = {candidate.strip() for candidate in header_value.split(",") if candidate.strip()}
    return "*" in candidates or etag in candidates


__all__ = [
    "CachePolicy",
    "PRIVATE_NEAR_REALTIME_CACHE",
    "PUBLIC_NEAR_REALTIME_CACHE",
    "apply_conditional_cache",
    "cache_not_modified_responses",
]
