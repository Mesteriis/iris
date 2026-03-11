from __future__ import annotations

import math
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.runtime.streams.publisher import publish_event
from app.apps.market_data.models import Coin
from app.apps.indicators.models import CoinMetrics
from app.apps.cross_market.models import CoinRelation
from app.apps.signals.models import MarketDecision
from app.apps.cross_market.models import Sector
from app.apps.cross_market.models import SectorMetric
from app.apps.market_data.repos import fetch_candle_points
from app.apps.cross_market.cache import cache_correlation_snapshot, read_cached_correlation
from app.apps.market_data.domain import ensure_utc, utc_now
from app.apps.predictions.engine import create_market_predictions

RELATION_LOOKBACK = 200
RELATION_MIN_POINTS = 48
RELATION_MAX_LAG_HOURS = 8
RELATION_MIN_CORRELATION = 0.25
MATERIAL_RELATION_DELTA = 0.04
LEADER_SYMBOLS = ("BTCUSD", "ETHUSD", "SOLUSD")


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _close_returns(points: list[object]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(points, points[1:], strict=False):
        previous_close = float(previous.close)
        current_close = float(current.close)
        returns.append((current_close - previous_close) / previous_close if previous_close else 0.0)
    return returns


def _pearson(values_a: list[float], values_b: list[float]) -> float:
    if len(values_a) != len(values_b) or len(values_a) < 3:
        return 0.0
    mean_a = sum(values_a) / len(values_a)
    mean_b = sum(values_b) / len(values_b)
    numerator = sum((left - mean_a) * (right - mean_b) for left, right in zip(values_a, values_b, strict=False))
    denominator_left = math.sqrt(sum((value - mean_a) ** 2 for value in values_a))
    denominator_right = math.sqrt(sum((value - mean_b) ** 2 for value in values_b))
    if denominator_left == 0 or denominator_right == 0:
        return 0.0
    return numerator / (denominator_left * denominator_right)


def _best_lagged_correlation(leader_points: list[object], follower_points: list[object], *, timeframe: int) -> tuple[float, int, int]:
    leader_returns = _close_returns(leader_points)
    follower_returns = _close_returns(follower_points)
    size = min(len(leader_returns), len(follower_returns))
    if size < RELATION_MIN_POINTS:
        return 0.0, 0, size
    leader_returns = leader_returns[-size:]
    follower_returns = follower_returns[-size:]
    max_lag_bars = max(min(int((RELATION_MAX_LAG_HOURS * 60) / max(timeframe, 1)), 24), 0)
    best = (0.0, 0, size)
    for lag in range(0, max_lag_bars + 1):
        if lag == 0:
            current_leader = leader_returns
            current_follower = follower_returns
        else:
            current_leader = leader_returns[:-lag]
            current_follower = follower_returns[lag:]
        usable = min(len(current_leader), len(current_follower))
        if usable < RELATION_MIN_POINTS:
            continue
        correlation = _pearson(current_leader[-usable:], current_follower[-usable:])
        if correlation > best[0]:
            lag_hours = max(int(round((lag * timeframe) / 60)), 1 if lag > 0 else 0)
            best = (correlation, lag_hours, usable)
    return best


def _relation_timeframe(timeframe: int) -> int:
    return 60 if timeframe < 60 else timeframe


def _candidate_leaders(db: Session, *, follower: Coin, limit: int = 8) -> list[Coin]:
    preferred_ids = db.scalars(
        select(Coin.id)
        .where(Coin.symbol.in_(LEADER_SYMBOLS), Coin.deleted_at.is_(None), Coin.enabled.is_(True))
    ).all()
    ranked = db.scalars(
        select(Coin)
        .join(CoinMetrics, CoinMetrics.coin_id == Coin.id)
        .where(
            Coin.id != follower.id,
            Coin.deleted_at.is_(None),
            Coin.enabled.is_(True),
        )
        .order_by(CoinMetrics.market_cap.desc().nullslast(), CoinMetrics.activity_score.desc().nullslast(), Coin.symbol.asc())
        .limit(max(limit * 2, 12))
    ).all()
    by_id: dict[int, Coin] = {}
    for coin in ranked:
        by_id[int(coin.id)] = coin
    if follower.sector_id is not None:
        same_sector = db.scalars(
            select(Coin)
            .where(
                Coin.id != follower.id,
                Coin.deleted_at.is_(None),
                Coin.enabled.is_(True),
                Coin.sector_id == follower.sector_id,
            )
            .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
            .limit(limit)
        ).all()
        for coin in same_sector:
            by_id[int(coin.id)] = coin
    ordered: list[Coin] = []
    for coin_id in preferred_ids:
        coin = by_id.get(int(coin_id))
        if coin is not None:
            ordered.append(coin)
    for coin in by_id.values():
        if coin.id != follower.id and coin not in ordered:
            ordered.append(coin)
    return ordered[:limit]


def update_coin_relations(
    db: Session,
    *,
    follower_coin_id: int,
    timeframe: int,
    emit_events: bool = True,
) -> dict[str, object]:
    follower = db.get(Coin, follower_coin_id)
    if follower is None or follower.deleted_at is not None or not follower.enabled:
        return {"status": "skipped", "reason": "follower_not_found", "follower_coin_id": follower_coin_id}
    relation_timeframe = _relation_timeframe(timeframe)
    follower_points = fetch_candle_points(db, follower_coin_id, relation_timeframe, RELATION_LOOKBACK)
    if len(follower_points) < RELATION_MIN_POINTS:
        return {"status": "skipped", "reason": "insufficient_follower_candles", "follower_coin_id": follower_coin_id}
    updated_rows: list[dict[str, object]] = []
    for leader in _candidate_leaders(db, follower=follower):
        leader_points = fetch_candle_points(db, int(leader.id), relation_timeframe, RELATION_LOOKBACK)
        if len(leader_points) < RELATION_MIN_POINTS:
            continue
        correlation, lag_hours, sample_size = _best_lagged_correlation(leader_points, follower_points, timeframe=relation_timeframe)
        if correlation < RELATION_MIN_CORRELATION:
            continue
        confidence = _clamp(correlation * min(sample_size / RELATION_LOOKBACK, 1.0), 0.2, 0.99)
        previous = db.scalar(
            select(CoinRelation)
            .where(CoinRelation.leader_coin_id == leader.id, CoinRelation.follower_coin_id == follower_coin_id)
            .limit(1)
        )
        updated_rows.append(
            {
                "leader_coin_id": int(leader.id),
                "follower_coin_id": int(follower_coin_id),
                "correlation": float(correlation),
                "lag_hours": int(lag_hours),
                "confidence": float(confidence),
                "updated_at": utc_now(),
                "_previous": previous,
            }
        )
    if not updated_rows:
        return {"status": "skipped", "reason": "relations_not_found", "follower_coin_id": follower_coin_id}
    stmt = insert(CoinRelation).values(
        [
            {
                "leader_coin_id": row["leader_coin_id"],
                "follower_coin_id": row["follower_coin_id"],
                "correlation": row["correlation"],
                "lag_hours": row["lag_hours"],
                "confidence": row["confidence"],
                "updated_at": row["updated_at"],
            }
            for row in updated_rows
        ]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["leader_coin_id", "follower_coin_id"],
        set_={
            "correlation": stmt.excluded.correlation,
            "lag_hours": stmt.excluded.lag_hours,
            "confidence": stmt.excluded.confidence,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    db.execute(stmt)
    db.commit()
    published = 0
    for row in updated_rows:
        cache_correlation_snapshot(
            leader_coin_id=int(row["leader_coin_id"]),
            follower_coin_id=int(row["follower_coin_id"]),
            correlation=float(row["correlation"]),
            lag_hours=int(row["lag_hours"]),
            confidence=float(row["confidence"]),
            updated_at=row["updated_at"],
        )
        previous = row["_previous"]
        if emit_events and (
            previous is None
            or abs(float(previous.confidence) - float(row["confidence"])) >= MATERIAL_RELATION_DELTA
            or abs(float(previous.correlation) - float(row["correlation"])) >= MATERIAL_RELATION_DELTA
        ):
            publish_event(
                "correlation_updated",
                {
                    "coin_id": int(row["follower_coin_id"]),
                    "timeframe": relation_timeframe,
                    "timestamp": row["updated_at"],
                    "leader_coin_id": int(row["leader_coin_id"]),
                    "follower_coin_id": int(row["follower_coin_id"]),
                    "correlation": float(row["correlation"]),
                    "lag_hours": int(row["lag_hours"]),
                    "confidence": float(row["confidence"]),
                },
            )
            published += 1
    best = max(updated_rows, key=lambda item: float(item["confidence"]))
    return {
        "status": "ok",
        "updated": len(updated_rows),
        "published": published,
        "follower_coin_id": follower_coin_id,
        "leader_coin_id": int(best["leader_coin_id"]),
        "confidence": float(best["confidence"]),
    }


def refresh_sector_momentum(
    db: Session,
    *,
    timeframe: int,
    emit_events: bool = True,
) -> dict[str, object]:
    previous_top = db.execute(
        select(SectorMetric.sector_id, Sector.name, SectorMetric.relative_strength)
        .join(Sector, Sector.id == SectorMetric.sector_id)
        .where(SectorMetric.timeframe == timeframe)
        .order_by(SectorMetric.relative_strength.desc(), Sector.name.asc())
        .limit(1)
    ).first()
    rows = db.execute(
        select(
            Sector.id.label("sector_id"),
            func.avg(CoinMetrics.price_change_24h).label("avg_price_change_24h"),
            func.avg(CoinMetrics.volume_change_24h).label("avg_volume_change_24h"),
            func.avg(CoinMetrics.volatility).label("avg_volatility"),
            func.avg(CoinMetrics.price_change_24h).label("sector_strength"),
            func.avg(CoinMetrics.volume_change_24h / 100.0).label("relative_strength"),
            func.avg(((CoinMetrics.volume_change_24h / 100.0) + (CoinMetrics.price_change_24h / 10.0))).label("capital_flow"),
        )
        .join(Coin, Coin.sector_id == Sector.id)
        .join(CoinMetrics, CoinMetrics.coin_id == Coin.id)
        .where(Coin.deleted_at.is_(None), Coin.enabled.is_(True))
        .group_by(Sector.id)
        .order_by(Sector.id.asc())
    ).all()
    if not rows:
        return {"status": "skipped", "reason": "sector_rows_not_found"}
    sector_strengths = [float(row.sector_strength or 0.0) for row in rows]
    market_average = sum(sector_strengths) / len(sector_strengths) if sector_strengths else 0.0
    values: list[dict[str, object]] = []
    for row in rows:
        avg_price_change_24h = float(row.avg_price_change_24h or 0.0)
        avg_volume_change_24h = float(row.avg_volume_change_24h or 0.0)
        trend = "sideways"
        if avg_price_change_24h >= 1 and avg_volume_change_24h >= 0:
            trend = "bullish"
        elif avg_price_change_24h <= -1:
            trend = "bearish"
        values.append(
            {
                "sector_id": int(row.sector_id),
                "timeframe": int(timeframe),
                "sector_strength": avg_price_change_24h,
                "relative_strength": avg_price_change_24h - market_average,
                "capital_flow": float(row.capital_flow or 0.0),
                "avg_price_change_24h": avg_price_change_24h,
                "avg_volume_change_24h": avg_volume_change_24h,
                "volatility": float(row.avg_volatility or 0.0),
                "trend": trend,
                "updated_at": utc_now(),
            }
        )
    stmt = insert(SectorMetric).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["sector_id", "timeframe"],
        set_={
            "sector_strength": stmt.excluded.sector_strength,
            "relative_strength": stmt.excluded.relative_strength,
            "capital_flow": stmt.excluded.capital_flow,
            "avg_price_change_24h": stmt.excluded.avg_price_change_24h,
            "avg_volume_change_24h": stmt.excluded.avg_volume_change_24h,
            "volatility": stmt.excluded.volatility,
            "trend": stmt.excluded.trend,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    db.execute(stmt)
    db.commit()
    current_top = db.execute(
        select(SectorMetric.sector_id, Sector.name, SectorMetric.relative_strength)
        .join(Sector, Sector.id == SectorMetric.sector_id)
        .where(SectorMetric.timeframe == timeframe)
        .order_by(SectorMetric.relative_strength.desc(), Sector.name.asc())
        .limit(1)
    ).first()
    if (
        emit_events
        and previous_top is not None
        and current_top is not None
        and int(previous_top.sector_id) != int(current_top.sector_id)
    ):
        publish_event(
            "sector_rotation_detected",
            {
                "coin_id": 0,
                "timeframe": int(timeframe),
                "timestamp": utc_now(),
                "source_sector": str(previous_top.name),
                "target_sector": str(current_top.name),
                "source_strength": float(previous_top.relative_strength or 0.0),
                "target_strength": float(current_top.relative_strength or 0.0),
            },
        )
    return {"status": "ok", "updated": len(values), "timeframe": timeframe}


def _latest_leader_decision(db: Session, *, leader_coin_id: int, timeframe: int) -> tuple[str | None, float]:
    row = db.scalar(
        select(MarketDecision)
        .where(
            MarketDecision.coin_id == leader_coin_id,
            MarketDecision.timeframe.in_((timeframe, 60, 240, 1440)),
        )
        .order_by(MarketDecision.created_at.desc(), MarketDecision.id.desc())
        .limit(1)
    )
    if row is not None:
        return row.decision, float(row.confidence)
    metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == leader_coin_id))
    if metrics is None:
        return None, 0.0
    price_change = float(metrics.price_change_24h or 0.0)
    if price_change > 0:
        return "BUY", _clamp(abs(price_change) / 10, 0.25, 0.75)
    if price_change < 0:
        return "SELL", _clamp(abs(price_change) / 10, 0.25, 0.75)
    return "HOLD", 0.3


def detect_market_leader(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    payload: dict[str, object],
    emit_events: bool = True,
) -> dict[str, object]:
    coin = db.get(Coin, coin_id)
    metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id))
    if coin is None or metrics is None:
        return {"status": "skipped", "reason": "coin_metrics_not_found", "coin_id": coin_id}
    activity_bucket = str(payload.get("activity_bucket") or metrics.activity_bucket or "")
    price_change_24h = float(payload.get("price_change_24h") or metrics.price_change_24h or 0.0)
    volume_change_24h = float(metrics.volume_change_24h or 0.0)
    regime = str(payload.get("market_regime") or metrics.market_regime or "")
    bullish = price_change_24h > 0
    directional_ok = (bullish and regime in {"bull_trend", "high_volatility"}) or ((not bullish) and regime == "bear_trend")
    if activity_bucket != "HOT" or abs(price_change_24h) < 2 or volume_change_24h < 12 or not directional_ok:
        return {"status": "skipped", "reason": "leader_threshold_not_met", "coin_id": coin_id}
    confidence = _clamp(
        0.45 + min(abs(price_change_24h) / 12, 0.2) + min(volume_change_24h / 100, 0.2) + (0.1 if activity_bucket == "HOT" else 0.0),
        0.45,
        0.95,
    )
    direction = "up" if bullish else "down"
    prediction_result = create_market_predictions(
        db,
        leader_coin_id=coin_id,
        prediction_event="leader_breakout" if bullish else "leader_breakdown",
        expected_move=direction,
        base_confidence=confidence,
        emit_events=emit_events,
    )
    if emit_events:
        publish_event(
            "market_leader_detected",
            {
                "coin_id": coin_id,
                "timeframe": int(timeframe),
                "timestamp": utc_now(),
                "leader_coin_id": coin_id,
                "leader_symbol": coin.symbol,
                "direction": direction,
                "confidence": confidence,
                "market_regime": regime,
            },
        )
    return {
        "status": "ok",
        "leader_coin_id": coin_id,
        "direction": direction,
        "confidence": confidence,
        "predictions": prediction_result,
    }


