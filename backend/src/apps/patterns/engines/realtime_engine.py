from src.apps.patterns.domain.cycle import _detect_cycle_phase
from src.apps.patterns.domain.semantics import (
    BEARISH_PATTERN_SLUGS,
    BULLISH_PATTERN_SLUGS,
    is_cluster_signal,
    is_pattern_signal,
    slug_from_signal_type,
)
from src.apps.patterns.engines.contracts import (
    PatternCoinMetricsSnapshot,
    PatternCycleComputation,
    PatternCycleEngineInput,
    PatternRuntimeSignalSnapshot,
    PatternSignalInsertSpec,
)


def build_pattern_cluster_specs(
    *,
    signals: tuple[PatternRuntimeSignalSnapshot, ...],
    metrics: PatternCoinMetricsSnapshot | None,
) -> tuple[PatternSignalInsertSpec, ...]:
    if metrics is None:
        return ()
    pattern_signals = tuple(signal for signal in signals if is_pattern_signal(signal.signal_type))
    if not pattern_signals:
        return ()
    bullish = tuple(
        signal
        for signal in pattern_signals
        if (slug_from_signal_type(signal.signal_type) or "") in BULLISH_PATTERN_SLUGS
    )
    bearish = tuple(
        signal
        for signal in pattern_signals
        if (slug_from_signal_type(signal.signal_type) or "") in BEARISH_PATTERN_SLUGS
    )
    specs: list[PatternSignalInsertSpec] = []
    if bullish and any(signal.signal_type == "pattern_volume_spike" for signal in pattern_signals) and int(metrics.trend_score or 0) >= 60:
        specs.append(
            PatternSignalInsertSpec(
                signal_type="pattern_cluster_bullish",
                confidence=min(sum(signal.confidence for signal in bullish) / len(bullish) + 0.12, 0.95),
                market_regime=metrics.market_regime,
            )
        )
    if bearish and any(
        signal.signal_type in {"pattern_volume_spike", "pattern_volume_climax"} for signal in pattern_signals
    ) and int(metrics.trend_score or 100) <= 40:
        specs.append(
            PatternSignalInsertSpec(
                signal_type="pattern_cluster_bearish",
                confidence=min(sum(signal.confidence for signal in bearish) / len(bearish) + 0.12, 0.95),
                market_regime=metrics.market_regime,
            )
        )
    return tuple(specs)


def build_pattern_hierarchy_specs(
    *,
    signals: tuple[PatternRuntimeSignalSnapshot, ...],
    has_cluster_signals: bool,
    metrics: PatternCoinMetricsSnapshot | None,
) -> tuple[PatternSignalInsertSpec, ...]:
    if metrics is None:
        return ()
    pattern_signals = tuple(signal for signal in signals if is_pattern_signal(signal.signal_type))
    if not pattern_signals:
        return ()
    bullish = sum(
        1
        for signal in pattern_signals
        if (slug_from_signal_type(signal.signal_type) or "") in BULLISH_PATTERN_SLUGS
    )
    bearish = sum(
        1
        for signal in pattern_signals
        if (slug_from_signal_type(signal.signal_type) or "") in BEARISH_PATTERN_SLUGS
    )
    exhaustion = sum(
        1
        for signal in pattern_signals
        if signal.signal_type in {"pattern_momentum_exhaustion", "pattern_volume_climax"}
    )
    specs: list[PatternSignalInsertSpec] = []
    if int(metrics.trend_score or 50) >= 55 and bullish >= 2 and has_cluster_signals:
        specs.append(
            PatternSignalInsertSpec(
                signal_type="pattern_hierarchy_trend_continuation",
                confidence=0.78,
                market_regime=metrics.market_regime,
            )
        )
    if int(metrics.trend_score or 50) <= 45 and bearish >= 2 and has_cluster_signals:
        specs.append(
            PatternSignalInsertSpec(
                signal_type="pattern_hierarchy_distribution",
                confidence=0.74,
                market_regime=metrics.market_regime,
            )
        )
    if (
        float(metrics.volatility or 0.0) < float(metrics.price_current or 1.0) * 0.03
        and bullish >= bearish
        and bullish >= 2
    ):
        specs.append(
            PatternSignalInsertSpec(
                signal_type="pattern_hierarchy_accumulation",
                confidence=0.70,
                market_regime=metrics.market_regime,
            )
        )
    if exhaustion >= 2:
        specs.append(
            PatternSignalInsertSpec(
                signal_type="pattern_hierarchy_trend_exhaustion",
                confidence=0.73,
                market_regime=metrics.market_regime,
            )
        )
    return tuple(specs)


def compute_pattern_market_cycle(inputs: PatternCycleEngineInput) -> PatternCycleComputation:
    cycle_phase, confidence = _detect_cycle_phase(
        trend_score=inputs.trend_score,
        regime=inputs.regime,
        volatility=inputs.volatility,
        price_current=inputs.price_current,
        pattern_density=inputs.pattern_density,
        cluster_frequency=inputs.cluster_frequency,
        sector_strength=inputs.sector_strength,
        capital_flow=inputs.capital_flow,
    )
    return PatternCycleComputation(cycle_phase=cycle_phase, confidence=confidence)


__all__ = [
    "build_pattern_cluster_specs",
    "build_pattern_hierarchy_specs",
    "compute_pattern_market_cycle",
]
