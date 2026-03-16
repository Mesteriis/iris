from datetime import UTC, datetime, timezone

import pytest
from iris.apps.signals.services import SignalFusionService
from iris.core.db.uow import SessionUnitOfWork

from tests.fusion_support import create_test_coin, insert_signals, replace_pattern_statistics, upsert_coin_metrics


async def _evaluate_market_decision(async_db_session, **kwargs):
    async with SessionUnitOfWork(async_db_session) as uow:
        result = await SignalFusionService(uow).evaluate_market_decision(**kwargs)
        await uow.commit()
        return result


@pytest.mark.asyncio
async def test_signal_fusion_respects_regime_adjustment(async_db_session, db_session) -> None:
    btc_coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    eth_coin = create_test_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test")
    btc_coin_id = int(btc_coin.id)
    eth_coin_id = int(eth_coin.id)
    btc_timestamp = datetime(2026, 3, 11, 13, 45, tzinfo=UTC)
    eth_timestamp = datetime(2026, 3, 11, 13, 45, tzinfo=UTC)

    upsert_coin_metrics(db_session, coin_id=btc_coin_id, regime="high_volatility")
    upsert_coin_metrics(db_session, coin_id=eth_coin_id, regime="sideways_range")
    replace_pattern_statistics(
        db_session,
        timeframe=15,
        rows=[
            ("bollinger_expansion", "high_volatility", 0.76, 65),
            ("bollinger_expansion", "sideways_range", 0.49, 65),
            ("bollinger_squeeze", "high_volatility", 0.73, 65),
            ("bollinger_squeeze", "sideways_range", 0.5, 65),
        ],
    )
    insert_signals(
        db_session,
        coin_id=btc_coin_id,
        timeframe=15,
        candle_timestamp=btc_timestamp,
        items=[
            ("pattern_bollinger_expansion", 0.76),
            ("pattern_bollinger_squeeze", 0.74),
        ],
    )
    insert_signals(
        db_session,
        coin_id=eth_coin_id,
        timeframe=15,
        candle_timestamp=eth_timestamp,
        items=[
            ("pattern_bollinger_expansion", 0.76),
            ("pattern_bollinger_squeeze", 0.74),
        ],
    )

    high_vol = await _evaluate_market_decision(
        async_db_session,
        coin_id=btc_coin_id,
        timeframe=15,
        trigger_timestamp=btc_timestamp,
        emit_event=False,
    )
    sideways = await _evaluate_market_decision(
        async_db_session,
        coin_id=eth_coin_id,
        timeframe=15,
        trigger_timestamp=eth_timestamp,
        emit_event=False,
    )

    assert high_vol.status == "ok"
    assert sideways.status == "ok"
    assert high_vol.decision == "BUY"
    assert float(high_vol.confidence or 0.0) > float(sideways.confidence or 0.0)
