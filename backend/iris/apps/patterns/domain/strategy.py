from dataclasses import dataclass
from datetime import datetime
from math import floor, sqrt

from iris.apps.cross_market.models import SectorMetric
from iris.apps.market_data.candles import CandlePoint, timeframe_delta
from iris.apps.patterns.domain.cycle import _detect_cycle_phase
from iris.apps.patterns.domain.regime import detect_market_regime
from iris.apps.patterns.domain.semantics import pattern_bias, slug_from_signal_type
from iris.apps.patterns.domain.utils import current_indicator_map
from iris.apps.signals.models import Signal

STRATEGY_LOOKBACK_DAYS = 365
MAX_DISCOVERED_STRATEGIES = 200
MIN_DISCOVERY_SAMPLE = 8
MIN_WIN_RATE = 0.45
MIN_AVG_RETURN = 0.0
MIN_SHARPE_RATIO = 0.4
MIN_MAX_DRAWDOWN = -0.18
HORIZON_BARS_BY_TIMEFRAME = {
    15: 16,
    60: 12,
    240: 8,
    1440: 5,
}


@dataclass(slots=True, frozen=True)
class StrategyCandidate:
    timeframe: int
    tokens: tuple[str, ...]
    regime: str
    sector: str
    cycle: str
    min_confidence: float


@dataclass(slots=True)
class StrategyObservation:
    candidate: StrategyCandidate
    terminal_return: float
    drawdown: float
    success: bool


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _round_confidence(value: float) -> float:
    return _clamp(floor(max(value, 0.0) * 20.0) / 20.0, 0.0, 0.99)


def _candle_index_map(candles: list[CandlePoint]) -> dict[datetime, int]:
    return {candle.timestamp: index for index, candle in enumerate(candles)}


def _trend_score_from_indicators(indicators: dict[str, float | None]) -> int:
    score = 50
    price = float(indicators.get("price_current") or 0.0)
    sma_200 = float(indicators.get("sma_200") or 0.0)
    ema_20 = float(indicators.get("ema_20") or 0.0)
    ema_50 = float(indicators.get("ema_50") or 0.0)
    macd_histogram = float(indicators.get("macd_histogram") or 0.0)
    adx = float(indicators.get("adx_14") or 0.0)
    score += 15 if price > sma_200 else -15
    score += 10 if ema_20 > ema_50 else -10
    score += 10 if macd_histogram > 0 else -10
    if adx >= 20:
        score += 10 if price >= ema_20 else -10
    return int(_clamp(score, 0, 100))


def _context_from_window(
    *,
    window: list[CandlePoint],
    signals: list[Signal],
    sector_metric: SectorMetric | None,
) -> tuple[str, str]:
    indicators = current_indicator_map(window)
    regime, _ = detect_market_regime(indicators)
    pattern_density = sum(
        1
        for signal in signals
        if str(signal.signal_type).startswith("pattern_")
        and "cluster_" not in str(signal.signal_type)
        and "hierarchy_" not in str(signal.signal_type)
    )
    cluster_frequency = sum(1 for signal in signals if "pattern_cluster_" in str(signal.signal_type))
    cycle, _ = _detect_cycle_phase(
        trend_score=_trend_score_from_indicators(indicators),
        regime=regime,
        volatility=float(indicators.get("atr_14") or 0.0),
        price_current=float(indicators.get("price_current") or 0.0),
        pattern_density=pattern_density,
        cluster_frequency=cluster_frequency,
        sector_strength=sector_metric.sector_strength if sector_metric is not None else None,
        capital_flow=sector_metric.capital_flow if sector_metric is not None else None,
    )
    return regime, cycle


def _signal_stack_bias(signals: list[Signal]) -> int:
    signed_weight = 0.0
    total_weight = 0.0
    for signal in signals:
        slug = slug_from_signal_type(str(signal.signal_type))
        if slug is None:
            continue
        weight = max(float(signal.priority_score or signal.confidence), 0.01)
        signed_weight += weight * pattern_bias(slug, fallback_price_delta=float(signal.confidence) - 0.5)
        total_weight += weight
    if total_weight <= 0:
        return 1
    ratio = signed_weight / total_weight
    return 1 if ratio >= 0 else -1


def _signal_outcome(
    *,
    signals: list[Signal],
    candles: list[CandlePoint],
    index_map: dict[datetime, int],
    timeframe: int,
    candle_timestamp: datetime,
) -> tuple[float, float, bool] | None:
    open_timestamp = candle_timestamp - timeframe_delta(timeframe)
    candle_index = index_map.get(open_timestamp)
    if candle_index is None:
        return None
    horizon = HORIZON_BARS_BY_TIMEFRAME.get(timeframe, 8)
    future_window = candles[candle_index + 1 : candle_index + 1 + horizon]
    if not future_window:
        return None
    entry_close = float(candles[candle_index].close)
    last_close = float(future_window[-1].close)
    bias = _signal_stack_bias(signals)
    if bias > 0:
        terminal_return = (last_close - entry_close) / max(entry_close, 1e-9)
        drawdown = (min(float(item.low) for item in future_window) - entry_close) / max(entry_close, 1e-9)
    else:
        terminal_return = (entry_close - last_close) / max(entry_close, 1e-9)
        drawdown = (entry_close - max(float(item.high) for item in future_window)) / max(entry_close, 1e-9)
    return terminal_return, drawdown, terminal_return > 0