def process_cross_market_event(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    event_type: str,
    payload: dict[str, object],
    emit_events: bool = True,
) -> dict[str, object]:
    relation_result = update_coin_relations(
        db,
        follower_coin_id=coin_id,
        timeframe=timeframe,
        emit_events=emit_events and event_type == "candle_closed",
    )
    sector_result = refresh_sector_momentum(db, timeframe=timeframe, emit_events=emit_events and event_type == "indicator_updated")
    leader_result = (
        detect_market_leader(db, coin_id=coin_id, timeframe=timeframe, payload=payload, emit_events=emit_events)
        if event_type == "indicator_updated"
        else {"status": "skipped", "reason": "leader_detection_not_requested"}
    )
    return {
        "status": "ok",
        "relations": relation_result,
        "sectors": sector_result,
        "leader": leader_result,
    }


def cross_market_alignment_weight(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    directional_bias: float,
) -> float:
    if directional_bias == 0:
        return 1.0
    relations = db.scalars(
        select(CoinRelation)
        .where(CoinRelation.follower_coin_id == coin_id, CoinRelation.confidence >= 0.45)
        .order_by(CoinRelation.confidence.desc(), CoinRelation.correlation.desc())
        .limit(3)
    ).all()
    if not relations:
        return 1.0
    weight = 1.0
    for relation in relations:
        cached = read_cached_correlation(
            leader_coin_id=int(relation.leader_coin_id),
            follower_coin_id=int(relation.follower_coin_id),
        )
        decision, decision_confidence = _latest_leader_decision(db, leader_coin_id=int(relation.leader_coin_id), timeframe=timeframe)
        if decision is None:
            continue
        relation_strength = float(cached.confidence if cached is not None else relation.confidence) * float(
            cached.correlation if cached is not None else relation.correlation
        )
        delta = min(relation_strength * max(decision_confidence, 0.3), 0.22)
        if directional_bias > 0 and decision == "BUY":
            weight += delta
        elif directional_bias < 0 and decision == "SELL":
            weight += delta
        elif decision in {"BUY", "SELL"}:
            weight -= delta * 0.8
    coin = db.get(Coin, coin_id)
    if coin is not None and coin.sector_id is not None:
        sector_metric = db.get(SectorMetric, (coin.sector_id, timeframe))
        if sector_metric is None and timeframe != 60:
            sector_metric = db.get(SectorMetric, (coin.sector_id, 60))
        if sector_metric is not None:
            if directional_bias > 0 and sector_metric.trend == "bullish":
                weight += 0.05
            elif directional_bias < 0 and sector_metric.trend == "bearish":
                weight += 0.05
            elif sector_metric.trend in {"bullish", "bearish"}:
                weight -= 0.04
    return _clamp(weight, 0.75, 1.35)
