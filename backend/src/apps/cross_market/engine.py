from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.apps.cross_market.cache import read_cached_correlation
from src.apps.cross_market.models import CoinRelation, SectorMetric
from src.apps.cross_market.support import (
    LEADER_SYMBOLS,
    best_lagged_correlation as _best_lagged_correlation,
    clamp_relation_value as _clamp,
    pearson as _pearson,
)
from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.models import Coin
from src.apps.signals.models import MarketDecision
from src.core.db.persistence import PERSISTENCE_LOGGER, sanitize_log_value


def _log_compat(level: int, event: str, /, *, component_type: str, component: str, **fields: Any) -> None:
    PERSISTENCE_LOGGER.log(
        level,
        event,
        extra={
            "persistence": {
                "event": event,
                "component_type": component_type,
                "domain": "cross_market",
                "component": component,
                **{key: sanitize_log_value(value) for key, value in fields.items()},
            }
        },
    )


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


def cross_market_alignment_weight(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    directional_bias: float,
) -> float:
    _log_compat(
        logging.DEBUG,
        "compat.cross_market_alignment_weight.execute",
        component_type="compatibility_query",
        component="cross_market_alignment_weight",
        mode="read",
        coin_id=coin_id,
        timeframe=timeframe,
        directional_bias=directional_bias,
    )
    if directional_bias == 0:
        _log_compat(
            logging.INFO,
            "compat.cross_market_alignment_weight.result",
            component_type="compatibility_query",
            component="cross_market_alignment_weight",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
            directional_bias=directional_bias,
            weight=1.0,
        )
        return 1.0
    relations = db.scalars(
        select(CoinRelation)
        .where(CoinRelation.follower_coin_id == coin_id, CoinRelation.confidence >= 0.45)
        .order_by(CoinRelation.confidence.desc(), CoinRelation.correlation.desc())
        .limit(3)
    ).all()
    if not relations:
        _log_compat(
            logging.INFO,
            "compat.cross_market_alignment_weight.result",
            component_type="compatibility_query",
            component="cross_market_alignment_weight",
            mode="read",
            coin_id=coin_id,
            timeframe=timeframe,
            directional_bias=directional_bias,
            weight=1.0,
            relation_count=0,
        )
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
    result = _clamp(weight, 0.75, 1.35)
    _log_compat(
        logging.INFO,
        "compat.cross_market_alignment_weight.result",
        component_type="compatibility_query",
        component="cross_market_alignment_weight",
        mode="read",
        coin_id=coin_id,
        timeframe=timeframe,
        directional_bias=directional_bias,
        weight=result,
        relation_count=len(relations),
    )
    return result

