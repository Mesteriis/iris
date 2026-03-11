from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.coin import Coin
from app.models.coin_metrics import CoinMetrics
from app.schemas.market_radar import MarketRadarCoinRead, MarketRadarRead, MarketRegimeChangeRead
from app.services.market_data import ensure_utc


def _metric_rows(
    db: Session,
    *,
    stmt,
) -> list[MarketRadarCoinRead]:
    rows = db.execute(stmt).all()
    return [
        MarketRadarCoinRead(
            coin_id=int(row.coin_id),
            symbol=str(row.symbol),
            name=str(row.name),
            activity_score=float(row.activity_score) if row.activity_score is not None else None,
            activity_bucket=row.activity_bucket,
            analysis_priority=int(row.analysis_priority) if row.analysis_priority is not None else None,
            price_change_24h=float(row.price_change_24h) if row.price_change_24h is not None else None,
            price_change_7d=float(row.price_change_7d) if row.price_change_7d is not None else None,
            volatility=float(row.volatility) if row.volatility is not None else None,
            market_regime=row.market_regime,
            updated_at=row.updated_at,
            last_analysis_at=row.last_analysis_at,
        )
        for row in rows
    ]


def _metric_projection():
    return (
        Coin.id.label("coin_id"),
        Coin.symbol,
        Coin.name,
        CoinMetrics.activity_score,
        CoinMetrics.activity_bucket,
        CoinMetrics.analysis_priority,
        CoinMetrics.price_change_24h,
        CoinMetrics.price_change_7d,
        CoinMetrics.volatility,
        CoinMetrics.market_regime,
        CoinMetrics.updated_at,
        CoinMetrics.last_analysis_at,
    )


def _recent_regime_changes(db: Session, *, limit: int) -> list[MarketRegimeChangeRead]:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        messages = redis.xrevrange(settings.event_stream_name, "+", "-", count=max(limit * 40, 100))
    finally:
        redis.close()
    changes: list[tuple[int, int, str, float, datetime]] = []
    seen: set[tuple[int, int, str]] = set()
    for _, fields in messages:
        if fields.get("event_type") != "market_regime_changed":
            continue
        coin_id = int(fields["coin_id"])
        timeframe = int(fields["timeframe"])
        timestamp = ensure_utc(datetime.fromisoformat(fields["timestamp"]))
        payload = fields.get("payload") or "{}"
        regime = "unknown"
        confidence = 0.0
        if "\"regime\"" in payload:
            import json

            data = json.loads(payload)
            regime = str(data.get("regime") or regime)
            confidence = float(data.get("confidence") or 0.0)
        key = (coin_id, timeframe, regime)
        if key in seen:
            continue
        seen.add(key)
        changes.append((coin_id, timeframe, regime, confidence, timestamp))
        if len(changes) >= limit:
            break
    if not changes:
        return []
    coin_ids = sorted({coin_id for coin_id, _, _, _, _ in changes})
    coin_rows = db.execute(select(Coin.id, Coin.symbol, Coin.name).where(Coin.id.in_(coin_ids))).all()
    coin_map = {int(row.id): (str(row.symbol), str(row.name)) for row in coin_rows}
    return [
        MarketRegimeChangeRead(
            coin_id=coin_id,
            symbol=coin_map.get(coin_id, ("UNKNOWN", "Unknown"))[0],
            name=coin_map.get(coin_id, ("UNKNOWN", "Unknown"))[1],
            timeframe=timeframe,
            regime=regime,
            confidence=confidence,
            timestamp=timestamp,
        )
        for coin_id, timeframe, regime, confidence, timestamp in changes
    ]


def get_market_radar(db: Session, *, limit: int = 8) -> MarketRadarRead:
    base_stmt = (
        select(*_metric_projection())
        .join(CoinMetrics, CoinMetrics.coin_id == Coin.id)
        .where(Coin.deleted_at.is_(None), Coin.enabled.is_(True))
    )
    hot_coins = _metric_rows(
        db,
        stmt=base_stmt.where(CoinMetrics.activity_bucket == "HOT")
        .order_by(CoinMetrics.activity_score.desc().nullslast(), Coin.symbol.asc())
        .limit(max(limit, 1)),
    )
    emerging_coins = _metric_rows(
        db,
        stmt=base_stmt.where(
            CoinMetrics.activity_bucket.in_(("HOT", "WARM")),
            CoinMetrics.price_change_24h.is_not(None),
            CoinMetrics.price_change_24h > 0,
            CoinMetrics.price_change_7d.is_not(None),
            CoinMetrics.price_change_7d >= 0,
            CoinMetrics.market_regime.in_(("bull_trend", "sideways_range", "high_volatility")),
        )
        .order_by(
            CoinMetrics.activity_score.desc().nullslast(),
            CoinMetrics.price_change_24h.desc().nullslast(),
            Coin.symbol.asc(),
        )
        .limit(max(limit, 1)),
    )
    volatility_spikes = _metric_rows(
        db,
        stmt=base_stmt.where(
            CoinMetrics.volatility.is_not(None),
            CoinMetrics.activity_bucket.in_(("HOT", "WARM", "COLD")),
        )
        .order_by(
            CoinMetrics.market_regime.desc().nullslast(),
            CoinMetrics.volatility.desc().nullslast(),
            Coin.symbol.asc(),
        )
        .limit(max(limit, 1)),
    )
    regime_changes = _recent_regime_changes(db, limit=max(limit, 1))
    return MarketRadarRead(
        hot_coins=hot_coins,
        emerging_coins=emerging_coins,
        regime_changes=regime_changes,
        volatility_spikes=volatility_spikes,
    )
