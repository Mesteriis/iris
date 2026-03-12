from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from math import floor, sqrt

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from src.apps.market_data.models import Coin
from src.apps.cross_market.models import SectorMetric
from src.apps.signals.models import Signal
from src.apps.signals.models import Strategy
from src.apps.signals.models import StrategyPerformance
from src.apps.signals.models import StrategyRule
from src.apps.patterns.domain.cycle import _detect_cycle_phase
from src.apps.patterns.domain.regime import detect_market_regime
from src.apps.patterns.domain.semantics import pattern_bias, slug_from_signal_type
from src.apps.patterns.domain.utils import current_indicator_map
from src.apps.market_data.repos import CandlePoint, fetch_candle_points_between, timeframe_delta
from src.apps.market_data.domain import ensure_utc, utc_now

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


def _candle_index_map(candles: list[CandlePoint]) -> dict[object, int]:
    return {ensure_utc(candle.timestamp): index for index, candle in enumerate(candles)}


def _signal_groups(db: Session) -> dict[tuple[int, int], dict[object, list[Signal]]]:
    cutoff = utc_now() - timedelta(days=STRATEGY_LOOKBACK_DAYS)
    rows = db.scalars(
        select(Signal)
        .where(
            Signal.candle_timestamp >= cutoff,
            Signal.signal_type.like("pattern_%"),
        )
        .order_by(Signal.coin_id.asc(), Signal.timeframe.asc(), Signal.candle_timestamp.asc(), Signal.created_at.asc())
    ).all()
    grouped: dict[tuple[int, int], dict[object, list[Signal]]] = defaultdict(lambda: defaultdict(list))
    for signal in rows:
        grouped[(signal.coin_id, signal.timeframe)][ensure_utc(signal.candle_timestamp)].append(signal)
    return grouped


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
        if signal.signal_type.startswith("pattern_")
        and "cluster_" not in signal.signal_type
        and "hierarchy_" not in signal.signal_type
    )
    cluster_frequency = sum(1 for signal in signals if "pattern_cluster_" in signal.signal_type)
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
        slug = slug_from_signal_type(signal.signal_type)
        if slug is None:
            continue
        weight = max(float(signal.priority_score or signal.confidence), 0.01)
        signed_weight += weight * pattern_bias(slug, fallback_price_delta=signal.confidence - 0.5)
        total_weight += weight
    if total_weight <= 0:
        return 1
    ratio = signed_weight / total_weight
    return 1 if ratio >= 0 else -1


def _signal_outcome(
    *,
    signals: list[Signal],
    candles: list[CandlePoint],
    index_map: dict[object, int],
    timeframe: int,
    candle_timestamp: object,
) -> tuple[float, float, bool] | None:
    open_timestamp = ensure_utc(candle_timestamp) - timeframe_delta(timeframe)
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
        slug = slug_from_signal_type(signal.signal_type)
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


def _upsert_strategy(
    db: Session,
    *,
    candidate: StrategyCandidate,
    sample_size: int,
    win_rate: float,
    avg_return: float,
    sharpe_ratio: float,
    max_drawdown: float,
    enabled: bool,
) -> int:
    name = _strategy_name(candidate)
    row = db.scalar(select(Strategy).where(Strategy.name == name))
    if row is None:
        row = Strategy(
            name=name,
            description=_strategy_description(candidate),
            enabled=enabled,
        )
        db.add(row)
        db.flush()
    else:
        row.description = _strategy_description(candidate)
        row.enabled = enabled

    db.execute(delete(StrategyRule).where(StrategyRule.strategy_id == row.id))
    db.add_all(
        [
            StrategyRule(
                strategy_id=row.id,
                pattern_slug=token,
                regime=candidate.regime,
                sector=candidate.sector,
                cycle=candidate.cycle,
                min_confidence=candidate.min_confidence,
            )
            for token in candidate.tokens
        ]
    )

    performance = db.get(StrategyPerformance, row.id)
    if performance is None:
        performance = StrategyPerformance(strategy_id=row.id)
        db.add(performance)
    performance.sample_size = sample_size
    performance.win_rate = win_rate
    performance.avg_return = avg_return
    performance.sharpe_ratio = sharpe_ratio
    performance.max_drawdown = max_drawdown
    performance.updated_at = utc_now()
    db.flush()
    return row.id


