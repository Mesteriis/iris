from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from src.apps.market_data.candles import CandlePoint, interval_to_timeframe
from src.apps.market_data.domain import ensure_utc
from src.apps.market_data.models import Candle, Coin
from src.apps.market_data.sources.base import MarketBar


def upsert_base_candles(
    db: Session,
    coin: Coin,
    interval: str,
    bars: Sequence[MarketBar],
) -> datetime | None:
    timeframe = interval_to_timeframe(interval)
    if not bars:
        return None

    rows = [
        {
            "coin_id": int(coin.id),
            "timeframe": timeframe,
            "timestamp": ensure_utc(bar.timestamp),
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.volume) if bar.volume is not None else None,
        }
        for bar in bars
    ]
    stmt = insert(Candle).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["coin_id", "timeframe", "timestamp"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
        },
    )
    db.execute(stmt)
    db.commit()
    return max(ensure_utc(bar.timestamp) for bar in bars)


def fetch_candle_points(
    db: Session,
    coin_id: int,
    timeframe: int,
    limit: int,
) -> list[CandlePoint]:
    if limit <= 0:
        return []

    rows = (
        db.execute(
            select(Candle.timestamp, Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume)
            .where(Candle.coin_id == coin_id, Candle.timeframe == timeframe)
            .order_by(Candle.timestamp.desc())
            .limit(limit)
        )
        .all()
    )
    return [
        CandlePoint(
            timestamp=ensure_utc(row.timestamp),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=float(row.volume) if row.volume is not None else None,
        )
        for row in reversed(rows)
    ]


__all__ = ["fetch_candle_points", "upsert_base_candles"]
