from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select
from src.apps.market_data.candles import CandlePoint
from src.apps.market_data.domain import ensure_utc
from src.apps.signals.history_support import (
    _candle_index_map,
    _close_timestamps,
    _drawdown_for_window,
    _evaluate_signal,
    _index_at_or_after,
    _open_timestamp_from_signal,
    _return_for_index,
    _signal_direction,
)
from src.apps.signals.models import Signal, SignalHistory
from src.apps.signals.repositories import SignalHistoryRepository
from src.apps.signals.services import SignalHistoryRefreshResult, SignalHistoryService
from src.core.db.persistence import PERSISTENCE_LOGGER
from src.core.db.uow import SessionUnitOfWork

from tests.cross_market_support import DEFAULT_START, seed_candles
from tests.factories.seeds import SignalSeedFactory
from tests.fusion_support import create_test_coin


def _hourly_candles(*, count: int, start_price: float = 100.0) -> list[CandlePoint]:
    return [
        CandlePoint(
            timestamp=DEFAULT_START + timedelta(hours=index),
            open=start_price + index,
            high=start_price + index + 2.0,
            low=start_price + index,
            close=start_price + index,
            volume=1_000.0 + index,
        )
        for index in range(count)
    ]


def _build_signal(
    *,
    coin_id: int,
    timeframe: int,
    signal_type: str,
    confidence: float,
    candle_timestamp,
) -> Signal:
    seed = SignalSeedFactory.build(
        signal_type=signal_type,
        confidence=confidence,
        priority_score=100.0,
        context_score=1.0,
        regime_alignment=1.0,
        candle_timestamp=candle_timestamp,
        created_at=candle_timestamp,
    )
    return Signal(coin_id=coin_id, timeframe=timeframe, **seed.__dict__)


async def _refresh_history(
    async_db_session,
    *,
    commit: bool,
    lookback_days: int,
    coin_id: int | None = None,
    timeframe: int | None = None,
    limit_per_scope: int | None = None,
) -> SignalHistoryRefreshResult:
    async with SessionUnitOfWork(async_db_session) as uow:
        result = await SignalHistoryService(uow).refresh_history(
            lookback_days=lookback_days,
            coin_id=coin_id,
            timeframe=timeframe,
            limit_per_scope=limit_per_scope,
        )
        if commit:
            await uow.commit()
        return result


async def _refresh_recent_history(
    async_db_session,
    *,
    coin_id: int,
    timeframe: int,
    commit: bool,
) -> SignalHistoryRefreshResult:
    async with SessionUnitOfWork(async_db_session) as uow:
        result = await SignalHistoryService(uow).refresh_recent_history(
            coin_id=coin_id,
            timeframe=timeframe,
        )
        if commit:
            await uow.commit()
        return result


def test_signal_history_helper_math_covers_direction_indexing_and_returns() -> None:
    signal_timestamp = DEFAULT_START + timedelta(hours=1)
    bullish_signal = _build_signal(
        coin_id=1,
        timeframe=60,
        signal_type="golden_cross",
        confidence=0.7,
        candle_timestamp=signal_timestamp,
    )
    bearish_signal = _build_signal(
        coin_id=1,
        timeframe=60,
        signal_type="death_cross",
        confidence=0.7,
        candle_timestamp=signal_timestamp,
    )
    pattern_signal = _build_signal(
        coin_id=1,
        timeframe=60,
        signal_type="pattern_bull_flag",
        confidence=0.3,
        candle_timestamp=signal_timestamp,
    )
    fallback_signal = _build_signal(
        coin_id=1,
        timeframe=60,
        signal_type="custom_unknown",
        confidence=0.3,
        candle_timestamp=signal_timestamp,
    )

    assert _signal_direction("golden_cross", 0.7) == 1
    assert _signal_direction("death_cross", 0.7) == -1
    assert _signal_direction("pattern_bull_flag", 0.3) == 1
    assert _signal_direction("custom_unknown", 0.3) == -1
    assert _open_timestamp_from_signal(bullish_signal) == DEFAULT_START

    candles = _hourly_candles(count=4)
    close_timestamps = _close_timestamps(candles, 60)
    assert close_timestamps[0] == DEFAULT_START + timedelta(hours=1)
    assert _candle_index_map(candles)[DEFAULT_START + timedelta(hours=2)] == 2
    assert _index_at_or_after(close_timestamps, DEFAULT_START + timedelta(hours=2, minutes=30)) == 2
    assert _index_at_or_after(close_timestamps, DEFAULT_START + timedelta(days=10)) is None

    future_candle = CandlePoint(
        timestamp=DEFAULT_START + timedelta(hours=5),
        open=104.0,
        high=107.0,
        low=103.0,
        close=105.0,
        volume=1200.0,
    )
    assert _return_for_index(bullish_signal, 100.0, future_candle) == pytest.approx(0.05)
    assert _return_for_index(bearish_signal, 100.0, future_candle) == pytest.approx(-0.05)
    assert _drawdown_for_window(pattern_signal, 100.0, candles[1:]) == pytest.approx(0.01)
    assert _drawdown_for_window(bearish_signal, 100.0, candles[1:]) == pytest.approx(-0.05)
    assert _drawdown_for_window(bullish_signal, 100.0, []) is None
    assert fallback_signal.signal_type == "custom_unknown"