def refresh_strategies(db: Session) -> dict[str, object]:
    grouped = _signal_groups(db)
    coin_map = {coin.id: coin for coin in db.scalars(select(Coin).where(Coin.deleted_at.is_(None))).all()}
    observations_by_candidate: dict[StrategyCandidate, list[StrategyObservation]] = defaultdict(list)

    for (coin_id, timeframe), groups in grouped.items():
        if not groups:
            continue
        ordered_timestamps = sorted(groups)
        start = ordered_timestamps[0] - timeframe_delta(timeframe) * 220
        end = ordered_timestamps[-1] + timeframe_delta(timeframe) * (HORIZON_BARS_BY_TIMEFRAME.get(timeframe, 8) + 1)
        candles = fetch_candle_points_between(db, coin_id, timeframe, start, end)
        if len(candles) < 30:
            continue
        index_map = _candle_index_map(candles)
        coin = coin_map.get(coin_id)
        sector = coin.sector.name if coin is not None and coin.sector is not None else "*"
        sector_metric = db.get(SectorMetric, (coin.sector_id, timeframe)) if coin is not None and coin.sector_id is not None else None

        for candle_timestamp in ordered_timestamps:
            signals = groups[candle_timestamp]
            outcome = _signal_outcome(
                signals=signals,
                candles=candles,
                index_map=index_map,
                timeframe=timeframe,
                candle_timestamp=candle_timestamp,
            )
            if outcome is None:
                continue
            open_timestamp = candle_timestamp - timeframe_delta(timeframe)
            candle_index = index_map.get(open_timestamp)
            if candle_index is None:
                continue
            window = candles[max(0, candle_index - 199) : candle_index + 1]
            if len(window) < 20:
                continue
            regime, cycle = _context_from_window(window=window, signals=signals, sector_metric=sector_metric)
            for candidate in _candidate_definitions(
                timeframe=timeframe,
                signals=signals,
                regime=regime,
                sector=sector,
                cycle=cycle,
            ):
                observations_by_candidate[candidate].append(
                    StrategyObservation(
                        candidate=candidate,
                        terminal_return=outcome[0],
                        drawdown=outcome[1],
                        success=outcome[2],
                    )
                )

    ranked_candidates: list[tuple[StrategyCandidate, int, float, float, float, float, bool]] = []
    for candidate, observations in observations_by_candidate.items():
        sample_size = len(observations)
        if sample_size < MIN_DISCOVERY_SAMPLE:
            continue
        returns = [item.terminal_return for item in observations]
        win_rate = sum(1 for item in observations if item.success) / sample_size
        avg_return = sum(returns) / sample_size
        sharpe_ratio = _sharpe_ratio(returns)
        max_drawdown = min(item.drawdown for item in observations)
        enabled = _strategy_enabled(sample_size, win_rate, avg_return, sharpe_ratio, max_drawdown)
        ranked_candidates.append(
            (candidate, sample_size, win_rate, avg_return, sharpe_ratio, max_drawdown, enabled)
        )

    ranked_candidates.sort(
        key=lambda item: (
            item[6],
            item[4],
            item[2],
            item[3],
            item[1],
            -item[5],
        ),
        reverse=True,
    )
    ranked_candidates = ranked_candidates[:MAX_DISCOVERED_STRATEGIES]

    seen_ids: set[int] = set()
    for candidate, sample_size, win_rate, avg_return, sharpe_ratio, max_drawdown, enabled in ranked_candidates:
        seen_ids.add(
            _upsert_strategy(
                db,
                candidate=candidate,
                sample_size=sample_size,
                win_rate=win_rate,
                avg_return=avg_return,
                sharpe_ratio=sharpe_ratio,
                max_drawdown=max_drawdown,
                enabled=enabled,
            )
        )

    for row in db.scalars(select(Strategy)).all():
        if row.id not in seen_ids:
            row.enabled = False

    db.commit()
    return {
        "status": "ok",
        "strategies": len(ranked_candidates),
        "enabled": sum(1 for item in ranked_candidates if item[6]),
    }


def strategy_alignment(
    db: Session,
    *,
    tokens: set[str],
    token_confidence: dict[str, float],
    regime: str | None,
    sector: str | None,
    cycle: str | None,
) -> tuple[float, list[str]]:
    rows = db.scalars(
        select(Strategy)
        .options(selectinload(Strategy.rules), selectinload(Strategy.performance))
        .where(Strategy.enabled.is_(True))
        .order_by(Strategy.id.asc())
    ).all()
    matched_names: list[str] = []
    best_alignment = 1.0
    for row in rows:
        performance = row.performance
        if performance is None or performance.sample_size < MIN_DISCOVERY_SAMPLE:
            continue
        matched = True
        for rule in row.rules:
            if rule.pattern_slug not in tokens:
                matched = False
                break
            if rule.regime != "*" and regime != rule.regime:
                matched = False
                break
            if rule.sector != "*" and sector != rule.sector:
                matched = False
                break
            if rule.cycle != "*" and cycle != rule.cycle:
                matched = False
                break
            if token_confidence.get(rule.pattern_slug, 0.0) < float(rule.min_confidence or 0.0):
                matched = False
                break
        if not matched:
            continue
        matched_names.append(row.name)
        alignment = 1.0
        alignment += _clamp((float(performance.win_rate) - 0.5) * 0.6, 0.0, 0.18)
        alignment += _clamp(float(performance.sharpe_ratio) * 0.05, 0.0, 0.12)
        alignment += _clamp(float(performance.avg_return) * 4.0, 0.0, 0.08)
        alignment -= _clamp(abs(min(float(performance.max_drawdown), 0.0)) * 0.15, 0.0, 0.05)
        best_alignment = max(best_alignment, _clamp(alignment, 1.0, 1.3))
    return best_alignment, matched_names[:3]
