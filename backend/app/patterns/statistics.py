from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from math import exp, log

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.pattern_registry import PatternRegistry
from app.models.pattern_statistic import PatternStatistic
from app.models.signal import Signal
from app.patterns.lifecycle import PatternLifecycleState, resolve_lifecycle_state
from app.patterns.registry import PATTERN_CATALOG, sync_pattern_metadata
from app.patterns.semantics import is_pattern_signal, pattern_bias, slug_from_signal_type
from app.services.candles_service import CandlePoint, fetch_candle_points_between, timeframe_delta
from app.services.market_data import ensure_utc, utc_now

STATISTICS_LOOKBACK_DAYS = 365
HORIZON_BARS_BY_TIMEFRAME = {
    15: 16,
    60: 12,
    240: 8,
    1440: 5,
}


@dataclass(slots=True)
class PatternOutcome:
    pattern_slug: str
    timeframe: int
    terminal_return: float
    drawdown: float
    success: bool
    age_days: int


def calculate_temperature(
    *,
    success_rate: float,
    sample_size: int,
    days_since_sample: int,
) -> float:
    if sample_size <= 0:
        return 0.0
    base = (success_rate - 0.5) * log(max(sample_size, 1))
    return base * exp(-(max(days_since_sample, 0) / 90))


def _signal_groups(db: Session) -> dict[tuple[int, int], list[Signal]]:
    cutoff = utc_now() - timedelta(days=STATISTICS_LOOKBACK_DAYS)
    rows = db.scalars(
        select(Signal)
        .where(
            Signal.candle_timestamp >= cutoff,
            Signal.signal_type.like("pattern_%"),
        )
        .order_by(Signal.coin_id.asc(), Signal.timeframe.asc(), Signal.candle_timestamp.asc())
    ).all()
    grouped: dict[tuple[int, int], list[Signal]] = defaultdict(list)
    for signal in rows:
        if is_pattern_signal(signal.signal_type):
            grouped[(signal.coin_id, signal.timeframe)].append(signal)
    return grouped


def _open_timestamp_from_signal(signal: Signal) -> object:
    return ensure_utc(signal.candle_timestamp) - timeframe_delta(signal.timeframe)


def _candle_index_map(candles: list[CandlePoint]) -> dict[object, int]:
    return {ensure_utc(candle.timestamp): index for index, candle in enumerate(candles)}


def _signal_outcome(signal: Signal, candles: list[CandlePoint], index_map: dict[object, int]) -> PatternOutcome | None:
    slug = slug_from_signal_type(signal.signal_type)
    if slug is None:
        return None
    open_timestamp = _open_timestamp_from_signal(signal)
    candle_index = index_map.get(open_timestamp)
    if candle_index is None:
        return None
    horizon = HORIZON_BARS_BY_TIMEFRAME.get(signal.timeframe, 8)
    if candle_index + 1 >= len(candles):
        return None
    future_window = candles[candle_index + 1 : candle_index + 1 + horizon]
    if not future_window:
        return None
    entry_close = float(candles[candle_index].close)
    last_close = float(future_window[-1].close)
    fallback_delta = float(candles[candle_index].close) - float(candles[max(candle_index - 1, 0)].close)
    bias = pattern_bias(slug, fallback_price_delta=fallback_delta)
    if bias > 0:
        terminal_return = (last_close - entry_close) / max(entry_close, 1e-9)
        drawdown = (min(float(item.low) for item in future_window) - entry_close) / max(entry_close, 1e-9)
    else:
        terminal_return = (entry_close - last_close) / max(entry_close, 1e-9)
        drawdown = (entry_close - max(float(item.high) for item in future_window)) / max(entry_close, 1e-9)
    return PatternOutcome(
        pattern_slug=slug,
        timeframe=signal.timeframe,
        terminal_return=terminal_return,
        drawdown=drawdown,
        success=terminal_return > 0,
        age_days=max((utc_now() - ensure_utc(signal.candle_timestamp)).days, 0),
    )


def refresh_pattern_statistics(db: Session) -> dict[str, object]:
    sync_pattern_metadata(db)
    outcomes_by_pattern: dict[tuple[str, int], list[PatternOutcome]] = defaultdict(list)
    grouped_signals = _signal_groups(db)
    for (coin_id, timeframe), signals in grouped_signals.items():
        if not signals:
            continue
        start = _open_timestamp_from_signal(signals[0])
        end = ensure_utc(signals[-1].candle_timestamp) + timeframe_delta(timeframe) * (HORIZON_BARS_BY_TIMEFRAME.get(timeframe, 8) + 1)
        candles = fetch_candle_points_between(db, coin_id, timeframe, start, end)
        if not candles:
            continue
        index_map = _candle_index_map(candles)
        for signal in signals:
            outcome = _signal_outcome(signal, candles, index_map)
            if outcome is not None:
                outcomes_by_pattern[(outcome.pattern_slug, outcome.timeframe)].append(outcome)

    rows: list[dict[str, object]] = []
    lifecycle_updates: list[dict[str, object]] = []
    for entry in PATTERN_CATALOG:
        entry_rows: list[dict[str, object]] = []
        for timeframe in HORIZON_BARS_BY_TIMEFRAME:
            outcomes = outcomes_by_pattern.get((entry.slug, timeframe), [])
            sample_size = len(outcomes)
            success_rate = sum(1 for item in outcomes if item.success) / sample_size if sample_size else 0.0
            avg_return = sum(item.terminal_return for item in outcomes) / sample_size if sample_size else 0.0
            avg_drawdown = sum(item.drawdown for item in outcomes) / sample_size if sample_size else 0.0
            age_days = min((item.age_days for item in outcomes), default=STATISTICS_LOOKBACK_DAYS)
            temperature = calculate_temperature(
                success_rate=success_rate,
                sample_size=sample_size,
                days_since_sample=age_days,
            )
            entry_row = {
                "pattern_slug": entry.slug,
                "timeframe": timeframe,
                "sample_size": sample_size,
                "success_rate": success_rate,
                "avg_return": avg_return,
                "avg_drawdown": avg_drawdown,
                "temperature": temperature,
                "updated_at": utc_now(),
            }
            rows.append(entry_row)
            entry_rows.append(entry_row)
        temps = [row["temperature"] for row in entry_rows]
        aggregate_temp = sum(float(value) for value in temps) / len(temps) if temps else 0.0
        next_state = resolve_lifecycle_state(aggregate_temp, True)
        lifecycle_updates.append(
            {
                "slug": entry.slug,
                "lifecycle_state": next_state.value,
            }
        )

    if rows:
        stmt = insert(PatternStatistic).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["pattern_slug", "timeframe"],
            set_={
                "sample_size": stmt.excluded.sample_size,
                "success_rate": stmt.excluded.success_rate,
                "avg_return": stmt.excluded.avg_return,
                "avg_drawdown": stmt.excluded.avg_drawdown,
                "temperature": stmt.excluded.temperature,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        db.execute(stmt)

    for update in lifecycle_updates:
        registry_row = db.get(PatternRegistry, update["slug"])
        if registry_row is None:
            continue
        registry_row.lifecycle_state = str(update["lifecycle_state"])
    db.commit()
    return {
        "status": "ok",
        "patterns": len(rows),
        "updated_registry": len(lifecycle_updates),
    }