def _signal_tokens(signals: list[Signal]) -> tuple[list[str], dict[str, float]]:
    ranked: list[tuple[str, float, float]] = []
    best_confidence: dict[str, float] = {}
    for signal in signals:
        slug = slug_from_signal_type(str(signal.signal_type))
        if slug is None:
            continue
        score = float(signal.priority_score or signal.confidence)
        confidence = float(signal.confidence)
        ranked.append((slug, score, confidence))
        best_confidence[slug] = max(best_confidence.get(slug, 0.0), confidence)
    ranked.sort(key=lambda item: (item[1], item[2], item[0]), reverse=True)
    ordered_tokens: list[str] = []
    for slug, _, _ in ranked:
        if slug not in ordered_tokens:
            ordered_tokens.append(slug)
    return ordered_tokens, best_confidence


def _candidate_definitions(
    *,
    timeframe: int,
    signals: list[Signal],
    regime: str,
    sector: str,
    cycle: str,
) -> list[StrategyCandidate]:
    ordered_tokens, best_confidence = _signal_tokens(signals)
    if not ordered_tokens:
        return []
    candidates: list[StrategyCandidate] = []
    seen: set[tuple[tuple[str, ...], str, str, str, float]] = set()

    def add_candidate(tokens: tuple[str, ...], candidate_regime: str, candidate_sector: str, candidate_cycle: str) -> None:
        min_confidence = _round_confidence(min(best_confidence[token] for token in tokens))
        key = (tokens, candidate_regime, candidate_sector, candidate_cycle, min_confidence)
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            StrategyCandidate(
                timeframe=timeframe,
                tokens=tokens,
                regime=candidate_regime,
                sector=candidate_sector,
                cycle=candidate_cycle,
                min_confidence=min_confidence,
            )
        )

    primary = (ordered_tokens[0],)
    add_candidate(primary, "*", "*", "*")
    add_candidate(primary, regime, "*", "*")
    add_candidate(primary, regime, "*", cycle)
    add_candidate(primary, regime, sector, cycle)

    if len(ordered_tokens) >= 2:
        combo = tuple(sorted(ordered_tokens[:2]))
        add_candidate(combo, "*", "*", "*")
        add_candidate(combo, regime, "*", cycle)
        add_candidate(combo, regime, sector, cycle)

    return candidates


def _strategy_name(candidate: StrategyCandidate) -> str:
    return " | ".join(
        [
            f"SESE {candidate.timeframe}m",
            " + ".join(token.replace("_", " ") for token in candidate.tokens),
            f"regime {candidate.regime}",
            f"sector {candidate.sector}",
            f"cycle {candidate.cycle}",
        ]
    )


def _strategy_description(candidate: StrategyCandidate) -> str:
    return (
        f"Auto-discovered strategy for timeframe {candidate.timeframe}m using "
        f"{', '.join(candidate.tokens)} with regime={candidate.regime}, "
        f"sector={candidate.sector}, cycle={candidate.cycle} and "
        f"min_confidence>={candidate.min_confidence:.2f}."
    )


def _sharpe_ratio(returns: list[float]) -> float:
    if len(returns) < 2:
        return 0.0
    avg = sum(returns) / len(returns)
    variance = sum((value - avg) ** 2 for value in returns) / len(returns)
    if variance <= 0:
        return 0.0
    return avg / sqrt(variance)


def _strategy_enabled(sample_size: int, win_rate: float, avg_return: float, sharpe_ratio: float, max_drawdown: float) -> bool:
    return (
        sample_size >= MIN_DISCOVERY_SAMPLE
        and win_rate >= MIN_WIN_RATE
        and avg_return > MIN_AVG_RETURN
        and sharpe_ratio >= MIN_SHARPE_RATIO
        and max_drawdown >= MIN_MAX_DRAWDOWN
    )


__all__ = [
    "HORIZON_BARS_BY_TIMEFRAME",
    "MAX_DISCOVERED_STRATEGIES",
    "MIN_AVG_RETURN",
    "MIN_DISCOVERY_SAMPLE",
    "MIN_MAX_DRAWDOWN",
    "MIN_SHARPE_RATIO",
    "MIN_WIN_RATE",
    "STRATEGY_LOOKBACK_DAYS",
    "StrategyCandidate",
    "StrategyObservation",
    "_candidate_definitions",
    "_candle_index_map",
    "_clamp",
    "_context_from_window",
    "_round_confidence",
    "_sharpe_ratio",
    "_signal_outcome",
    "_signal_stack_bias",
    "_signal_tokens",
    "_strategy_description",
    "_strategy_enabled",
    "_strategy_name",
    "_trend_score_from_indicators",
]