def test_signal_history_evaluate_signal_handles_complete_and_missing_windows() -> None:
    candles = _hourly_candles(count=80)
    close_timestamps = _close_timestamps(candles, 60)
    close_index_map = {timestamp: index for index, timestamp in enumerate(close_timestamps)}

    signal = _build_signal(
        coin_id=1,
        timeframe=60,
        signal_type="golden_cross",
        confidence=0.8,
        candle_timestamp=close_timestamps[0],
    )
    outcome = _evaluate_signal(signal, candles, close_timestamps, close_index_map)
    assert outcome.profit_after_24h == pytest.approx(0.24)
    assert outcome.profit_after_72h == pytest.approx(0.72)
    assert outcome.maximum_drawdown == pytest.approx(0.01)
    assert outcome.result_return == pytest.approx(0.72)
    assert outcome.result_drawdown == pytest.approx(0.01)
    assert outcome.evaluated_at is not None

    missing_signal = _build_signal(
        coin_id=1,
        timeframe=60,
        signal_type="golden_cross",
        confidence=0.8,
        candle_timestamp=ensure_utc(DEFAULT_START),
    )
    missing_outcome = _evaluate_signal(missing_signal, candles, close_timestamps, close_index_map)
    assert missing_outcome.profit_after_24h is None
    assert missing_outcome.profit_after_72h is None
    assert missing_outcome.maximum_drawdown is None
    assert missing_outcome.result_return is None
    assert missing_outcome.result_drawdown is None
    assert missing_outcome.evaluated_at is None


@pytest.mark.asyncio
async def test_refresh_signal_history_returns_empty_when_no_signals(async_db_session) -> None:
    result = await _refresh_history(
        async_db_session,
        coin_id=999_999,
        timeframe=60,
        lookback_days=30,
        commit=False,
    )
    assert result == SignalHistoryRefreshResult(
        status="ok",
        rows=0,
        evaluated=0,
        coin_id=999_999,
        timeframe=60,
    )


@pytest.mark.asyncio
async def test_signal_history_service_emits_execution_logs(async_db_session, monkeypatch) -> None:
    events: list[str] = []

    def _log(level: int, message: str, *args, **kwargs) -> None:
        del level, args, kwargs
        events.append(message)

    monkeypatch.setattr(PERSISTENCE_LOGGER, "log", _log)

    result = await _refresh_history(
        async_db_session,
        coin_id=999_999,
        timeframe=60,
        lookback_days=30,
        commit=False,
    )

    assert result.rows == 0
    assert "service.refresh_signal_history" in events
    assert "repo.list_signal_history_signals" in events
    assert "service.refresh_signal_history.result" in events


@pytest.mark.asyncio
async def test_signal_history_service_refresh_recent_logs(async_db_session, monkeypatch) -> None:
    events: list[str] = []

    def _log(level: int, message: str, *args, **kwargs) -> None:
        del level, args, kwargs
        events.append(message)

    monkeypatch.setattr(PERSISTENCE_LOGGER, "log", _log)

    result = await _refresh_recent_history(
        async_db_session,
        coin_id=999_999,
        timeframe=60,
        commit=False,
    )

    assert result.rows == 0
    assert "service.refresh_recent_signal_history" in events
    assert "service.refresh_signal_history.result" in events


