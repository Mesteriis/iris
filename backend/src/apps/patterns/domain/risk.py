from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.runtime.streams.messages import publish_investment_signal_message
from src.apps.market_data.models import Candle
from src.apps.market_data.models import Coin
from src.apps.indicators.models import CoinMetrics
from src.apps.signals.models import FinalSignal
from src.apps.indicators.models import IndicatorCache
from src.apps.signals.models import InvestmentDecision
from src.apps.signals.models import RiskMetric
from src.apps.market_data.domain import utc_now

RECENT_FINAL_SIGNAL_LOOKBACK_DAYS = 30
MATERIAL_RISK_SCORE_DELTA = 0.02
MATERIAL_RISK_CONFIDENCE_DELTA = 0.02

_BULLISH_STRENGTH = {
    "ACCUMULATE": 1,
    "BUY": 2,
    "STRONG_BUY": 3,
}
_BEARISH_STRENGTH = {
    "REDUCE": 1,
    "SELL": 2,
    "STRONG_SELL": 3,
}
_BULLISH_BY_STRENGTH = {
    1: "ACCUMULATE",
    2: "BUY",
    3: "STRONG_BUY",
}
_BEARISH_BY_STRENGTH = {
    1: "REDUCE",
    2: "SELL",
    3: "STRONG_SELL",
}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def calculate_liquidity_score(*, volume_24h: float, market_cap: float) -> float:
    if volume_24h <= 0 and market_cap <= 0:
        return 0.1
    volume_score = _clamp((max(volume_24h, 1.0) ** 0.18) / 40.0, 0.0, 1.0)
    market_cap_score = _clamp((max(market_cap, 1.0) ** 0.12) / 20.0, 0.0, 1.0)
    return _clamp((volume_score * 0.65) + (market_cap_score * 0.35), 0.1, 1.0)


def calculate_slippage_risk(*, volume_24h: float, market_cap: float) -> float:
    liquidity = max((market_cap * 0.1) + volume_24h, 1.0)
    activity_ratio = volume_24h / liquidity
    return _clamp(1.0 - (activity_ratio * 4.0), 0.02, 0.98)


def calculate_volatility_risk(*, atr_14: float, price: float) -> float:
    if price <= 0 or atr_14 <= 0:
        return 0.5
    atr_ratio = atr_14 / price
    return _clamp(atr_ratio / 0.12, 0.01, 0.98)


def calculate_risk_adjusted_score(
    *,
    decision_score: float,
    liquidity_score: float,
    slippage_risk: float,
    volatility_risk: float,
) -> float:
    return max(
        decision_score
        * liquidity_score
        * (1.0 - slippage_risk)
        * (1.0 - volatility_risk),
        0.0,
    )


def _latest_decision(db: Session, coin_id: int, timeframe: int) -> InvestmentDecision | None:
    return db.scalar(
        select(InvestmentDecision)
        .where(
            InvestmentDecision.coin_id == coin_id,
            InvestmentDecision.timeframe == timeframe,
        )
        .order_by(InvestmentDecision.created_at.desc(), InvestmentDecision.id.desc())
        .limit(1)
    )


def _latest_final_signal(db: Session, coin_id: int, timeframe: int) -> FinalSignal | None:
    return db.scalar(
        select(FinalSignal)
        .where(FinalSignal.coin_id == coin_id, FinalSignal.timeframe == timeframe)
        .order_by(FinalSignal.created_at.desc(), FinalSignal.id.desc())
        .limit(1)
    )


def _latest_close(db: Session, coin_id: int, timeframe: int) -> float | None:
    value = db.scalar(
        select(Candle.close)
        .where(Candle.coin_id == coin_id, Candle.timeframe == timeframe)
        .order_by(Candle.timestamp.desc())
        .limit(1)
    )
    return float(value) if value is not None else None


def _latest_indicator_value(db: Session, coin_id: int, timeframe: int, indicator: str) -> float | None:
    value = db.scalar(
        select(IndicatorCache.value)
        .where(
            IndicatorCache.coin_id == coin_id,
            IndicatorCache.timeframe == timeframe,
            IndicatorCache.indicator == indicator,
        )
        .order_by(IndicatorCache.timestamp.desc(), IndicatorCache.id.desc())
        .limit(1)
    )
    return float(value) if value is not None else None


