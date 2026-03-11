from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.coin import Coin
from app.models.coin_metrics import CoinMetrics
from app.models.sector import Sector
from app.models.sector_metric import SectorMetric
from app.services.candles_service import fetch_candle_points
from app.services.market_data import utc_now

ROTATION_STATES = [
    "btc_dominance_rising",
    "btc_dominance_falling",
    "sector_leadership_change",
]


@dataclass(slots=True, frozen=True)
class SectorNarrative:
    timeframe: int
    top_sector: str | None
    rotation_state: str | None
    btc_dominance: float | None


def _coin_bar_return(db: Session, coin_id: int, timeframe: int) -> tuple[float | None, float | None]:
    candles = fetch_candle_points(db, coin_id, timeframe, 25)
    if len(candles) < 2:
        return None, None
    previous = float(candles[-2].close)
    current = float(candles[-1].close)
    change = (current - previous) / previous if previous else 0.0
    closes = [float(item.close) for item in candles[-20:]]
    mean_close = sum(closes) / len(closes)
    volatility = (sum((value - mean_close) ** 2 for value in closes) / len(closes)) ** 0.5 if closes else 0.0
    return change, (volatility / current if current else 0.0)


def refresh_sector_metrics(db: Session, *, timeframe: int | None = None) -> dict[str, object]:
    sectors = db.scalars(select(Sector).order_by(Sector.name.asc())).all()
    if not sectors:
        return {"status": "skipped", "reason": "sectors_not_found"}

    timeframes = [timeframe] if timeframe is not None else [15, 60, 240, 1440]
    created = 0
    for current_timeframe in timeframes:
        market_returns: list[float] = []
        sector_rows: list[dict[str, object]] = []
        for sector in sectors:
            sector_coins = db.scalars(
                select(Coin)
                .where(
                    Coin.sector_id == sector.id,
                    Coin.enabled.is_(True),
                    Coin.deleted_at.is_(None),
                )
                .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
            ).all()
            if not sector_coins:
                continue
            price_changes: list[float] = []
            volatility_values: list[float] = []
            capital_flow_components: list[float] = []
            for coin in sector_coins:
                price_change, bar_volatility = _coin_bar_return(db, coin.id, current_timeframe)
                metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin.id))
                if price_change is not None:
                    price_changes.append(price_change)
                    market_returns.append(price_change)
                if bar_volatility is not None:
                    volatility_values.append(bar_volatility)
                if metrics is not None:
                    market_cap_component = ((metrics.market_cap or 0.0) / 1_000_000_000) * (price_change or 0.0)
                    volume_component = (metrics.volume_change_24h or 0.0) / 100
                    capital_flow_components.append(market_cap_component + volume_component)
            if not price_changes:
                continue
            sector_rows.append(
                {
                    "sector_id": sector.id,
                    "timeframe": current_timeframe,
                    "sector_strength": sum(price_changes) / len(price_changes),
                    "relative_strength": 0.0,
                    "capital_flow": sum(capital_flow_components) / len(capital_flow_components) if capital_flow_components else 0.0,
                    "volatility": sum(volatility_values) / len(volatility_values) if volatility_values else 0.0,
                    "updated_at": utc_now(),
                }
            )

        market_return = sum(market_returns) / len(market_returns) if market_returns else 0.0
        for row in sector_rows:
            row["relative_strength"] = float(row["sector_strength"]) - market_return
        if sector_rows:
            stmt = insert(SectorMetric).values(sector_rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["sector_id", "timeframe"],
                set_={
                    "sector_strength": stmt.excluded.sector_strength,
                    "relative_strength": stmt.excluded.relative_strength,
                    "capital_flow": stmt.excluded.capital_flow,
                    "volatility": stmt.excluded.volatility,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            result = db.execute(stmt)
            created += int(result.rowcount or 0)
    db.commit()
    return {"status": "ok", "updated": created}


def build_sector_narratives(db: Session) -> list[SectorNarrative]:
    metrics = db.scalars(select(SectorMetric).order_by(SectorMetric.timeframe.asc(), SectorMetric.relative_strength.desc())).all()
    by_timeframe: dict[int, list[SectorMetric]] = defaultdict(list)
    for metric in metrics:
        by_timeframe[metric.timeframe].append(metric)

    btc_metrics = db.scalar(
        select(CoinMetrics)
        .join(Coin, CoinMetrics.coin_id == Coin.id)
        .where(Coin.symbol == "BTCUSD")
    )
    market_caps = db.scalars(
        select(CoinMetrics.market_cap)
        .join(Coin, CoinMetrics.coin_id == Coin.id)
        .where(Coin.asset_type == "crypto", Coin.deleted_at.is_(None))
    ).all()
    total_market_cap = sum(float(value or 0.0) for value in market_caps)
    btc_dominance = (float(btc_metrics.market_cap or 0.0) / total_market_cap) if btc_metrics is not None and total_market_cap > 0 else None

    narratives: list[SectorNarrative] = []
    for timeframe, items in by_timeframe.items():
        top_sector = next((item.sector.name for item in items if item.sector is not None), None)
        if btc_dominance is None:
            rotation_state = None
        elif btc_dominance >= 0.45 and (btc_metrics.price_change_24h or 0.0) >= 0:
            rotation_state = "btc_dominance_rising"
        elif btc_dominance < 0.45 and (btc_metrics.price_change_24h or 0.0) < 0:
            rotation_state = "btc_dominance_falling"
        else:
            rotation_state = "sector_leadership_change" if top_sector is not None else None
        narratives.append(
            SectorNarrative(
                timeframe=timeframe,
                top_sector=top_sector,
                rotation_state=rotation_state,
                btc_dominance=btc_dominance,
            )
        )
    return narratives