@pytest.mark.asyncio
async def test_refresh_signal_history_handles_missing_candles(async_db_session, db_session) -> None:
    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    signal_timestamp = DEFAULT_START + timedelta(hours=1)
    db_session.add(
        _build_signal(
            coin_id=int(coin.id),
            timeframe=60,
            signal_type="golden_cross",
            confidence=0.72,
            candle_timestamp=signal_timestamp,
        )
    )
    db_session.commit()

    result = await _refresh_history(
        async_db_session,
        coin_id=int(coin.id),
        timeframe=60,
        lookback_days=30,
        commit=True,
    )
    assert result.rows == 1
    assert result.evaluated == 0

    db_session.expire_all()
    history_row = db_session.scalar(
        select(SignalHistory).where(SignalHistory.coin_id == int(coin.id), SignalHistory.timeframe == 60).limit(1)
    )
    assert history_row is not None
    assert history_row.result_return is None
    assert history_row.evaluated_at is None


@pytest.mark.asyncio
async def test_signal_history_service_handles_short_windows(async_db_session, db_session) -> None:
    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    closes = [100.0, 101.0, 102.0]
    seed_candles(db_session, coin=coin, interval="1h", closes=closes, start=DEFAULT_START)
    signal_timestamp = DEFAULT_START + timedelta(hours=1)
    db_session.add(
        _build_signal(
            coin_id=int(coin.id),
            timeframe=60,
            signal_type="golden_cross",
            confidence=0.66,
            candle_timestamp=signal_timestamp,
        )
    )
    db_session.commit()

    fetched = await SignalHistoryRepository(async_db_session).list_signals_for_history(
        lookback_days=30,
        coin_id=int(coin.id),
        timeframe=60,
        limit_per_scope=1,
    )
    assert len(fetched) == 1
    assert (
        len(
            await SignalHistoryRepository(async_db_session).list_signals_for_history(
                lookback_days=30, limit_per_scope=1
            )
        )
        >= 1
    )

    result = await _refresh_history(
        async_db_session,
        coin_id=int(coin.id),
        timeframe=60,
        lookback_days=30,
        limit_per_scope=1,
        commit=True,
    )
    assert result.rows == 1
    assert result.evaluated == 0

    db_session.expire_all()
    history_row = db_session.scalar(
        select(SignalHistory).where(SignalHistory.coin_id == int(coin.id), SignalHistory.timeframe == 60).limit(1)
    )
    assert history_row is not None
    assert history_row.result_return is None
    assert history_row.evaluated_at is None


@pytest.mark.asyncio
async def test_signal_history_service_upserts_rows_and_recent_refresh(async_db_session, db_session) -> None:
    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    closes = [100.0 + index for index in range(80)]
    seed_candles(db_session, coin=coin, interval="1h", closes=closes, start=DEFAULT_START)
    signal_timestamp = DEFAULT_START + timedelta(hours=1)
    signal = Signal(
        coin_id=int(coin.id),
        timeframe=60,
        signal_type="golden_cross",
        confidence=0.72,
        candle_timestamp=signal_timestamp,
        created_at=signal_timestamp,
    )
    db_session.add(signal)
    db_session.commit()

    result = await _refresh_history(
        async_db_session,
        coin_id=int(coin.id),
        timeframe=60,
        lookback_days=30,
        commit=True,
    )
    assert result.rows == 1
    assert result.evaluated == 1

    db_session.expire_all()
    history_row = db_session.scalar(
        select(SignalHistory)
        .where(
            SignalHistory.coin_id == int(coin.id),
            SignalHistory.timeframe == 60,
            SignalHistory.signal_type == "golden_cross",
        )
        .limit(1)
    )
    assert history_row is not None
    assert history_row.result_return == pytest.approx(0.72)
    assert history_row.profit_after_24h == pytest.approx(0.24)
    assert history_row.profit_after_72h == pytest.approx(0.72)
    assert history_row.evaluated_at is not None

    signal.confidence = 0.41
    db_session.commit()

    recent_result = await _refresh_recent_history(
        async_db_session,
        coin_id=int(coin.id),
        timeframe=60,
        commit=True,
    )
    assert recent_result.rows == 1

    db_session.expire_all()
    refreshed_row = db_session.scalar(
        select(SignalHistory)
        .where(
            SignalHistory.coin_id == int(coin.id),
            SignalHistory.timeframe == 60,
            SignalHistory.signal_type == "golden_cross",
        )
        .limit(1)
    )
    assert refreshed_row is not None
    assert refreshed_row.confidence == pytest.approx(0.41)