def _upsert_risk_metric(db: Session, *, coin_id: int, timeframe: int) -> tuple[RiskMetric, dict[str, float]]:
    metrics = db.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id))
    volume_24h = float(metrics.volume_24h or 0.0) if metrics is not None else 0.0
    market_cap = float(metrics.market_cap or 0.0) if metrics is not None else 0.0
    atr_14 = _latest_indicator_value(db, coin_id, timeframe, "atr_14")
    if atr_14 is None and metrics is not None:
        atr_14 = float(metrics.atr_14 or 0.0)
    price = _latest_close(db, coin_id, timeframe)
    if price is None and metrics is not None:
        price = float(metrics.price_current or 0.0)

    liquidity_score = calculate_liquidity_score(volume_24h=volume_24h, market_cap=market_cap)
    slippage_risk = calculate_slippage_risk(volume_24h=volume_24h, market_cap=market_cap)
    volatility_risk = calculate_volatility_risk(atr_14=float(atr_14 or 0.0), price=float(price or 0.0))

    row = db.get(RiskMetric, (coin_id, timeframe))
    if row is None:
        row = RiskMetric(coin_id=coin_id, timeframe=timeframe)
        db.add(row)
    row.liquidity_score = liquidity_score
    row.slippage_risk = slippage_risk
    row.volatility_risk = volatility_risk
    row.updated_at = utc_now()
    return row, {
        "liquidity_score": liquidity_score,
        "slippage_risk": slippage_risk,
        "volatility_risk": volatility_risk,
    }


def update_risk_metrics(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    commit: bool = True,
) -> dict[str, object]:
    coin = db.get(Coin, coin_id)
    if coin is None:
        return {"status": "skipped", "reason": "coin_not_found", "coin_id": coin_id, "timeframe": timeframe}

    _, payload = _upsert_risk_metric(db, coin_id=coin_id, timeframe=timeframe)
    if commit:
        db.commit()
    return {
        "status": "ok",
        "coin_id": coin_id,
        "timeframe": timeframe,
        **payload,
    }


def _risk_adjusted_decision(decision: str, risk_adjusted_score: float) -> str:
    if decision in _BULLISH_STRENGTH:
        max_strength = _BULLISH_STRENGTH[decision]
        if risk_adjusted_score < 0.32:
            return "HOLD"
        if max_strength >= 3 and risk_adjusted_score >= 1.35:
            return _BULLISH_BY_STRENGTH[3]
        if max_strength >= 2 and risk_adjusted_score >= 0.8:
            return _BULLISH_BY_STRENGTH[2]
        return _BULLISH_BY_STRENGTH[1]
    if decision in _BEARISH_STRENGTH:
        max_strength = _BEARISH_STRENGTH[decision]
        if risk_adjusted_score < 0.32:
            return "HOLD"
        if max_strength >= 3 and risk_adjusted_score >= 1.35:
            return _BEARISH_BY_STRENGTH[3]
        if max_strength >= 2 and risk_adjusted_score >= 0.8:
            return _BEARISH_BY_STRENGTH[2]
        return _BEARISH_BY_STRENGTH[1]
    return "HOLD"


def _risk_confidence(
    *,
    base_confidence: float,
    liquidity_score: float,
    slippage_risk: float,
    volatility_risk: float,
) -> float:
    risk_factor = liquidity_score * (1.0 - slippage_risk) * (1.0 - volatility_risk)
    return _clamp(base_confidence * (0.55 + (risk_factor * 0.45)), 0.05, 0.99)


def _final_signal_reason(
    *,
    decision: str,
    base_decision: str,
    decision_score: float,
    risk_adjusted_score: float,
    liquidity_score: float,
    slippage_risk: float,
    volatility_risk: float,
) -> str:
    return (
        f"{decision}: base_decision={base_decision}; "
        f"decision_score={decision_score:.3f}; "
        f"liquidity_score={liquidity_score:.3f}; "
        f"slippage_risk={slippage_risk:.3f}; "
        f"volatility_risk={volatility_risk:.3f}; "
        f"risk_adjusted_score={risk_adjusted_score:.3f}"
    )


