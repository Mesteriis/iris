import importlib
from datetime import UTC, datetime, timezone

import pytest
from src.apps.indicators.repositories import IndicatorMetricsRepository
from src.apps.indicators.services import AnalysisSchedulerService
from src.apps.patterns.domain.scheduler import (
    analysis_interval,
    analysis_priority_for_bucket,
    should_request_analysis,
)
from src.core.db.uow import SessionUnitOfWork

from tests.fusion_support import create_test_coin, upsert_coin_metrics


@pytest.mark.asyncio
async def test_scheduler_helpers_update_analysis_snapshot(async_db_session, db_session) -> None:
    timestamp = datetime(2026, 3, 12, 10, 15, tzinfo=UTC)
    assert analysis_priority_for_bucket("HOT") == 100
    assert analysis_priority_for_bucket("unknown") == 5
    assert analysis_interval("HOT", 15).total_seconds() == 900
    assert analysis_interval("WARM", 15).total_seconds() == 1800
    assert analysis_interval("COLD", 15).total_seconds() == 9000
    assert analysis_interval(None, 15).total_seconds() == 3600
    assert should_request_analysis(
        timeframe=15,
        timestamp=timestamp,
        activity_bucket="HOT",
        last_analysis_at=None,
    ) is True
    assert should_request_analysis(
        timeframe=15,
        timestamp=timestamp,
        activity_bucket="WARM",
        last_analysis_at=datetime(2026, 3, 12, 10, 10, tzinfo=UTC),
    ) is False

    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    metrics = upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=15)
    module = importlib.import_module("src.apps.patterns.domain.scheduler")
    assert not hasattr(module, "mark_analysis_requested")
    assert not hasattr(module, "get_activity_snapshot")

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await AnalysisSchedulerService(uow).evaluate_indicator_update(
            coin_id=int(coin.id),
            timeframe=15,
            timestamp=timestamp,
            activity_bucket_hint="HOT",
        )
        missing = await AnalysisSchedulerService(uow).evaluate_indicator_update(
            coin_id=999999,
            timeframe=15,
            timestamp=timestamp,
            activity_bucket_hint="HOT",
        )
        await uow.commit()

    snapshot = await IndicatorMetricsRepository(async_db_session).get_by_coin_id(int(coin.id))
    assert result.should_publish is True
    assert result.state_updated is True
    assert missing.should_publish is True
    assert missing.state_updated is False
    assert snapshot is not None
    assert snapshot.id == metrics.id
    assert snapshot.last_analysis_at == timestamp
