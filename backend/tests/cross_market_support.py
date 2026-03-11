from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.apps.market_data.models import Coin
from app.apps.indicators.models import CoinMetrics
from app.apps.predictions.models import MarketPrediction
from app.apps.market_data.repos import upsert_base_candles
from app.apps.market_data.sources.base import MarketBar
from tests.fusion_support import create_test_coin, upsert_coin_metrics
from tests.portfolio_support import create_sector


def generate_close_series(*, start_price: float, returns: list[float]) -> list[float]:
    closes = [start_price]
    for value in returns:
        closes.append(closes[-1] * (1 + value))
    return closes


def correlated_close_series(*, leader_returns: list[float], lag_bars: int, start_price: float) -> list[float]:
    follower_returns: list[float] = []
    for index in range(len(leader_returns)):
        if index < lag_bars:
            follower_returns.append(0.0015 if index % 2 == 0 else 0.0008)
            continue
        follower_returns.append((leader_returns[index - lag_bars] * 0.9) + 0.0004)
    return generate_close_series(start_price=start_price, returns=follower_returns)


def seed_candles(
    db: Session,
    *,
    coin: Coin,
    interval: str,
    closes: list[float],
    start: datetime,
    base_volume: float = 1_000.0,
) -> None:
    delta = timedelta(hours=1) if interval == "1h" else timedelta(minutes=15)
    bars: list[MarketBar] = []
    previous_close = closes[0]
    for index, close in enumerate(closes):
        timestamp = start + (delta * index)
        open_value = previous_close
        high_value = max(open_value, close) * 1.01
        low_value = min(open_value, close) * 0.99
        bars.append(
            MarketBar(
                timestamp=timestamp,
                open=open_value,
                high=high_value,
                low=low_value,
                close=close,
                volume=base_volume + (index * 10),
                source="fixture",
            )
        )
        previous_close = close
    upsert_base_candles(db, coin, interval, bars)


def create_cross_market_coin(
    db: Session,
    *,
    symbol: str,
    name: str,
    sector_name: str,
) -> Coin:
    coin = create_test_coin(db, symbol=symbol, name=name)
    sector = create_sector(db, name=sector_name)
    coin.sector_id = int(sector.id)
    coin.sector_code = sector_name
    db.commit()
    return coin


def set_market_metrics(
    db: Session,
    *,
    coin_id: int,
    regime: str,
    price_change_24h: float,
    volume_change_24h: float,
    volatility: float = 0.04,
    market_cap: float = 5_000_000_000.0,
) -> CoinMetrics:
    row = upsert_coin_metrics(db, coin_id=coin_id, regime=regime, timeframe=60)
    row.price_change_24h = price_change_24h
    row.volume_change_24h = volume_change_24h
    row.volatility = volatility
    row.market_cap = market_cap
    db.commit()
    db.refresh(row)
    return row


def create_pending_prediction(
    db: Session,
    *,
    leader_coin_id: int,
    target_coin_id: int,
    created_at: datetime,
    lag_hours: int,
    expected_move: str = "up",
    confidence: float = 0.75,
) -> MarketPrediction:
    row = MarketPrediction(
        prediction_type="cross_market_follow_through",
        leader_coin_id=leader_coin_id,
        target_coin_id=target_coin_id,
        prediction_event="leader_breakout" if expected_move == "up" else "leader_breakdown",
        expected_move=expected_move,
        lag_hours=lag_hours,
        confidence=confidence,
        created_at=created_at,
        evaluation_time=created_at + timedelta(hours=lag_hours),
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


DEFAULT_START = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)
