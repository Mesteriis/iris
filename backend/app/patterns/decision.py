from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.messaging import publish_investment_decision_message
from app.models.coin import Coin
from app.models.coin_metrics import CoinMetrics
from app.models.investment_decision import InvestmentDecision
from app.models.market_cycle import MarketCycle
from app.models.pattern_statistic import PatternStatistic
from app.models.sector_metric import SectorMetric
from app.models.signal import Signal
from app.patterns.narrative import SectorNarrative, build_sector_narratives
from app.patterns.regime import read_regime_details
from app.patterns.semantics import is_cluster_signal, is_hierarchy_signal, is_pattern_signal, pattern_bias, slug_from_signal_type
from app.services.market_data import utc_now

DECISION_TYPES = [
    "STRONG_BUY",
    "BUY",
    "ACCUMULATE",
    "HOLD",
    "REDUCE",
    "SELL",
    "STRONG_SELL",
]
RECENT_DECISION_LOOKBACK_DAYS = 30
MATERIAL_SCORE_DELTA = 0.03
MATERIAL_CONFIDENCE_DELTA = 0.03


@dataclass(slots=True, frozen=True)
class DecisionFactors:
    signal_priority: float
    regime_alignment: float
    sector_strength: float
    cycle_alignment: float
    historical_pattern_success: float


def calculate_decision_score(
    *,
    signal_priority: float,
    regime_alignment: float,
    sector_strength: float,
    cycle_alignment: float,
    historical_pattern_success: float,
) -> float:
    return max(
        signal_priority
        * regime_alignment
        * sector_strength
        * cycle_alignment
        * historical_pattern_success,
        0.0,
    )


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _latest_pattern_timestamp(db: Session, coin_id: int, timeframe: int) -> object | None:
    return db.scalar(
        select(func.max(Signal.candle_timestamp)).where(
            Signal.coin_id == coin_id,
            Signal.timeframe == timeframe,
            Signal.signal_type.like("pattern_%"),
        )
    )


def _latest_signal_stack(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    candle_timestamp: object,
) -> list[Signal]:
    return db.scalars(
        select(Signal).where(
            Signal.coin_id == coin_id,
            Signal.timeframe == timeframe,
            Signal.candle_timestamp == candle_timestamp,
            Signal.signal_type.like("pattern_%"),
        )
    ).all()


def _regime_alignment(signals: Sequence[Signal]) -> float:
    if not signals:
        return 1.0
    return sum(float(signal.regime_alignment or 1.0) for signal in signals) / len(signals)


def _cycle_alignment(cycle: MarketCycle | None, bias: int) -> float:
    if cycle is None:
        return 1.0
    if cycle.cycle_phase in {"ACCUMULATION", "EARLY_MARKUP", "MARKUP"}:
        return 1.18 if bias > 0 else 0.82
    if cycle.cycle_phase == "LATE_MARKUP":
        return 0.95 if bias > 0 else 1.06
    if cycle.cycle_phase in {"DISTRIBUTION", "EARLY_MARKDOWN", "MARKDOWN", "CAPITULATION"}:
        return 1.18 if bias < 0 else 0.82
    return 1.0


def _sector_strength_factor(
    coin: Coin,
    metrics: CoinMetrics | None,
    sector_metric: SectorMetric | None,
    narrative: SectorNarrative | None,
) -> float:
    if sector_metric is None:
        return 1.0
    factor = 1.0
    factor += _clamp(float(sector_metric.sector_strength) * 3.0, -0.2, 0.2)
    factor += _clamp(float(sector_metric.relative_strength) * 3.0, -0.15, 0.15)
    if narrative is not None and coin.sector is not None and narrative.top_sector == coin.sector.name:
        factor += 0.05
    market_cap = float(metrics.market_cap or 0.0) if metrics is not None else 0.0
    if narrative is not None:
        if narrative.capital_wave == "btc" and coin.symbol != "BTCUSD":
            factor -= 0.05
        elif narrative.capital_wave == "large_caps" and market_cap >= 10_000_000_000:
            factor += 0.05
        elif narrative.capital_wave == "sector_leaders" and coin.sector is not None and narrative.top_sector == coin.sector.name:
            factor += 0.05
        elif narrative.capital_wave == "mid_caps" and 1_000_000_000 <= market_cap < 10_000_000_000:
            factor += 0.04
        elif narrative.capital_wave == "micro_caps" and 0 < market_cap < 500_000_000:
            factor += 0.05
    return _clamp(factor, 0.65, 1.35)


