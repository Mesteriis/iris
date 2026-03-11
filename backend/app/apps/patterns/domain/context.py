from __future__ import annotations

from datetime import datetime
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.apps.market_data.models import Coin
from app.apps.indicators.models import CoinMetrics
from app.apps.patterns.models import MarketCycle
from app.apps.patterns.models import PatternStatistic
from app.apps.cross_market.models import SectorMetric
from app.apps.signals.models import Signal
from app.apps.patterns.domain.regime import read_regime_details
from app.apps.patterns.domain.semantics import is_cluster_signal, is_pattern_signal, pattern_bias, slug_from_signal_type
from app.apps.patterns.domain.success import load_pattern_success_snapshot
from app.apps.market_data.domain import ensure_utc, utc_now
from app.apps.patterns.cache import read_cached_regime


def calculate_priority_score(
    *,
    confidence: float,
    pattern_temperature: float,
    regime_alignment: float,
    volatility_alignment: float,
    liquidity_score: float,
) -> float:
    return max(confidence * pattern_temperature * regime_alignment * volatility_alignment * liquidity_score, 0.0)


def _regime_alignment(regime: str | None, bias: int) -> float:
    if regime in {"bull_trend", "bull_market"}:
        return 1.25 if bias > 0 else 0.75
    if regime in {"bear_trend", "bear_market"}:
        return 1.25 if bias < 0 else 0.75
    if regime in {"sideways_range", "accumulation"}:
        return 1.05 if bias > 0 else 0.95
    if regime in {"distribution", "high_volatility"}:
        return 1.1 if bias < 0 else 0.85
    if regime == "low_volatility":
        return 1.05
    return 1.0


def _volatility_alignment(signal_type: str, metrics: CoinMetrics | None) -> float:
    bb_width = float(metrics.bb_width or 0.0) if metrics is not None else 0.0
    volatility = float(metrics.volatility or 0.0) if metrics is not None else 0.0
    if signal_type.endswith("bollinger_squeeze"):
        return 1.15 if bb_width < 0.05 else 0.9
    if signal_type.endswith("atr_spike") or signal_type.endswith("bollinger_expansion"):
        return 1.15 if volatility > 0 else 1.0
    if volatility > 0 and bb_width > 0.08:
        return 1.08
    return 1.0


def _liquidity_score(metrics: CoinMetrics | None) -> float:
    if metrics is None:
        return 1.0
    volume_change = float(metrics.volume_change_24h or 0.0)
    market_cap = float(metrics.market_cap or 0.0)
    score = 1.0
    if volume_change > 20:
        score += 0.15
    elif volume_change < -20:
        score -= 0.15
    if market_cap > 10_000_000_000:
        score += 0.1
    elif 0 < market_cap < 500_000_000:
        score -= 0.1
    return max(score, 0.4)


def _sector_alignment(sector_metric: SectorMetric | None, bias: int) -> float:
    if sector_metric is None:
        return 1.0
    if sector_metric.sector_strength > 0 and bias > 0:
        return 1.12
    if sector_metric.sector_strength < 0 and bias < 0:
        return 1.12
    if sector_metric.relative_strength < 0 and bias > 0:
        return 0.88
    if sector_metric.relative_strength > 0 and bias < 0:
        return 0.88
    return 1.0


def _cycle_alignment(cycle: MarketCycle | None, bias: int) -> float:
    if cycle is None:
        return 1.0
    if cycle.cycle_phase in {"ACCUMULATION", "EARLY_MARKUP", "MARKUP"}:
        return 1.15 if bias > 0 else 0.82
    if cycle.cycle_phase in {"DISTRIBUTION", "EARLY_MARKDOWN", "MARKDOWN", "CAPITULATION"}:
        return 1.15 if bias < 0 else 0.82
    if cycle.cycle_phase == "LATE_MARKUP":
        return 0.92 if bias > 0 else 1.05
    return 1.0


def _pattern_temperature(db: Session, slug: str | None, timeframe: int, regime: str | None = None) -> float:
    if slug is None:
        return 1.0
    snapshot = load_pattern_success_snapshot(
        db,
        slug=slug,
        timeframe=timeframe,
        market_regime=regime,
    )
    if snapshot is None:
        return 1.0
    return float(snapshot.temperature) if snapshot.temperature != 0 else 1.0


