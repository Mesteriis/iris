from __future__ import annotations

from collections import defaultdict
from hashlib import sha1

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.coin import Coin
from app.models.discovered_pattern import DiscoveredPattern
from app.patterns.registry import feature_enabled
from app.services.candles_service import fetch_candle_points

DISCOVERY_WINDOW_BARS = 24
DISCOVERY_STEP = 4
DISCOVERY_HORIZON = 8


def _window_signature(closes: list[float]) -> str:
    base = closes[0]
    normalized = [((value - base) / base) if base else 0.0 for value in closes]
    chunk_size = max(len(normalized) // 8, 1)
    compressed = [
        round(sum(normalized[index : index + chunk_size]) / len(normalized[index : index + chunk_size]), 4)
        for index in range(0, len(normalized), chunk_size)
    ]
    volatility_bucket = round((max(closes) - min(closes)) / max(closes[-1], 1e-9), 3)
    signature = "|".join(f"{value:.4f}" for value in compressed[:8]) + f"|{volatility_bucket:.3f}"
    return sha1(signature.encode("ascii")).hexdigest()


def refresh_discovered_patterns(db: Session) -> dict[str, object]:
    if not feature_enabled(db, "pattern_discovery_engine"):
        return {"status": "skipped", "reason": "pattern_discovery_disabled"}

    aggregates: dict[tuple[str, int], list[tuple[float, float]]] = defaultdict(list)
    coins = db.scalars(
        select(Coin).where(Coin.enabled.is_(True), Coin.deleted_at.is_(None)).order_by(Coin.sort_order.asc(), Coin.symbol.asc())
    ).all()
    for coin in coins:
        for candle_config in coin.candles_config or []:
            timeframe = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}.get(str(candle_config["interval"]))
            if timeframe is None:
                continue
            candles = fetch_candle_points(db, coin.id, timeframe, min(int(candle_config.get("retention_bars", 220)), 240))
            if len(candles) < DISCOVERY_WINDOW_BARS + DISCOVERY_HORIZON:
                continue
            closes = [float(item.close) for item in candles]
            lows = [float(item.low) for item in candles]
            for start_index in range(0, len(candles) - DISCOVERY_WINDOW_BARS - DISCOVERY_HORIZON + 1, DISCOVERY_STEP):
                window_closes = closes[start_index : start_index + DISCOVERY_WINDOW_BARS]
                future_closes = closes[
                    start_index + DISCOVERY_WINDOW_BARS : start_index + DISCOVERY_WINDOW_BARS + DISCOVERY_HORIZON
                ]
                future_lows = lows[
                    start_index + DISCOVERY_WINDOW_BARS : start_index + DISCOVERY_WINDOW_BARS + DISCOVERY_HORIZON
                ]
                structure_hash = _window_signature(window_closes)
                entry = window_closes[-1]
                avg_return = (future_closes[-1] - entry) / max(entry, 1e-9)
                avg_drawdown = (min(future_lows) - entry) / max(entry, 1e-9)
                aggregates[(structure_hash, timeframe)].append((avg_return, avg_drawdown))

    rows: list[dict[str, object]] = []
    for (structure_hash, timeframe), outcomes in aggregates.items():
        sample_size = len(outcomes)
        if sample_size < 3:
            continue
        avg_return = sum(item[0] for item in outcomes) / sample_size
        avg_drawdown = sum(item[1] for item in outcomes) / sample_size
        confidence = max(min(0.5 + sample_size / 20 + avg_return - abs(avg_drawdown) * 0.5, 0.95), 0.1)
        rows.append(
            {
                "structure_hash": structure_hash,
                "timeframe": timeframe,
                "sample_size": sample_size,
                "avg_return": avg_return,
                "avg_drawdown": avg_drawdown,
                "confidence": confidence,
            }
        )

    db.execute(delete(DiscoveredPattern))
    if rows:
        stmt = insert(DiscoveredPattern).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["structure_hash", "timeframe"],
            set_={
                "sample_size": stmt.excluded.sample_size,
                "avg_return": stmt.excluded.avg_return,
                "avg_drawdown": stmt.excluded.avg_drawdown,
                "confidence": stmt.excluded.confidence,
            },
        )
        db.execute(stmt)
    db.commit()
    return {"status": "ok", "patterns": len(rows)}