def _historical_pattern_success(db: Session, slugs: set[str], timeframe: int) -> float:
    if not slugs:
        return 0.55
    rows = db.execute(
        select(PatternStatistic.success_rate).where(
            PatternStatistic.pattern_slug.in_(sorted(slugs)),
            PatternStatistic.timeframe == timeframe,
        )
    ).all()
    values = [float(row.success_rate) for row in rows if row.success_rate is not None]
    if not values:
        return 0.55
    return _clamp(sum(values) / len(values), 0.35, 0.95)


def _decision_from_score(score: float, bias_ratio: float) -> str:
    if abs(bias_ratio) < 0.18 or score < 0.45:
        return "HOLD"
    if bias_ratio > 0:
        if score >= 1.65 and abs(bias_ratio) >= 0.55:
            return "STRONG_BUY"
        if score >= 1.1:
            return "BUY"
        return "ACCUMULATE"
    if score >= 1.65 and abs(bias_ratio) >= 0.55:
        return "STRONG_SELL"
    if score >= 1.1:
        return "SELL"
    return "REDUCE"


def _decision_confidence(score: float, bias_ratio: float, factors: DecisionFactors) -> float:
    base = _clamp(score / 2.5, 0.0, 0.98)
    directionality = 0.55 + min(abs(bias_ratio), 1.0) * 0.45
    stability = _clamp(
        (factors.regime_alignment + factors.cycle_alignment + factors.historical_pattern_success + factors.sector_strength) / 4,
        0.5,
        1.2,
    )
    return _clamp(base * directionality * stability, 0.05, 0.99)


def _latest_decision(db: Session, coin_id: int, timeframe: int) -> InvestmentDecision | None:
    return db.scalar(
        select(InvestmentDecision)
        .where(InvestmentDecision.coin_id == coin_id, InvestmentDecision.timeframe == timeframe)
        .order_by(InvestmentDecision.created_at.desc(), InvestmentDecision.id.desc())
        .limit(1)
    )


def _decision_reason(
    *,
    decision: str,
    score: float,
    bias_ratio: float,
    signals: Sequence[Signal],
    regime: str | None,
    sector_metric: SectorMetric | None,
    narrative: SectorNarrative | None,
    cycle: MarketCycle | None,
    historical_pattern_success: float,
) -> str:
    cluster_count = sum(1 for signal in signals if is_cluster_signal(signal.signal_type))
    hierarchy_count = sum(1 for signal in signals if is_hierarchy_signal(signal.signal_type))
    base_patterns = sum(1 for signal in signals if is_pattern_signal(signal.signal_type))
    bias_label = "bullish" if bias_ratio > 0.18 else "bearish" if bias_ratio < -0.18 else "neutral"
    sector_strength = float(sector_metric.sector_strength) if sector_metric is not None else 0.0
    capital_wave = narrative.capital_wave if narrative is not None else None
    top_sector = narrative.top_sector if narrative is not None else None
    return (
        f"{decision}: {bias_label} stack {base_patterns} patterns/{cluster_count} clusters/{hierarchy_count} hierarchies; "
        f"regime={regime or 'unknown'}; "
        f"cycle={cycle.cycle_phase if cycle is not None else 'unknown'}; "
        f"sector_strength={sector_strength:.4f}; "
        f"top_sector={top_sector or 'n/a'}; "
        f"capital_wave={capital_wave or 'n/a'}; "
        f"historical_success={historical_pattern_success:.2f}; "
        f"score={score:.3f}"
    )


