from collections.abc import Iterable
from dataclasses import dataclass

from src.apps.patterns.domain.base import PatternDetection
from src.apps.patterns.domain.utils import clamp

GLOBAL_MARKET_REGIME = "all"
PATTERN_SUCCESS_ROLLING_WINDOW = 200
MIN_SAMPLE_FOR_DEGRADE = 10
MIN_SAMPLE_FOR_DISABLE = 20
DISABLE_SUCCESS_RATE = 0.45
DEGRADE_SUCCESS_RATE = 0.55
BOOST_SUCCESS_RATE = 0.70


@dataclass(slots=True, frozen=True)
class PatternSuccessSnapshot:
    pattern_slug: str
    timeframe: int
    market_regime: str
    total_signals: int
    successful_signals: int
    success_rate: float
    avg_return: float
    avg_drawdown: float
    temperature: float
    enabled: bool


@dataclass(slots=True, frozen=True)
class PatternSuccessDecision:
    action: str
    factor: float
    snapshot: PatternSuccessSnapshot | None
    suppress: bool = False


def normalize_market_regime(market_regime: str | None) -> str:
    value = (market_regime or "").strip()
    return value if value else GLOBAL_MARKET_REGIME


def build_pattern_success_cache(
    snapshots: Iterable[PatternSuccessSnapshot],
) -> dict[tuple[str, str], PatternSuccessSnapshot]:
    return {
        (snapshot.pattern_slug, snapshot.market_regime): snapshot
        for snapshot in snapshots
    }


def load_pattern_success_snapshot(
    *,
    slug: str,
    timeframe: int,
    market_regime: str | None = None,
    snapshot_cache: dict[tuple[str, str], PatternSuccessSnapshot] | None = None,
) -> PatternSuccessSnapshot | None:
    del timeframe
    if snapshot_cache is None:
        return None
    normalized_regime = normalize_market_regime(market_regime)
    cached = snapshot_cache.get((slug, normalized_regime))
    if cached is not None:
        return cached
    return snapshot_cache.get((slug, GLOBAL_MARKET_REGIME))


def assess_pattern_success(
    *,
    slug: str,
    timeframe: int,
    market_regime: str | None = None,
    snapshot_cache: dict[tuple[str, str], PatternSuccessSnapshot] | None = None,
) -> PatternSuccessDecision:
    snapshot = load_pattern_success_snapshot(
        slug=slug,
        timeframe=timeframe,
        market_regime=market_regime,
        snapshot_cache=snapshot_cache,
    )
    if snapshot is None or snapshot.total_signals <= 0:
        return PatternSuccessDecision(action="neutral", factor=1.0, snapshot=snapshot)
    if not snapshot.enabled:
        return PatternSuccessDecision(action="disabled", factor=0.0, snapshot=snapshot, suppress=True)
    if snapshot.total_signals >= MIN_SAMPLE_FOR_DISABLE and snapshot.success_rate < DISABLE_SUCCESS_RATE:
        return PatternSuccessDecision(action="disabled", factor=0.0, snapshot=snapshot, suppress=True)
    if snapshot.total_signals >= MIN_SAMPLE_FOR_DEGRADE and snapshot.success_rate < DEGRADE_SUCCESS_RATE:
        factor = clamp(0.72 + max(snapshot.success_rate - 0.35, 0.0), 0.55, 0.9)
        return PatternSuccessDecision(action="degraded", factor=factor, snapshot=snapshot)
    if snapshot.total_signals >= MIN_SAMPLE_FOR_DEGRADE and snapshot.success_rate > BOOST_SUCCESS_RATE:
        factor = clamp(1.0 + min(snapshot.success_rate - BOOST_SUCCESS_RATE, 0.2), 1.03, 1.2)
        return PatternSuccessDecision(action="boosted", factor=factor, snapshot=snapshot)
    return PatternSuccessDecision(action="neutral", factor=1.0, snapshot=snapshot)


