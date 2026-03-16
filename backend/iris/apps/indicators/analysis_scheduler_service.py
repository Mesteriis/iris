from datetime import datetime

from iris.apps.indicators.repositories import IndicatorMetricsRepository
from iris.apps.indicators.results import AnalysisScheduleResult
from iris.apps.market_data.domain import ensure_utc
from iris.apps.patterns.domain.scheduler import should_request_analysis
from iris.core.db.uow import BaseAsyncUnitOfWork


class AnalysisSchedulerService:
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        self._metrics = IndicatorMetricsRepository(uow.session)

    async def evaluate_indicator_update(
        self,
        *,
        coin_id: int,
        timeframe: int,
        timestamp: datetime,
        activity_bucket_hint: str | None,
    ) -> AnalysisScheduleResult:
        normalized_timestamp = ensure_utc(timestamp)
        metrics = await self._metrics.get_by_coin_id(int(coin_id))
        activity_bucket = (
            str(activity_bucket_hint)
            if activity_bucket_hint is not None
            else (str(metrics.activity_bucket) if metrics is not None and metrics.activity_bucket is not None else None)
        )
        should_publish = should_request_analysis(
            timeframe=int(timeframe),
            timestamp=normalized_timestamp,
            activity_bucket=activity_bucket,
            last_analysis_at=metrics.last_analysis_at if metrics is not None else None,
        )
        if not should_publish:
            return AnalysisScheduleResult(
                should_publish=False,
                activity_bucket=activity_bucket,
                state_updated=False,
            )
        if metrics is None:
            return AnalysisScheduleResult(
                should_publish=True,
                activity_bucket=activity_bucket,
                state_updated=False,
            )
        metrics.last_analysis_at = normalized_timestamp
        return AnalysisScheduleResult(
            should_publish=True,
            activity_bucket=activity_bucket,
            state_updated=True,
        )


__all__ = ["AnalysisSchedulerService"]
