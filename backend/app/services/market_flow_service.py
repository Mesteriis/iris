from __future__ import annotations

import json
from datetime import datetime

from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.core.config import get_settings
from app.models.coin import Coin
from app.models.coin_metrics import CoinMetrics
from app.models.coin_relation import CoinRelation
from app.models.sector import Sector
from app.models.sector_metric import SectorMetric
from app.schemas.market_flow import CoinRelationRead, MarketFlowRead, MarketLeaderRead, SectorMomentumRead, SectorRotationRead
from app.services.market_data import ensure_utc


def _recent_market_leaders(db: Session, *, limit: int) -> list[MarketLeaderRead]:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        messages = redis.xrevrange(settings.event_stream_name, "+", "-", count=max(limit * 30, 100))
    finally:
        redis.close()
    seen: set[int] = set()
    leaders: list[tuple[int, float, datetime]] = []
    for _, fields in messages:
        if fields.get("event_type") != "market_leader_detected":
            continue
        coin_id = int(fields["coin_id"])
        if coin_id in seen:
            continue
        seen.add(coin_id)
        payload = json.loads(fields.get("payload") or "{}")
        leaders.append(
            (
                coin_id,
                float(payload.get("confidence") or 0.0),
                ensure_utc(datetime.fromisoformat(fields["timestamp"])),
            )
        )
        if len(leaders) >= limit:
            break
    result: list[MarketLeaderRead] = []
    for coin_id, confidence, timestamp in leaders:
        coin = db.get(Coin, coin_id)
        metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id))
        if coin is None:
            continue
        result.append(
            MarketLeaderRead(
                leader_coin_id=coin_id,
                symbol=coin.symbol,
                name=coin.name,
                sector=coin.sector_code,
                regime=metrics.market_regime if metrics is not None else None,
                confidence=confidence,
                price_change_24h=float(metrics.price_change_24h) if metrics is not None and metrics.price_change_24h is not None else None,
                volume_change_24h=float(metrics.volume_change_24h) if metrics is not None and metrics.volume_change_24h is not None else None,
                timestamp=timestamp,
            )
        )
    return result


def _recent_sector_rotations(*, limit: int) -> list[SectorRotationRead]:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        messages = redis.xrevrange(settings.event_stream_name, "+", "-", count=max(limit * 20, 100))
    finally:
        redis.close()
    rotations: list[SectorRotationRead] = []
    seen: set[tuple[str, str, int]] = set()
    for _, fields in messages:
        if fields.get("event_type") != "sector_rotation_detected":
            continue
        payload = json.loads(fields.get("payload") or "{}")
        source_sector = str(payload.get("source_sector") or "")
        target_sector = str(payload.get("target_sector") or "")
        timeframe = int(fields["timeframe"])
        key = (source_sector, target_sector, timeframe)
        if not source_sector or not target_sector or key in seen:
            continue
        seen.add(key)
        rotations.append(
            SectorRotationRead(
                source_sector=source_sector,
                target_sector=target_sector,
                timeframe=timeframe,
                timestamp=ensure_utc(datetime.fromisoformat(fields["timestamp"])),
            )
        )
        if len(rotations) >= limit:
            break
    return rotations


def get_market_flow(db: Session, *, limit: int = 8, timeframe: int = 60) -> MarketFlowRead:
    follower_coin = aliased(Coin)
    relation_rows = db.execute(
        select(
            CoinRelation.leader_coin_id,
            Coin.symbol.label("leader_symbol"),
            CoinRelation.follower_coin_id,
            follower_coin.symbol.label("follower_symbol"),
            CoinRelation.correlation,
            CoinRelation.lag_hours,
            CoinRelation.confidence,
            CoinRelation.updated_at,
        )
        .join(Coin, Coin.id == CoinRelation.leader_coin_id)
        .join(follower_coin, CoinRelation.follower_coin_id == follower_coin.id)
        .order_by(CoinRelation.confidence.desc(), CoinRelation.correlation.desc(), CoinRelation.updated_at.desc())
        .limit(max(limit, 1))
    ).all()
    sector_rows = db.execute(
        select(
            SectorMetric.sector_id,
            Sector.name.label("sector"),
            SectorMetric.timeframe,
            SectorMetric.avg_price_change_24h,
            SectorMetric.avg_volume_change_24h,
            SectorMetric.volatility,
            SectorMetric.trend,
            SectorMetric.relative_strength,
            SectorMetric.capital_flow,
            SectorMetric.updated_at,
        )
        .join(Sector, Sector.id == SectorMetric.sector_id)
        .where(SectorMetric.timeframe == timeframe)
        .order_by(SectorMetric.relative_strength.desc(), Sector.name.asc())
        .limit(max(limit, 1))
    ).all()
    return MarketFlowRead(
        leaders=_recent_market_leaders(db, limit=max(limit, 1)),
        relations=[CoinRelationRead.model_validate(dict(row._mapping)) for row in relation_rows],
        sectors=[SectorMomentumRead.model_validate(dict(row._mapping)) for row in sector_rows],
        rotations=_recent_sector_rotations(limit=max(limit, 1)),
    )