def evaluate_investment_decision(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    narratives_by_timeframe: dict[int, SectorNarrative] | None = None,
    emit_event: bool = True,
) -> dict[str, object]:
    latest_timestamp = _latest_pattern_timestamp(db, coin_id, timeframe)
    if latest_timestamp is None:
        return {"status": "skipped", "reason": "pattern_signals_not_found", "coin_id": coin_id, "timeframe": timeframe}

    signals = _latest_signal_stack(db, coin_id=coin_id, timeframe=timeframe, candle_timestamp=latest_timestamp)
    if not signals:
        return {"status": "skipped", "reason": "signal_stack_not_found", "coin_id": coin_id, "timeframe": timeframe}

    coin = db.get(Coin, coin_id)
    if coin is None:
        return {"status": "skipped", "reason": "coin_not_found", "coin_id": coin_id, "timeframe": timeframe}
    metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id))
    cycle = db.get(MarketCycle, (coin_id, timeframe))
    sector_metric = db.get(SectorMetric, (coin.sector_id, timeframe)) if coin.sector_id is not None else None
    narrative = narratives_by_timeframe.get(timeframe) if narratives_by_timeframe is not None else None
    if narrative is None:
        narrative = next((item for item in build_sector_narratives(db) if item.timeframe == timeframe), None)

    relevant_signals = [signal for signal in signals if signal.signal_type.startswith("pattern_")]
    weights = [max(float(signal.priority_score or signal.confidence), 0.01) for signal in relevant_signals]
    signal_priority = sum(sorted(weights, reverse=True)[:5]) / max(min(len(weights), 5), 1)

    signed_weight = 0.0
    pattern_slugs: set[str] = set()
    for signal in relevant_signals:
        slug = slug_from_signal_type(signal.signal_type)
        if slug is not None and is_pattern_signal(signal.signal_type):
            pattern_slugs.add(slug)
        weight = max(float(signal.priority_score or signal.confidence), 0.01)
        signed_weight += weight * pattern_bias(slug or signal.signal_type, fallback_price_delta=signal.confidence - 0.5)

    total_weight = sum(weights)
    bias_ratio = signed_weight / max(total_weight, 1e-9)
    bias = 1 if bias_ratio > 0 else -1 if bias_ratio < 0 else 0
    regime_snapshot = (
        read_regime_details(metrics.market_regime_details, timeframe)
        if metrics is not None and metrics.market_regime_details
        else None
    )
    regime = regime_snapshot.regime if regime_snapshot is not None else (metrics.market_regime if metrics is not None else None)
    regime_alignment = _regime_alignment(relevant_signals)
    sector_strength = _sector_strength_factor(coin, metrics, sector_metric, narrative)
    cycle_alignment = _cycle_alignment(cycle, bias)
    historical_pattern_success = _historical_pattern_success(db, pattern_slugs, timeframe)
    factors = DecisionFactors(
        signal_priority=signal_priority,
        regime_alignment=regime_alignment,
        sector_strength=sector_strength,
        cycle_alignment=cycle_alignment,
        historical_pattern_success=historical_pattern_success,
    )
    score = calculate_decision_score(
        signal_priority=factors.signal_priority,
        regime_alignment=factors.regime_alignment,
        sector_strength=factors.sector_strength,
        cycle_alignment=factors.cycle_alignment,
        historical_pattern_success=factors.historical_pattern_success,
    )
    decision = _decision_from_score(score, bias_ratio)
    confidence = _decision_confidence(score, bias_ratio, factors)
    reason = _decision_reason(
        decision=decision,
        score=score,
        bias_ratio=bias_ratio,
        signals=relevant_signals,
        regime=regime,
        sector_metric=sector_metric,
        narrative=narrative,
        cycle=cycle,
        historical_pattern_success=historical_pattern_success,
    )

    latest_decision = _latest_decision(db, coin_id, timeframe)
    if (
        latest_decision is not None
        and latest_decision.decision == decision
        and abs(float(latest_decision.score) - score) < MATERIAL_SCORE_DELTA
        and abs(float(latest_decision.confidence) - confidence) < MATERIAL_CONFIDENCE_DELTA
        and latest_decision.reason == reason
    ):
        return {
            "status": "skipped",
            "reason": "decision_unchanged",
            "coin_id": coin_id,
            "timeframe": timeframe,
            "decision": decision,
            "score": score,
        }

    row = InvestmentDecision(
        coin_id=coin_id,
        timeframe=timeframe,
        decision=decision,
        confidence=confidence,
        score=score,
        reason=reason,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    if emit_event:
        publish_investment_decision_message(
            coin,
            timeframe=timeframe,
            decision=decision,
            confidence=confidence,
            score=score,
            reason=reason,
        )
    return {
        "status": "ok",
        "id": row.id,
        "coin_id": coin_id,
        "timeframe": timeframe,
        "decision": decision,
        "confidence": confidence,
        "score": score,
    }


def _decision_candidates(db: Session, *, lookback_days: int) -> list[tuple[int, int]]:
    cutoff = utc_now() - timedelta(days=max(lookback_days, 1))
    rows = db.execute(
        select(Signal.coin_id, Signal.timeframe)
        .where(
            Signal.signal_type.like("pattern_%"),
            Signal.candle_timestamp >= cutoff,
        )
        .distinct()
        .order_by(Signal.coin_id.asc(), Signal.timeframe.asc())
    ).all()
    return [(int(row.coin_id), int(row.timeframe)) for row in rows]


def refresh_investment_decisions(
    db: Session,
    *,
    lookback_days: int = RECENT_DECISION_LOOKBACK_DAYS,
    emit_events: bool = False,
) -> dict[str, object]:
    candidates = _decision_candidates(db, lookback_days=lookback_days)
    narratives_by_timeframe = {item.timeframe: item for item in build_sector_narratives(db)}
    items = [
        evaluate_investment_decision(
            db,
            coin_id=coin_id,
            timeframe=timeframe,
            narratives_by_timeframe=narratives_by_timeframe,
            emit_event=emit_events,
        )
        for coin_id, timeframe in candidates
    ]
    return {
        "status": "ok",
        "items": items,
        "updated": sum(1 for item in items if item.get("status") == "ok"),
        "candidates": len(candidates),
    }
