from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.apps.market_data.models import Coin
from app.apps.indicators.models import CoinMetrics
from app.apps.signals.models import MarketDecision
from app.apps.cross_market.models import Sector
from app.apps.patterns.domain.regime import read_regime_details
from app.apps.signals.cache import read_cached_market_decision
from app.apps.market_data.service_layer import get_coin_by_symbol

PREFERRED_TIMEFRAMES = (1440, 240, 60, 15)


def _latest_market_decisions_subquery():
    return (
        select(
            MarketDecision.id.label("id"),
            MarketDecision.coin_id.label("coin_id"),
            MarketDecision.timeframe.label("timeframe"),
            MarketDecision.decision.label("decision"),
            MarketDecision.confidence.label("confidence"),
            MarketDecision.signal_count.label("signal_count"),
            MarketDecision.created_at.label("created_at"),
            func.row_number()
            .over(
                partition_by=(MarketDecision.coin_id, MarketDecision.timeframe),
                order_by=(MarketDecision.created_at.desc(), MarketDecision.id.desc()),
            )
            .label("market_decision_rank"),
        )
        .subquery()
    )


def _serialize_rows(rows: Sequence[object]) -> list[dict[str, Any]]:
    return [
        {
            "id": int(row.id),
            "coin_id": int(row.coin_id),
            "symbol": str(row.symbol),
            "name": str(row.name),
            "sector": row.sector,
            "timeframe": int(row.timeframe),
            "decision": str(row.decision),
            "confidence": float(row.confidence),
            "signal_count": int(row.signal_count),
            "regime": row.regime,
            "created_at": row.created_at,
        }
        for row in rows
    ]


def list_market_decisions(
    db: Session,
    *,
    symbol: str | None = None,
    timeframe: int | None = None,
    limit: int = 100,
) -> Sequence[dict[str, Any]]:
    latest = _latest_market_decisions_subquery()
    stmt = (
        select(
            latest.c.id,
            latest.c.coin_id,
            Coin.symbol,
            Coin.name,
            Sector.name.label("sector"),
            latest.c.timeframe,
            latest.c.decision,
            latest.c.confidence,
            latest.c.signal_count,
            CoinMetrics.market_regime.label("regime"),
            latest.c.created_at,
        )
        .join(Coin, Coin.id == latest.c.coin_id)
        .outerjoin(Sector, Sector.id == Coin.sector_id)
        .outerjoin(CoinMetrics, CoinMetrics.coin_id == latest.c.coin_id)
        .where(latest.c.market_decision_rank == 1, Coin.deleted_at.is_(None))
        .order_by(latest.c.created_at.desc(), latest.c.id.desc())
        .limit(max(limit, 1))
    )
    if symbol is not None:
        stmt = stmt.where(Coin.symbol == symbol.upper())
    if timeframe is not None:
        stmt = stmt.where(latest.c.timeframe == timeframe)
    return _serialize_rows(db.execute(stmt).all())


def list_top_market_decisions(db: Session, *, limit: int = 20) -> Sequence[dict[str, Any]]:
    latest = _latest_market_decisions_subquery()
    rows = db.execute(
        select(
            latest.c.id,
            latest.c.coin_id,
            Coin.symbol,
            Coin.name,
            Sector.name.label("sector"),
            latest.c.timeframe,
            latest.c.decision,
            latest.c.confidence,
            latest.c.signal_count,
            CoinMetrics.market_regime.label("regime"),
            latest.c.created_at,
        )
        .join(Coin, Coin.id == latest.c.coin_id)
        .outerjoin(Sector, Sector.id == Coin.sector_id)
        .outerjoin(CoinMetrics, CoinMetrics.coin_id == latest.c.coin_id)
        .where(latest.c.market_decision_rank == 1, Coin.deleted_at.is_(None))
        .order_by(latest.c.confidence.desc(), latest.c.signal_count.desc(), latest.c.created_at.desc())
        .limit(max(limit, 1))
    ).all()
    return _serialize_rows(rows)


def get_coin_market_decision(db: Session, symbol: str) -> dict[str, Any] | None:
    coin = get_coin_by_symbol(db, symbol)
    if coin is None:
        return None
    metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin.id))
    cached_items: list[dict[str, Any]] = []
    for timeframe in PREFERRED_TIMEFRAMES:
        cached = read_cached_market_decision(coin_id=coin.id, timeframe=timeframe)
        if cached is None:
            continue
        detailed = read_regime_details(metrics.market_regime_details, timeframe) if metrics is not None else None
        cached_items.append(
            {
                "timeframe": timeframe,
                "decision": cached.decision,
                "confidence": cached.confidence,
                "signal_count": cached.signal_count,
                "regime": cached.regime or (detailed.regime if detailed is not None else (metrics.market_regime if metrics is not None else None)),
                "created_at": cached.created_at,
            }
        )
    if cached_items:
        items = sorted(cached_items, key=lambda item: item["timeframe"])
    else:
        latest = _latest_market_decisions_subquery()
        rows = db.execute(
            select(
                latest.c.timeframe,
                latest.c.decision,
                latest.c.confidence,
                latest.c.signal_count,
                latest.c.created_at,
                CoinMetrics.market_regime,
                CoinMetrics.market_regime_details,
            )
            .outerjoin(CoinMetrics, CoinMetrics.coin_id == latest.c.coin_id)
            .where(latest.c.coin_id == coin.id, latest.c.market_decision_rank == 1)
            .order_by(latest.c.timeframe.asc())
        ).all()
        items = []
        for row in rows:
            detailed = read_regime_details(row.market_regime_details, int(row.timeframe))
            items.append(
                {
                    "timeframe": int(row.timeframe),
                    "decision": str(row.decision),
                    "confidence": float(row.confidence),
                    "signal_count": int(row.signal_count),
                    "regime": detailed.regime if detailed is not None else row.market_regime,
                    "created_at": row.created_at,
                }
            )
    canonical = None
    items_by_timeframe = {item["timeframe"]: item for item in items}
    for current_timeframe in PREFERRED_TIMEFRAMES:
        if current_timeframe in items_by_timeframe:
            canonical = str(items_by_timeframe[current_timeframe]["decision"])
            break
    return {
        "coin_id": coin.id,
        "symbol": coin.symbol,
        "canonical_decision": canonical,
        "items": items,
    }
