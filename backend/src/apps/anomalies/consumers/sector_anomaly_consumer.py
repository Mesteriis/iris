from src.apps.anomalies.constants import (
    ANOMALY_SOURCE_MARKET_STRUCTURE_SCAN,
    ANOMALY_SOURCE_SECTOR_SCAN,
    ANOMALY_TYPE_CROSS_ASSET_SYNCHRONOUS_MOVE,
)
from src.apps.anomalies.tasks.anomaly_enrichment_tasks import (
    anomaly_enrichment_job,
    market_structure_anomaly_scan,
    sector_anomaly_scan,
)
from src.runtime.orchestration.dispatcher import enqueue_task
from src.runtime.streams.types import IrisEvent


class SectorAnomalyConsumer:
    def __init__(self, *, high_severity_levels: set[str] | None = None) -> None:
        self._high_severity_levels = high_severity_levels or {"high", "critical"}

    async def handle_event(self, event: IrisEvent) -> None:
        if event.event_type != "anomaly_detected":
            return
        anomaly_id = int(event.payload.get("anomaly_id") or 0)
        if anomaly_id <= 0:
            return

        await enqueue_task(anomaly_enrichment_job, anomaly_id=anomaly_id)

        anomaly_type = str(event.payload.get("type") or "")
        severity = str(event.payload.get("severity") or "")
        source_pipeline = str(event.payload.get("source_pipeline") or "")
        if anomaly_type == ANOMALY_TYPE_CROSS_ASSET_SYNCHRONOUS_MOVE:
            return
        if source_pipeline in {ANOMALY_SOURCE_SECTOR_SCAN, ANOMALY_SOURCE_MARKET_STRUCTURE_SCAN}:
            return
        if severity not in self._high_severity_levels:
            return

        await enqueue_task(
            sector_anomaly_scan,
            trigger_coin_id=event.coin_id,
            timeframe=event.timeframe,
            timestamp=event.timestamp.isoformat(),
            trigger_anomaly_id=anomaly_id,
        )
        await enqueue_task(
            market_structure_anomaly_scan,
            trigger_coin_id=event.coin_id,
            timeframe=event.timeframe,
            timestamp=event.timestamp.isoformat(),
            trigger_anomaly_id=anomaly_id,
        )