def publish_pattern_state_event(
    event_type: str,
    *,
    pattern_slug: str,
    timeframe: int,
    market_regime: str | None = None,
    timestamp: object | None = None,
    coin_id: int | None = None,
    confidence: float | None = None,
    factor: float | None = None,
    success_rate: float | None = None,
    total_signals: int | None = None,
) -> None:
    from src.runtime.streams.publisher import publish_event

    payload: dict[str, object] = {
        "coin_id": coin_id or 0,
        "timeframe": timeframe,
        "timestamp": timestamp,
        "pattern_slug": pattern_slug,
        "market_regime": market_regime,
    }
    if confidence is not None:
        payload["confidence"] = confidence
    if factor is not None:
        payload["factor"] = factor
    if success_rate is not None:
        payload["success_rate"] = success_rate
    if total_signals is not None:
        payload["total_signals"] = total_signals
    publish_event(event_type, payload)


def apply_pattern_success_validation(
    *,
    detection: PatternDetection,
    timeframe: int,
    market_regime: str | None,
    coin_id: int | None = None,
    emit_events: bool = True,
    snapshot_cache: dict[tuple[str, str], PatternSuccessSnapshot] | None = None,
) -> PatternDetection | None:
    decision = assess_pattern_success(
        slug=detection.slug,
        timeframe=timeframe,
        market_regime=market_regime,
        snapshot_cache=snapshot_cache,
    )
    snapshot = decision.snapshot
    if decision.suppress:
        if emit_events:
            publish_pattern_state_event(
                "pattern_disabled",
                pattern_slug=detection.slug,
                timeframe=timeframe,
                market_regime=market_regime,
                timestamp=detection.candle_timestamp,
                coin_id=coin_id,
                confidence=detection.confidence,
                factor=decision.factor,
                success_rate=snapshot.success_rate if snapshot is not None else None,
                total_signals=snapshot.total_signals if snapshot is not None else None,
            )
        return None

    adjusted_confidence = clamp(detection.confidence * decision.factor, 0.35, 0.99)
    if decision.action == "degraded" and adjusted_confidence < 0.4:
        if emit_events:
            publish_pattern_state_event(
                "pattern_degraded",
                pattern_slug=detection.slug,
                timeframe=timeframe,
                market_regime=market_regime,
                timestamp=detection.candle_timestamp,
                coin_id=coin_id,
                confidence=adjusted_confidence,
                factor=decision.factor,
                success_rate=snapshot.success_rate if snapshot is not None else None,
                total_signals=snapshot.total_signals if snapshot is not None else None,
            )
        return None

    if emit_events and decision.action in {"degraded", "boosted"}:
        publish_pattern_state_event(
            f"pattern_{decision.action}",
            pattern_slug=detection.slug,
            timeframe=timeframe,
            market_regime=market_regime,
            timestamp=detection.candle_timestamp,
            coin_id=coin_id,
            confidence=adjusted_confidence,
            factor=decision.factor,
            success_rate=snapshot.success_rate if snapshot is not None else None,
            total_signals=snapshot.total_signals if snapshot is not None else None,
        )

    attributes = {
        **detection.attributes,
        "pattern_success_factor": round(decision.factor, 4),
        "pattern_success_action": decision.action,
    }
    if snapshot is not None:
        attributes.update(
            {
                "pattern_success_rate": round(snapshot.success_rate, 4),
                "pattern_total_signals": snapshot.total_signals,
                "pattern_success_regime": snapshot.market_regime,
            }
        )
    return PatternDetection(
        slug=detection.slug,
        signal_type=detection.signal_type,
        confidence=adjusted_confidence,
        candle_timestamp=detection.candle_timestamp,
        category=detection.category,
        attributes=attributes,
    )


__all__ = [
    "BOOST_SUCCESS_RATE",
    "DEGRADE_SUCCESS_RATE",
    "DISABLE_SUCCESS_RATE",
    "GLOBAL_MARKET_REGIME",
    "MIN_SAMPLE_FOR_DEGRADE",
    "MIN_SAMPLE_FOR_DISABLE",
    "PATTERN_SUCCESS_ROLLING_WINDOW",
    "PatternSuccessDecision",
    "PatternSuccessSnapshot",
    "apply_pattern_success_validation",
    "assess_pattern_success",
    "build_pattern_success_cache",
    "load_pattern_success_snapshot",
    "normalize_market_regime",
    "publish_pattern_state_event",
]
