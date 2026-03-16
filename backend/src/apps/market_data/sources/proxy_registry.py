from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from time import perf_counter

import httpx

from src.apps.market_data.domain import utc_now
from src.core.settings import get_settings

LOGGER = logging.getLogger(__name__)
EARLIEST_UTC = datetime.min.replace(tzinfo=UTC)


def _serialize_timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@dataclass(slots=True)
class ProxyRecord:
    proxy_url: str
    source_urls: list[str] = field(default_factory=list)
    imported_at: datetime = field(default_factory=utc_now)
    last_checked_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    cooldown_until: datetime | None = None
    last_error: str | None = None
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    average_latency_ms: float | None = None
    rating: float = 0.2

    @property
    def total_checks(self) -> int:
        return self.success_count + self.failure_count

    def is_available(self, *, now: datetime, min_rating: float) -> bool:
        if self.cooldown_until is not None and self.cooldown_until > now:
            return False
        return self.rating >= min_rating

    def to_dict(self) -> dict[str, object]:
        return {
            "proxy_url": self.proxy_url,
            "source_urls": sorted(set(self.source_urls)),
            "imported_at": _serialize_timestamp(self.imported_at),
            "last_checked_at": _serialize_timestamp(self.last_checked_at),
            "last_success_at": _serialize_timestamp(self.last_success_at),
            "last_failure_at": _serialize_timestamp(self.last_failure_at),
            "cooldown_until": _serialize_timestamp(self.cooldown_until),
            "last_error": self.last_error,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "consecutive_failures": self.consecutive_failures,
            "average_latency_ms": self.average_latency_ms,
            "rating": self.rating,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> ProxyRecord | None:
        proxy_url = str(payload.get("proxy_url") or "").strip()
        if not proxy_url:
            return None
        source_urls_raw = payload.get("source_urls")
        source_urls = [str(item).strip() for item in source_urls_raw if str(item).strip()] if isinstance(source_urls_raw, list) else []
        return cls(
            proxy_url=proxy_url,
            source_urls=source_urls,
            imported_at=_parse_timestamp(str(payload.get("imported_at") or "")) or utc_now(),
            last_checked_at=_parse_timestamp(str(payload.get("last_checked_at") or "")),
            last_success_at=_parse_timestamp(str(payload.get("last_success_at") or "")),
            last_failure_at=_parse_timestamp(str(payload.get("last_failure_at") or "")),
            cooldown_until=_parse_timestamp(str(payload.get("cooldown_until") or "")),
            last_error=str(payload.get("last_error")) if payload.get("last_error") not in {None, ""} else None,
            success_count=max(int(payload.get("success_count") or 0), 0),
            failure_count=max(int(payload.get("failure_count") or 0), 0),
            consecutive_failures=max(int(payload.get("consecutive_failures") or 0), 0),
            average_latency_ms=float(payload["average_latency_ms"]) if payload.get("average_latency_ms") is not None else None,
            rating=max(float(payload.get("rating") or 0.0), 0.0),
        )


class FreeProxyRegistry:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._records: dict[str, ProxyRecord] = {}
        self._lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._selection_cursor = 0
        self._started = False
        self._dirty = False
        self._last_persist_at: datetime | None = None
        self._stop_event = asyncio.Event()
        self._refresh_task: asyncio.Task[None] | None = None
        self._import_client: httpx.AsyncClient | None = None

    @property
    def storage_path(self) -> Path:
        return Path(self.settings.runtime_data_dir) / "market_data" / "free_http_proxy_registry.json"

    async def start(self) -> None:
        async with self._start_lock:
            if self._started:
                return
            await self._load_from_disk()
            self._stop_event = asyncio.Event()
            self._import_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.settings.free_proxy_pool_request_timeout_seconds),
                headers={
                    "User-Agent": "IRIS/0.1 proxy-registry",
                    "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
                },
                follow_redirects=True,
                trust_env=False,
            )
            if self.settings.free_proxy_pool_enabled:
                self._refresh_task = asyncio.create_task(
                    self._run_loop(),
                    name="iris-free-proxy-registry",
                )
            self._started = True

    async def stop(self) -> None:
        async with self._start_lock:
            if not self._started:
                return
            self._stop_event.set()
            if self._refresh_task is not None:
                self._refresh_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._refresh_task
            await self._persist_to_disk()
            if self._import_client is not None:
                await self._import_client.aclose()
            self._refresh_task = None
            self._import_client = None
            self._started = False

    async def has_available_proxy(self, *, min_rating: float | None = None) -> bool:
        return bool(await self.get_best_proxies(limit=1, min_rating=min_rating))

    async def get_best_proxies(self, *, limit: int, min_rating: float | None = None) -> list[str]:
        effective_min_rating = min_rating if min_rating is not None else self.settings.free_proxy_pool_min_rating
        async with self._lock:
            healthy = self._healthy_records_locked(min_rating=effective_min_rating)
            if not healthy:
                return []
            window_size = min(len(healthy), max(limit * 3, limit))
            window = healthy[:window_size]
            start = self._selection_cursor % len(window)
            selected = [window[(start + offset) % len(window)].proxy_url for offset in range(min(limit, len(window)))]
            self._selection_cursor = (start + 1) % len(window)
            return selected

    async def record_success(self, proxy_url: str, *, latency_ms: float) -> None:
        async with self._lock:
            record = self._records.get(proxy_url)
            if record is None:
                return
            now = utc_now()
            record.last_checked_at = now
            record.last_success_at = now
            record.last_error = None
            record.cooldown_until = None
            record.success_count += 1
            record.consecutive_failures = 0
            if record.average_latency_ms is None:
                record.average_latency_ms = round(latency_ms, 2)
            else:
                record.average_latency_ms = round((record.average_latency_ms * 0.7) + (latency_ms * 0.3), 2)
            record.rating = self._calculate_rating(record, now=now)
            self._dirty = True

    async def record_failure(
        self,
        proxy_url: str,
        *,
        reason: str,
        cooldown_seconds: int = 180,
    ) -> None:
        async with self._lock:
            record = self._records.get(proxy_url)
            if record is None:
                return
            now = utc_now()
            record.last_checked_at = now
            record.last_failure_at = now
            record.last_error = reason
            record.failure_count += 1
            record.consecutive_failures += 1
            record.cooldown_until = now + timedelta(seconds=max(cooldown_seconds, 1))
            record.rating = self._calculate_rating(record, now=now)
            self._dirty = True

    async def record_rate_limited(self, proxy_url: str, *, retry_after_seconds: int) -> None:
        await self.record_failure(
            proxy_url,
            reason="proxy path rate limited",
            cooldown_seconds=max(retry_after_seconds, 1),
        )

    async def _run_loop(self) -> None:
        next_refresh = utc_now()
        while not self._stop_event.is_set():
            try:
                now = utc_now()
                if now >= next_refresh:
                    await self.refresh_once()
                    next_refresh = now + timedelta(seconds=max(self.settings.free_proxy_pool_refresh_interval_seconds, 30))
                await self._persist_if_due()
                wait_seconds = min(
                    max((next_refresh - utc_now()).total_seconds(), 1.0),
                    max(float(self.settings.free_proxy_pool_persist_interval_seconds), 1.0),
                )
                await asyncio.wait_for(self._stop_event.wait(), timeout=wait_seconds)
            except TimeoutError:
                continue
            except Exception:  # pragma: no cover - defensive runtime shield
                LOGGER.exception("Free proxy registry refresh loop failed.")
                await asyncio.sleep(5.0)

    async def refresh_once(self) -> None:
        candidates = await self._fetch_proxy_candidates()
        async with self._lock:
            now = utc_now()
            for proxy_url, source_url in candidates:
                record = self._records.get(proxy_url)
                if record is None:
                    record = ProxyRecord(proxy_url=proxy_url, imported_at=now)
                    self._records[proxy_url] = record
                if source_url not in record.source_urls:
                    record.source_urls.append(source_url)
                record.imported_at = now
            probe_targets = self._probe_targets_locked()
        if probe_targets:
            await asyncio.gather(*(self._probe_proxy(proxy_url) for proxy_url in probe_targets), return_exceptions=True)
        async with self._lock:
            self._prune_records_locked()
            self._dirty = True

    async def _fetch_proxy_candidates(self) -> set[tuple[str, str]]:
        if not self.settings.free_proxy_pool_enabled:
            return set()
        client = self._import_client
        if client is None:
            return set()
        tasks = [self._fetch_source_candidates(client, source_url) for source_url in self.settings.free_proxy_pool_source_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        candidates: set[tuple[str, str]] = set()
        for source_url, result in zip(self.settings.free_proxy_pool_source_urls, results, strict=False):
            if isinstance(result, Exception):
                LOGGER.warning("Failed to import proxy list from %s: %s", source_url, result)
                continue
            for proxy_url in result:
                candidates.add((proxy_url, source_url))
        return candidates

    async def _fetch_source_candidates(self, client: httpx.AsyncClient, source_url: str) -> set[str]:
        response = await client.get(source_url)
        response.raise_for_status()
        content = response.text.strip()
        if not content:
            return set()
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return self._parse_proxy_lines(content.splitlines())
        return self._parse_proxy_payload(payload)

    def _parse_proxy_payload(self, payload: object) -> set[str]:
        if isinstance(payload, list):
            normalized: set[str] = set()
            for item in payload:
                normalized.update(self._parse_proxy_payload(item))
            return normalized
        if isinstance(payload, dict):
            normalized: set[str] = set()
            if "proxy" in payload:
                candidate = self._normalize_proxy_url(str(payload["proxy"]))
                if candidate is not None:
                    normalized.add(candidate)
            elif "url" in payload:
                candidate = self._normalize_proxy_url(str(payload["url"]))
                if candidate is not None:
                    normalized.add(candidate)
            elif "ip" in payload and "port" in payload:
                candidate = self._normalize_proxy_url(f"{payload['ip']}:{payload['port']}")
                if candidate is not None:
                    normalized.add(candidate)
            return normalized
        if isinstance(payload, str):
            candidate = self._normalize_proxy_url(payload)
            return {candidate} if candidate is not None else set()
        return set()

    def _parse_proxy_lines(self, lines: list[str]) -> set[str]:
        normalized: set[str] = set()
        for line in lines:
            candidate = self._normalize_proxy_url(line)
            if candidate is not None:
                normalized.add(candidate)
        return normalized

    def _normalize_proxy_url(self, raw: str) -> str | None:
        candidate = raw.strip()
        if not candidate or candidate.startswith("#"):
            return None
        if "://" not in candidate:
            candidate = f"http://{candidate}"
        try:
            parsed = httpx.URL(candidate)
        except httpx.InvalidURL:
            return None
        if parsed.scheme not in {"http", "https"} or not parsed.host:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return f"{parsed.scheme}://{parsed.host}:{port}"

    def _probe_targets_locked(self) -> list[str]:
        records = sorted(
            self._records.values(),
            key=lambda record: (
                record.last_checked_at is not None,
                record.last_checked_at or EARLIEST_UTC,
                -record.rating,
            ),
        )
        batch_size = max(self.settings.free_proxy_pool_validation_batch_size, 1)
        return [record.proxy_url for record in records[:batch_size]]

    async def _probe_proxy(self, proxy_url: str) -> None:
        timeout = httpx.Timeout(self.settings.free_proxy_pool_request_timeout_seconds)
        client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": "IRIS/0.1 proxy-probe",
                "Accept": "text/plain,*/*;q=0.5",
            },
            follow_redirects=True,
            proxy=proxy_url,
            trust_env=False,
        )
        response_status_code: int | None = None
        try:
            for probe_url in self.settings.free_proxy_pool_probe_urls:
                started_at = perf_counter()
                response = await client.get(probe_url)
                response_status_code = response.status_code
                latency_ms = (perf_counter() - started_at) * 1000
                if 200 <= response.status_code < 400:
                    await self.record_success(proxy_url, latency_ms=latency_ms)
                    return
            await self.record_failure(
                proxy_url,
                reason=f"probe returned {response_status_code or 'unknown'}",
                cooldown_seconds=180,
            )
        except httpx.HTTPError as exc:
            await self.record_failure(proxy_url, reason=f"probe error: {exc}", cooldown_seconds=300)
        finally:
            await client.aclose()

    async def _persist_if_due(self) -> None:
        if not self._dirty:
            return
        now = utc_now()
        if self._last_persist_at is None:
            await self._persist_to_disk()
            return
        if (now - self._last_persist_at).total_seconds() >= max(self.settings.free_proxy_pool_persist_interval_seconds, 1):
            await self._persist_to_disk()

    async def _load_from_disk(self) -> None:
        path = self.storage_path
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            LOGGER.warning("Failed to load proxy registry cache from %s.", path)
            return
        proxies = payload.get("proxies") if isinstance(payload, dict) else None
        if not isinstance(proxies, list):
            return
        async with self._lock:
            self._records.clear()
            for item in proxies:
                if not isinstance(item, dict):
                    continue
                record = ProxyRecord.from_dict(item)
                if record is not None:
                    self._records[record.proxy_url] = record

    async def _persist_to_disk(self) -> None:
        async with self._lock:
            payload = {
                "version": 1,
                "generated_at": _serialize_timestamp(utc_now()),
                "proxy_count": len(self._records),
                "proxies": [record.to_dict() for record in self._sorted_records_locked()],
            }
            self._dirty = False
        path = self.storage_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        self._last_persist_at = utc_now()

    def _healthy_records_locked(self, *, min_rating: float) -> list[ProxyRecord]:
        now = utc_now()
        return [record for record in self._sorted_records_locked() if record.is_available(now=now, min_rating=min_rating)]

    def _sorted_records_locked(self) -> list[ProxyRecord]:
        now = utc_now()
        return sorted(
            self._records.values(),
            key=lambda record: (
                record.cooldown_until is None or record.cooldown_until <= now,
                record.rating,
                record.last_success_at or EARLIEST_UTC,
                -(record.average_latency_ms or 10_000.0),
            ),
            reverse=True,
        )

    def _prune_records_locked(self) -> None:
        max_entries = max(self.settings.free_proxy_pool_max_entries, 1)
        sorted_records = self._sorted_records_locked()
        keep = {record.proxy_url for record in sorted_records[:max_entries]}
        self._records = {proxy_url: record for proxy_url, record in self._records.items() if proxy_url in keep}

    def _calculate_rating(self, record: ProxyRecord, *, now: datetime) -> float:
        checks = max(record.total_checks, 1)
        success_rate = record.success_count / checks
        latency_score = 0.4
        if record.average_latency_ms is not None:
            latency_score = max(0.05, 1.0 - min(record.average_latency_ms, 4000.0) / 4000.0)
        freshness_score = 0.2
        if record.last_success_at is not None:
            minutes_since_success = max((now - record.last_success_at).total_seconds() / 60.0, 0.0)
            freshness_score = max(0.05, 1.0 - min(minutes_since_success, 720.0) / 720.0)
        failure_penalty = min(record.consecutive_failures * 0.12, 0.6)
        cooldown_penalty = 0.25 if record.cooldown_until is not None and record.cooldown_until > now else 0.0
        return round(max((success_rate * 0.55) + (latency_score * 0.25) + (freshness_score * 0.20) - failure_penalty - cooldown_penalty, 0.0), 4)


_proxy_registry: FreeProxyRegistry | None = None
_proxy_registry_lock = Lock()


def get_free_proxy_registry() -> FreeProxyRegistry:
    global _proxy_registry
    if _proxy_registry is None:
        with _proxy_registry_lock:
            if _proxy_registry is None:
                _proxy_registry = FreeProxyRegistry()
    return _proxy_registry


__all__ = ["FreeProxyRegistry", "ProxyRecord", "get_free_proxy_registry"]
