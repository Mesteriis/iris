from datetime import timedelta

import pytest
from iris.apps.market_data.domain import utc_now
from iris.apps.signals.backtest_support import clamp_backtest_value, serialize_backtest_group, sharpe_ratio
from iris.apps.signals.models import SignalHistory
from iris.apps.signals.query_services import SignalQueryService

from tests.factories.signals import SignalHistorySeedFactory
from tests.fusion_support import create_test_coin


def test_backtest_math_helpers_cover_clamp_sharpe_and_empty_groups() -> None:
    assert clamp_backtest_value(-1.0, 0.0, 1.0) == 0.0
    assert clamp_backtest_value(2.0, 0.0, 1.0) == 1.0
    assert clamp_backtest_value(0.4, 0.0, 1.0) == 0.4

    assert sharpe_ratio([1.0]) == 0.0
    assert sharpe_ratio([2.0, 2.0, 2.0]) == 0.0
    assert sharpe_ratio([0.01, 0.03, 0.05]) > 0

    empty = serialize_backtest_group(symbol=None, signal_type="pattern_bull_flag", timeframe=15, points=[])
    assert empty == {
        "symbol": None,
        "signal_type": "pattern_bull_flag",
        "timeframe": 15,
        "sample_size": 0,
        "coin_count": 0,
        "win_rate": 0.0,
        "roi": 0,
        "avg_return": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
        "avg_confidence": 0.0,
        "last_evaluated_at": None,
    }


@pytest.mark.asyncio
async def test_backtest_queries_group_and_filter_signal_history(async_db_session, db_session) -> None:
    btc = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    eth = create_test_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test")
    now = utc_now()

    winning_seed = SignalHistorySeedFactory.build(
        timeframe=15,
        signal_type="pattern_bull_flag",
        confidence=0.82,
        market_regime="bull_trend",
        candle_timestamp=now - timedelta(days=2),
        result_return=0.05,
        result_drawdown=-0.02,
        evaluated_at=now - timedelta(days=1),
    )
    follow_up_seed = SignalHistorySeedFactory.build(
        timeframe=15,
        signal_type="pattern_bull_flag",
        confidence=0.78,
        market_regime="bull_trend",
        candle_timestamp=now - timedelta(days=3),
        result_return=0.03,
        result_drawdown=-0.01,
        evaluated_at=now - timedelta(days=1, hours=4),
    )
    failed_seed = SignalHistorySeedFactory.build(
        timeframe=60,
        signal_type="golden_cross",
        confidence=0.74,
        market_regime="sideways_range",
        candle_timestamp=now - timedelta(days=1),
        result_return=-0.02,
        result_drawdown=-0.03,
        evaluated_at=now - timedelta(hours=12),
    )

    db_session.add_all(
        [
            SignalHistory(coin_id=int(btc.id), **winning_seed.__dict__),
            SignalHistory(coin_id=int(btc.id), **follow_up_seed.__dict__),
            SignalHistory(coin_id=int(eth.id), **failed_seed.__dict__),
        ]
    )
    db_session.commit()

    query_service = SignalQueryService(async_db_session)

    rows = await query_service.list_backtests(
        symbol="BTCUSD_EVT",
        timeframe=15,
        signal_type="pattern_bull_flag",
        lookback_days=30,
        limit=10,
    )
    assert len(rows) == 1
    assert rows[0].symbol == "BTCUSD_EVT"
    assert rows[0].signal_type == "pattern_bull_flag"
    assert rows[0].timeframe == 15
    assert rows[0].sample_size == 2
    assert rows[0].coin_count == 1
    assert rows[0].win_rate == 1.0
    assert rows[0].roi == 0.08
    assert rows[0].avg_return == 0.04
    assert rows[0].sharpe_ratio == pytest.approx(4.0)
    assert rows[0].max_drawdown == -0.02
    assert rows[0].avg_confidence == 0.8
    assert rows[0].last_evaluated_at == max(now - timedelta(days=1), now - timedelta(days=1, hours=4))

    top_rows = await query_service.list_top_backtests(timeframe=15, lookback_days=30, limit=10)
    assert top_rows[0].signal_type == "pattern_bull_flag"
    assert top_rows[0].timeframe == 15

    coin_payload = await query_service.get_coin_backtests(
        "BTCUSD_EVT",
        timeframe=15,
        signal_type="pattern_bull_flag",
        lookback_days=30,
        limit=10,
    )
    assert coin_payload is not None
    assert coin_payload.coin_id == int(btc.id)
    assert coin_payload.items[0].signal_type == "pattern_bull_flag"

    unscoped_rows = await query_service.list_backtests(
        symbol="BTCUSD_EVT",
        signal_type="pattern_bull_flag",
        lookback_days=30,
        limit=10,
    )
    assert unscoped_rows[0].timeframe == 15

    assert await query_service.get_coin_backtests("MISSING_EVT") is None
