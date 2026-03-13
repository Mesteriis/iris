from __future__ import annotations

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


__all__ = [
    "MATERIAL_RISK_CONFIDENCE_DELTA",
    "MATERIAL_RISK_SCORE_DELTA",
    "RECENT_FINAL_SIGNAL_LOOKBACK_DAYS",
    "_final_signal_reason",
    "_risk_adjusted_decision",
    "_risk_confidence",
    "calculate_liquidity_score",
    "calculate_risk_adjusted_score",
    "calculate_slippage_risk",
    "calculate_volatility_risk",
]
