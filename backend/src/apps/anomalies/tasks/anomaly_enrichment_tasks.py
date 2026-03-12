from __future__ import annotations

from datetime import datetime

from src.apps.anomalies.services import AnomalyService
from src.apps.market_data.domain import ensure_utc
from src.core.db.session import AsyncSessionLocal
from src.runtime.orchestration.broker import analytics_broker
from src.runtime.orchestration.locks import async_redis_task_lock

ANOMALY_ENRICHMENT_LOCK_TIMEOUT_SECONDS = 300
SECTOR_SCAN_LOCK_TIMEOUT_SECONDS = 300
MARKET_STRUCTURE_SCAN_LOCK_TIMEOUT_SECONDS = 300


@analytics_broker.task
async def anomaly_enrichment_job(anomaly_id: int) -> dict[str, object]:
    async with async_redis_task_lock(
        f"iris:tasklock:anomaly_enrichment:{int(anomaly_id)}",
        timeout=ANOMALY_ENRICHMENT_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "anomaly_enrichment_in_progress", "anomaly_id": int(anomaly_id)}
        async with AsyncSessionLocal() as db:
            service = AnomalyService(db)
            return await service.enrich_anomaly(int(anomaly_id))


@analytics_broker.task
async def sector_anomaly_scan(
    trigger_coin_id: int,
    timeframe: int,
    timestamp: str,
    trigger_anomaly_id: int | None = None,
) -> dict[str, object]:
    normalized_timestamp = ensure_utc(datetime.fromisoformat(timestamp))
    lock_key = (
        f"iris:tasklock:sector_anomaly_scan:{int(trigger_coin_id)}:{int(timeframe)}:"
        f"{normalized_timestamp.isoformat()}"
    )
    async with async_redis_task_lock(lock_key, timeout=SECTOR_SCAN_LOCK_TIMEOUT_SECONDS) as acquired:
        if not acquired:
            return {
                "status": "skipped",
                "reason": "sector_anomaly_scan_in_progress",
                "trigger_coin_id": int(trigger_coin_id),
                "timeframe": int(timeframe),
            }
        async with AsyncSessionLocal() as db:
            service = AnomalyService(db)
            return await service.scan_sector_synchrony(
                trigger_coin_id=int(trigger_coin_id),
                timeframe=int(timeframe),
                timestamp=normalized_timestamp,
                trigger_anomaly_id=trigger_anomaly_id,
            )


@analytics_broker.task
async def market_structure_anomaly_scan(
    trigger_coin_id: int,
    timeframe: int,
    timestamp: str,
    trigger_anomaly_id: int | None = None,
) -> dict[str, object]:
    normalized_timestamp = ensure_utc(datetime.fromisoformat(timestamp))
    lock_key = (
        f"iris:tasklock:market_structure_anomaly_scan:{int(trigger_coin_id)}:{int(timeframe)}:"
        f"{normalized_timestamp.isoformat()}"
    )
    async with async_redis_task_lock(lock_key, timeout=MARKET_STRUCTURE_SCAN_LOCK_TIMEOUT_SECONDS) as acquired:
        if not acquired:
            return {
                "status": "skipped",
                "reason": "market_structure_anomaly_scan_in_progress",
                "trigger_coin_id": int(trigger_coin_id),
                "timeframe": int(timeframe),
            }
        async with AsyncSessionLocal() as db:
            service = AnomalyService(db)
            return await service.scan_market_structure(
                trigger_coin_id=int(trigger_coin_id),
                timeframe=int(timeframe),
                timestamp=normalized_timestamp,
                trigger_anomaly_id=trigger_anomaly_id,
            )