def evaluate_final_signal(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    emit_event: bool = True,
) -> dict[str, object]:
    coin = db.get(Coin, coin_id)
    if coin is None:
        return {"status": "skipped", "reason": "coin_not_found", "coin_id": coin_id, "timeframe": timeframe}

    latest_decision = _latest_decision(db, coin_id, timeframe)
    if latest_decision is None:
        return {"status": "skipped", "reason": "decision_not_found", "coin_id": coin_id, "timeframe": timeframe}

    _, metrics_payload = _upsert_risk_metric(db, coin_id=coin_id, timeframe=timeframe)
    risk_adjusted_score = calculate_risk_adjusted_score(
        decision_score=float(latest_decision.score),
        liquidity_score=float(metrics_payload["liquidity_score"]),
        slippage_risk=float(metrics_payload["slippage_risk"]),
        volatility_risk=float(metrics_payload["volatility_risk"]),
    )
    decision = _risk_adjusted_decision(str(latest_decision.decision), risk_adjusted_score)
    confidence = _risk_confidence(
        base_confidence=float(latest_decision.confidence),
        liquidity_score=float(metrics_payload["liquidity_score"]),
        slippage_risk=float(metrics_payload["slippage_risk"]),
        volatility_risk=float(metrics_payload["volatility_risk"]),
    )
    reason = _final_signal_reason(
        decision=decision,
        base_decision=str(latest_decision.decision),
        decision_score=float(latest_decision.score),
        risk_adjusted_score=risk_adjusted_score,
        liquidity_score=float(metrics_payload["liquidity_score"]),
        slippage_risk=float(metrics_payload["slippage_risk"]),
        volatility_risk=float(metrics_payload["volatility_risk"]),
    )

    latest_signal = _latest_final_signal(db, coin_id, timeframe)
    if (
        latest_signal is not None
        and latest_signal.decision == decision
        and abs(float(latest_signal.risk_adjusted_score) - risk_adjusted_score) < MATERIAL_RISK_SCORE_DELTA
        and abs(float(latest_signal.confidence) - confidence) < MATERIAL_RISK_CONFIDENCE_DELTA
        and latest_signal.reason == reason
    ):
        db.commit()
        return {
            "status": "skipped",
            "reason": "final_signal_unchanged",
            "coin_id": coin_id,
            "timeframe": timeframe,
            "decision": decision,
            "risk_adjusted_score": risk_adjusted_score,
        }

    row = FinalSignal(
        coin_id=coin_id,
        timeframe=timeframe,
        decision=decision,
        confidence=confidence,
        risk_adjusted_score=risk_adjusted_score,
        reason=reason,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    if emit_event:
        publish_investment_signal_message(
            coin,
            timeframe=timeframe,
            decision=decision,
            confidence=confidence,
            risk_score=risk_adjusted_score,
            reason=reason,
        )
    return {
        "status": "ok",
        "id": row.id,
        "coin_id": coin_id,
        "timeframe": timeframe,
        "decision": decision,
        "confidence": confidence,
        "risk_adjusted_score": risk_adjusted_score,
    }


def _final_signal_candidates(db: Session, *, lookback_days: int) -> list[tuple[int, int]]:
    cutoff = utc_now() - timedelta(days=max(lookback_days, 1))
    rows = db.execute(
        select(InvestmentDecision.coin_id, InvestmentDecision.timeframe)
        .where(InvestmentDecision.created_at >= cutoff)
        .distinct()
        .order_by(InvestmentDecision.coin_id.asc(), InvestmentDecision.timeframe.asc())
    ).all()
    return [(int(row.coin_id), int(row.timeframe)) for row in rows]


def refresh_final_signals(
    db: Session,
    *,
    lookback_days: int = RECENT_FINAL_SIGNAL_LOOKBACK_DAYS,
    emit_events: bool = False,
) -> dict[str, object]:
    candidates = _final_signal_candidates(db, lookback_days=lookback_days)
    items = [
        evaluate_final_signal(
            db,
            coin_id=coin_id,
            timeframe=timeframe,
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
