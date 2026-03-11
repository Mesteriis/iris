from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.coin_metrics import CoinMetrics
from app.models.pattern_statistic import PatternStatistic
from app.models.signal import Signal
from app.schemas.coin import CoinCreate
from app.services.history_loader import create_coin


def create_test_coin(db: Session, *, symbol: str, name: str):
    return create_coin(
        db,
        CoinCreate(
            symbol=symbol,
            name=name,
            asset_type="crypto",
            theme="core",
            source="fixture",
        ),
    )


def upsert_coin_metrics(
    db: Session,
    *,
    coin_id: int,
    regime: str | None,
    timeframe: int = 15,
) -> CoinMetrics:
    row = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id))
    payload = {str(timeframe): {"regime": regime, "confidence": 0.82}} if regime is not None else None
    if row is None:
        row = CoinMetrics(
            coin_id=coin_id,
            price_current=100.0,
            adx_14=28.0,
            bb_width=0.08 if regime == "high_volatility" else 0.03 if regime == "sideways_range" else 0.05,
            atr_14=2.5,
            volume_24h=1_000_000.0,
            volume_change_24h=18.0,
            volatility=0.04,
            market_cap=5_000_000_000.0,
            market_regime=regime,
            market_regime_details=payload,
        )
        db.add(row)
    else:
        row.price_current = 100.0
        row.adx_14 = 28.0
        row.bb_width = 0.08 if regime == "high_volatility" else 0.03 if regime == "sideways_range" else 0.05
        row.atr_14 = 2.5
        row.volume_24h = 1_000_000.0
        row.volume_change_24h = 18.0
        row.volatility = 0.04
        row.market_cap = 5_000_000_000.0
        row.market_regime = regime
        row.market_regime_details = payload
    db.commit()
    db.refresh(row)
    return row


def replace_pattern_statistics(
    db: Session,
    *,
    timeframe: int,
    rows: list[tuple[str, str, float, int]],
) -> None:
    slugs = sorted({slug for slug, _, _, _ in rows})
    db.execute(
        delete(PatternStatistic).where(
            PatternStatistic.pattern_slug.in_(slugs),
            PatternStatistic.timeframe == timeframe,
        )
    )
    for slug, market_regime, success_rate, total_signals in rows:
        successful_signals = int(round(success_rate * total_signals))
        db.add(
            PatternStatistic(
                pattern_slug=slug,
                timeframe=timeframe,
                market_regime=market_regime,
                sample_size=total_signals,
                total_signals=total_signals,
                successful_signals=successful_signals,
                success_rate=success_rate,
                avg_return=0.03 if success_rate >= 0.5 else -0.02,
                avg_drawdown=-0.03,
                temperature=0.7 if success_rate >= 0.5 else -0.4,
                enabled=True,
            )
        )
    db.commit()


def insert_signals(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    candle_timestamp: datetime,
    items: list[tuple[str, float]],
) -> None:
    for signal_type, confidence in items:
        db.add(
            Signal(
                coin_id=coin_id,
                timeframe=timeframe,
                signal_type=signal_type,
                confidence=confidence,
                priority_score=confidence,
                context_score=1.0,
                regime_alignment=1.0,
                market_regime=None,
                candle_timestamp=candle_timestamp,
            )
        )
    db.commit()
