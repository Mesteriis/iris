from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.apps.indicators.models import CoinMetrics
from app.apps.patterns.models import PatternRegistry
from app.apps.patterns.models import PatternStatistic
from app.apps.signals.models import Signal
from app.apps.market_data.schemas import CoinCreate
from app.apps.market_data.service_layer import create_coin


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


def _pattern_category(slug: str) -> str:
    if slug in {"bull_flag", "bear_flag", "high_tight_flag"}:
        return "continuation"
    if slug in {"head_shoulders", "inverse_head_shoulders", "breakout_retest"}:
        return "structural"
    if slug.startswith("bollinger") or "volatility" in slug:
        return "volatility"
    if slug.endswith("cross") or slug.startswith("macd"):
        return "momentum"
    return "structural"


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
    registry_rows = {
        row.slug: row
        for row in db.scalars(select(PatternRegistry).where(PatternRegistry.slug.in_(slugs))).all()
    }
    for slug in slugs:
        registry_row = registry_rows.get(slug)
        if registry_row is None:
            db.add(
                PatternRegistry(
                    slug=slug,
                    category=_pattern_category(slug),
                    enabled=True,
                    cpu_cost=1,
                    lifecycle_state="ACTIVE",
                )
            )
            continue
        registry_row.enabled = True
        registry_row.lifecycle_state = "ACTIVE"
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
