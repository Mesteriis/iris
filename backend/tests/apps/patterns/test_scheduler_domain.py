from __future__ import annotations

from datetime import datetime, timezone

from src.apps.patterns.domain.scheduler import (
    analysis_interval,
    analysis_priority_for_bucket,
    get_activity_snapshot,
    mark_analysis_requested,
    should_request_analysis,
)
from tests.fusion_support import create_test_coin, upsert_coin_metrics


def test_scheduler_helpers_update_analysis_snapshot(db_session) -> None:
    timestamp = datetime(2026, 3, 12, 10, 15, tzinfo=timezone.utc)
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
        last_analysis_at=datetime(2026, 3, 12, 10, 10, tzinfo=timezone.utc),
    ) is False

    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    metrics = upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=15)

    mark_analysis_requested(db_session, coin_id=int(coin.id), analysis_timestamp=timestamp)
    mark_analysis_requested(db_session, coin_id=999999, analysis_timestamp=timestamp)

    snapshot = get_activity_snapshot(db_session, coin_id=int(coin.id))
    assert snapshot is not None
    assert snapshot.id == metrics.id
    assert snapshot.last_analysis_at == timestamp
