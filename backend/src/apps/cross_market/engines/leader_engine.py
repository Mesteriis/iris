from src.apps.cross_market.engines.contracts import (
    CrossMarketLeaderDetectionInput,
    CrossMarketLeaderDetectionResult,
)


def evaluate_market_leader(
    leader_input: CrossMarketLeaderDetectionInput,
) -> CrossMarketLeaderDetectionResult:
    bullish = leader_input.price_change_24h > 0
    directional_ok = (bullish and leader_input.market_regime in {"bull_trend", "high_volatility"}) or (
        (not bullish) and leader_input.market_regime == "bear_trend"
    )
    if (
        leader_input.activity_bucket != "HOT"
        or abs(leader_input.price_change_24h) < 2
        or leader_input.volume_change_24h < 12
        or not directional_ok
    ):
        return CrossMarketLeaderDetectionResult(status="skipped", reason="leader_threshold_not_met")

    confidence = max(
        0.45,
        min(
            0.45
            + min(abs(leader_input.price_change_24h) / 12, 0.2)
            + min(leader_input.volume_change_24h / 100, 0.2)
            + (0.1 if leader_input.activity_bucket == "HOT" else 0.0),
            0.95,
        ),
    )
    return CrossMarketLeaderDetectionResult(
        status="ok",
        direction="up" if bullish else "down",
        confidence=float(confidence),
    )


__all__ = ["evaluate_market_leader"]
