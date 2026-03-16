from datetime import datetime

from src.apps.anomalies.results import AnomalyDetectionBatchResult, AnomalyEnrichmentResult
from src.apps.anomalies.services import AnomalyService
from src.apps.market_data.domain import ensure_utc
from src.core.db.uow import AsyncUnitOfWork
from src.runtime.orchestration.broker import analytics_broker
from src.runtime.orchestration.locks import async_redis_task_lock

ANOMALY_ENRICHMENT_LOCK_TIMEOUT_SECONDS = 300
SECTOR_SCAN_LOCK_TIMEOUT_SECONDS = 300
MARKET_STRUCTURE_SCAN_LOCK_TIMEOUT_SECONDS = 300


def _serialize_enrichment_result(result: AnomalyEnrichmentResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": result.status,
        "anomaly_id": int(result.anomaly_id),
        "portfolio_relevant": result.portfolio_relevant,
        "market_wide": result.market_wide,
    }
    if result.reason is not None:
        payload["reason"] = result.reason
    return payload


def _serialize_detection_result(result: AnomalyDetectionBatchResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": result.status,
        "created": int(result.created),
        "items": list(result.items),
    }
    if result.reason is not None:
        payload["reason"] = result.reason
    return payload


@analytics_broker.task
async def anomaly_enrichment_job(anomaly_id: int) -> dict[str, object]:
    async with async_redis_task_lock(
        f"iris:tasklock:anomaly_enrichment:{int(anomaly_id)}",
        timeout=ANOMALY_ENRICHMENT_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "anomaly_enrichment_in_progress", "anomaly_id": int(anomaly_id)}
        async with AsyncUnitOfWork() as uow:
            service = AnomalyService(uow)
            result = await service.enrich_anomaly(int(anomaly_id))
            await uow.commit()
            return _serialize_enrichment_result(result)


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
        async with AsyncUnitOfWork() as uow:
            service = AnomalyService(uow)
            result = await service.scan_sector_synchrony(
                trigger_coin_id=int(trigger_coin_id),
                timeframe=int(timeframe),
                timestamp=normalized_timestamp,
                trigger_anomaly_id=trigger_anomaly_id,
            )
            await uow.commit()
            return _serialize_detection_result(result)


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
        async with AsyncUnitOfWork() as uow:
            service = AnomalyService(uow)
            result = await service.scan_market_structure(
                trigger_coin_id=int(trigger_coin_id),
                timeframe=int(timeframe),
                timestamp=normalized_timestamp,
                trigger_anomaly_id=trigger_anomaly_id,
            )
            await uow.commit()
            return _serialize_detection_result(result)
