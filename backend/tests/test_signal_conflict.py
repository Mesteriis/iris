from __future__ import annotations

from datetime import datetime, timezone

from app.analysis.signal_fusion_engine import evaluate_market_decision
from tests.fusion_support import create_test_coin, insert_signals, replace_pattern_statistics


def test_signal_fusion_conflicting_stack_returns_hold(db_session) -> None:
    coin = create_test_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test")
    coin_id = int(coin.id)
    timestamp = datetime(2026, 3, 11, 13, 45, tzinfo=timezone.utc)
    replace_pattern_statistics(
        db_session,
        timeframe=15,
        rows=[
            ("bull_flag", "all", 0.64, 70),
            ("head_shoulders", "all", 0.63, 70),
        ],
    )
    insert_signals(
        db_session,
        coin_id=coin_id,
        timeframe=15,
        candle_timestamp=timestamp,
        items=[
            ("pattern_bull_flag", 0.78),
            ("pattern_head_shoulders", 0.77),
        ],
    )

    result = evaluate_market_decision(
        db_session,
        coin_id=coin_id,
        timeframe=15,
        trigger_timestamp=timestamp,
        emit_event=False,
    )

    assert result["status"] == "ok"
    assert result["decision"] == "HOLD"
    assert float(result["confidence"]) >= 0.35