def _signal_regime(metrics: CoinMetrics | None, timeframe: int) -> str | None:
    if metrics is not None:
        cached = read_cached_regime(coin_id=metrics.coin_id, timeframe=timeframe)
        if cached is not None:
            return cached.regime
    if metrics is None:
        return None
    detailed = read_regime_details(metrics.market_regime_details, timeframe)
    return detailed.regime if detailed is not None else metrics.market_regime


def enrich_signal_context(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    candle_timestamp: object | None = None,
    commit: bool = True,
) -> dict[str, object]:
    stmt = select(Signal).where(Signal.coin_id == coin_id, Signal.timeframe == timeframe)
    if candle_timestamp is not None:
        normalized_timestamp = (
            ensure_utc(datetime.fromisoformat(candle_timestamp))
            if isinstance(candle_timestamp, str)
            else candle_timestamp
        )
        stmt = stmt.where(Signal.candle_timestamp == normalized_timestamp)
    signals = db.scalars(stmt).all()
    if not signals:
        return {"status": "skipped", "reason": "signals_not_found", "coin_id": coin_id, "timeframe": timeframe}

    metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id))
    coin = db.get(Coin, coin_id)
    sector_metric = db.get(SectorMetric, (coin.sector_id, timeframe)) if coin is not None and coin.sector_id is not None else None
    cycle = db.get(MarketCycle, (coin_id, timeframe))
    cluster_timestamps = {
        signal.candle_timestamp
        for signal in signals
        if is_cluster_signal(signal.signal_type)
    }
    for signal in signals:
        slug = slug_from_signal_type(signal.signal_type)
        bias = pattern_bias(slug or signal.signal_type, fallback_price_delta=signal.confidence - 0.5)
        regime_alignment = _regime_alignment(_signal_regime(metrics, signal.timeframe), bias)
        signal_regime = signal.market_regime or _signal_regime(metrics, signal.timeframe)
        volatility_alignment = _volatility_alignment(signal.signal_type, metrics)
        liquidity_score = _liquidity_score(metrics)
        sector_alignment = _sector_alignment(sector_metric, bias)
        cycle_alignment = _cycle_alignment(cycle, bias)
        temperature = _pattern_temperature(db, slug, signal.timeframe, signal_regime)
        cluster_bonus = 1.15 if signal.candle_timestamp in cluster_timestamps and is_pattern_signal(signal.signal_type) else 1.0
        context_score = max(
            temperature * volatility_alignment * liquidity_score * cluster_bonus * sector_alignment * cycle_alignment,
            0.0,
        )
        signal.regime_alignment = regime_alignment
        signal.context_score = context_score
        signal.priority_score = calculate_priority_score(
            confidence=signal.confidence,
            pattern_temperature=temperature,
            regime_alignment=regime_alignment,
            volatility_alignment=volatility_alignment * cluster_bonus * sector_alignment * cycle_alignment,
            liquidity_score=liquidity_score,
        )
    if commit:
        db.commit()
    return {
        "status": "ok",
        "coin_id": coin_id,
        "timeframe": timeframe,
        "signals": len(signals),
    }


def refresh_recent_signal_contexts(
    db: Session,
    *,
    lookback_days: int = 30,
) -> dict[str, object]:
    recent_cutoff = utc_now() - timedelta(days=max(lookback_days, 1))
    rows = db.execute(
        select(Signal.coin_id, Signal.timeframe, Signal.candle_timestamp)
        .where(Signal.candle_timestamp >= recent_cutoff)
        .distinct()
        .order_by(Signal.coin_id.asc(), Signal.timeframe.asc(), Signal.candle_timestamp.asc())
    ).all()
    updated = 0
    for row in rows:
        result = enrich_signal_context(
            db,
            coin_id=int(row.coin_id),
            timeframe=int(row.timeframe),
            candle_timestamp=row.candle_timestamp,
            commit=False,
        )
        updated += int(result.get("signals", 0))
    db.commit()
    return {"status": "ok", "signals": updated, "groups": len(rows)}
