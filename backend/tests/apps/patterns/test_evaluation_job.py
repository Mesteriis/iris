from __future__ import annotations

from datetime import timedelta

import pytest
from redis import Redis
from sqlalchemy import delete

from src.apps.market_data.domain import utc_now
from src.apps.patterns.domain.registry import sync_pattern_metadata
from src.apps.patterns.models import PatternRegistry
from src.apps.patterns.models import PatternStatistic
from src.apps.patterns.task_services import PatternEvaluationService
from src.apps.signals.models import SignalHistory
from src.core.db.uow import SessionUnitOfWork
from src.runtime.streams.publisher import flush_publisher


@pytest.mark.asyncio
async def test_pattern_evaluation_job_disables_weak_patterns_and_emits_events(
    async_db_session,
    db_session,
    seeded_market,
    settings,
) -> None:
    sync_pattern_metadata(db_session)
    db_session.execute(delete(SignalHistory))
    db_session.execute(delete(PatternStatistic))
    db_session.commit()

    coin_id = int(seeded_market["SOLUSD_EVT"]["coin_id"])
    start = utc_now() - timedelta(days=7)
    db_session.add_all(
        [
            SignalHistory(
                coin_id=coin_id,
                timeframe=15,
                signal_type="pattern_bull_flag",
                confidence=0.7,
                market_regime="bull_trend",
                candle_timestamp=start + timedelta(minutes=15 * index),
                profit_after_24h=-0.04,
                profit_after_72h=-0.05,
                maximum_drawdown=-0.08,
                result_return=-0.05,
                result_drawdown=-0.08,
                evaluated_at=start + timedelta(minutes=15 * index, hours=24),
            )
            for index in range(25)
        ]
    )
    db_session.commit()

    async with SessionUnitOfWork(async_db_session) as uow:
        result = await PatternEvaluationService(uow).run()
    assert result["status"] == "ok"
    assert result["statistics"]["rolling_window"] == 200
    assert flush_publisher(timeout=5.0)

    db_session.expire_all()
    registry_row = db_session.get(PatternRegistry, "bull_flag")
    stat_row = db_session.get(PatternStatistic, ("bull_flag", 15, "all"))
    assert registry_row is not None
    assert registry_row.lifecycle_state == "DISABLED"
    assert stat_row is not None
    assert stat_row.enabled is False

    client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        event_types = [fields["event_type"] for _, fields in client.xrange(settings.event_stream_name, "-", "+")]
        assert "pattern_disabled" in event_types
    finally:
        client.close()
