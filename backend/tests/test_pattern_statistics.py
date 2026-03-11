from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select

from app.models.pattern_statistic import PatternStatistic
from app.models.signal_history import SignalHistory
from app.patterns.statistics import refresh_pattern_statistics
from app.patterns.success import GLOBAL_MARKET_REGIME, PATTERN_SUCCESS_ROLLING_WINDOW
from app.patterns.registry import sync_pattern_metadata
from app.services.market_data import utc_now


def _history_row(
    *,
    coin_id: int,
    timeframe: int,
    signal_type: str,
    market_regime: str,
    candle_timestamp,
    result_return: float,
    result_drawdown: float,
) -> SignalHistory:
    return SignalHistory(
        coin_id=coin_id,
        timeframe=timeframe,
        signal_type=signal_type,
        confidence=0.75,
        market_regime=market_regime,
        candle_timestamp=candle_timestamp,
        profit_after_24h=result_return,
        profit_after_72h=result_return,
        maximum_drawdown=result_drawdown,
        result_return=result_return,
        result_drawdown=result_drawdown,
        evaluated_at=candle_timestamp + timedelta(hours=24),
    )


def test_pattern_statistics_use_rolling_success_window(db_session, seeded_market) -> None:
    sync_pattern_metadata(db_session)
    db_session.execute(delete(SignalHistory))
    db_session.execute(delete(PatternStatistic))
    db_session.commit()

    coin_id = int(seeded_market["BTCUSD_EVT"]["coin_id"])
    start = utc_now() - timedelta(days=20)
    rows = []
    for index in range(PATTERN_SUCCESS_ROLLING_WINDOW + 10):
        result = -0.04 if index < 10 else 0.05
        rows.append(
            _history_row(
                coin_id=coin_id,
                timeframe=15,
                signal_type="pattern_bull_flag",
                market_regime="bull_trend",
                candle_timestamp=start + timedelta(minutes=15 * index),
                result_return=result,
                result_drawdown=-0.015,
            )
        )
    db_session.add_all(rows)
    db_session.commit()

    refresh_pattern_statistics(db_session, emit_events=False)

    global_row = db_session.get(PatternStatistic, ("bull_flag", 15, GLOBAL_MARKET_REGIME))
    regime_row = db_session.get(PatternStatistic, ("bull_flag", 15, "bull_trend"))
    assert global_row is not None
    assert regime_row is not None
    assert global_row.total_signals == PATTERN_SUCCESS_ROLLING_WINDOW
    assert global_row.successful_signals == PATTERN_SUCCESS_ROLLING_WINDOW
    assert global_row.success_rate == 1.0
    assert global_row.last_evaluated_at is not None
    assert regime_row.total_signals == PATTERN_SUCCESS_ROLLING_WINDOW


def test_pattern_statistics_track_market_regime_scopes(db_session, seeded_market) -> None:
    sync_pattern_metadata(db_session)
    db_session.execute(delete(SignalHistory))
    db_session.execute(delete(PatternStatistic))
    db_session.commit()

    coin_id = int(seeded_market["ETHUSD_EVT"]["coin_id"])
    base = utc_now() - timedelta(days=5)
    db_session.add_all(
        [
            _history_row(
                coin_id=coin_id,
                timeframe=60,
                signal_type="pattern_head_shoulders",
                market_regime="bear_trend",
                candle_timestamp=base,
                result_return=0.06,
                result_drawdown=-0.02,
            ),
            _history_row(
                coin_id=coin_id,
                timeframe=60,
                signal_type="pattern_head_shoulders",
                market_regime="bear_trend",
                candle_timestamp=base + timedelta(hours=1),
                result_return=0.05,
                result_drawdown=-0.01,
            ),
            _history_row(
                coin_id=coin_id,
                timeframe=60,
                signal_type="pattern_head_shoulders",
                market_regime="bull_trend",
                candle_timestamp=base + timedelta(hours=2),
                result_return=-0.03,
                result_drawdown=-0.05,
            ),
        ]
    )
    db_session.commit()

    refresh_pattern_statistics(db_session, emit_events=False)

    global_row = db_session.get(PatternStatistic, ("head_shoulders", 60, GLOBAL_MARKET_REGIME))
    bear_row = db_session.get(PatternStatistic, ("head_shoulders", 60, "bear_trend"))
    bull_row = db_session.get(PatternStatistic, ("head_shoulders", 60, "bull_trend"))
    assert global_row is not None
    assert bear_row is not None
    assert bull_row is not None
    assert global_row.total_signals == 3
    assert global_row.successful_signals == 2
    assert round(global_row.success_rate, 4) == round(2 / 3, 4)
    assert bear_row.success_rate == 1.0
    assert bull_row.success_rate == 0.0
