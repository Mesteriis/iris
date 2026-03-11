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
from app.models.signal_history import SignalHistory
from app.patterns.lifecycle import resolve_lifecycle_state
from app.patterns.registry import PATTERN_CATALOG, sync_pattern_metadata
from app.patterns.semantics import is_pattern_signal, slug_from_signal_type
from app.patterns.success import (
    BOOST_SUCCESS_RATE,
    DEGRADE_SUCCESS_RATE,
    DISABLE_SUCCESS_RATE,
    GLOBAL_MARKET_REGIME,
    MIN_SAMPLE_FOR_DEGRADE,
    MIN_SAMPLE_FOR_DISABLE,
    PATTERN_SUCCESS_ROLLING_WINDOW,
    normalize_market_regime,
    publish_pattern_state_event,
)
from app.services.market_data import ensure_utc, utc_now

STATISTICS_LOOKBACK_DAYS = 365
SUPPORTED_STATISTIC_TIMEFRAMES = (15, 60, 240, 1440)


@dataclass(slots=True)
class PatternOutcome:
    pattern_slug: str
    timeframe: int
    market_regime: str
    terminal_return: float
    drawdown: float
    success: bool
    age_days: int
    evaluated_at: object | None


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


def _history_rows(db: Session) -> list[SignalHistory]:
    cutoff = utc_now() - timedelta(days=STATISTICS_LOOKBACK_DAYS)
    return db.scalars(
        select(SignalHistory)
        .where(
            SignalHistory.candle_timestamp >= cutoff,
            SignalHistory.signal_type.like("pattern_%"),
            SignalHistory.result_return.is_not(None),
            SignalHistory.result_drawdown.is_not(None),
        )
        .order_by(SignalHistory.timeframe.asc(), SignalHistory.candle_timestamp.asc())
    ).all()


def _select_return(row: SignalHistory) -> float | None:
    if row.profit_after_72h is not None:
        return float(row.profit_after_72h)
    if row.profit_after_24h is not None:
        return float(row.profit_after_24h)
    if row.result_return is not None:
        return float(row.result_return)
    return None


def _select_drawdown(row: SignalHistory) -> float | None:
    if row.maximum_drawdown is not None:
        return float(row.maximum_drawdown)
    if row.result_drawdown is not None:
        return float(row.result_drawdown)
    return None


def _rolling_window(
    outcomes_by_scope: dict[tuple[str, int, str], list[PatternOutcome]],
) -> dict[tuple[str, int, str], list[PatternOutcome]]:
    limited: dict[tuple[str, int, str], list[PatternOutcome]] = {}
    for scope, outcomes in outcomes_by_scope.items():
        ordered = sorted(outcomes, key=lambda item: item.evaluated_at or utc_now())
        limited[scope] = ordered[-PATTERN_SUCCESS_ROLLING_WINDOW:]
    return limited


def refresh_pattern_statistics(db: Session, *, emit_events: bool = True) -> dict[str, object]:
    sync_pattern_metadata(db)
    outcomes_by_pattern: dict[tuple[str, int, str], list[PatternOutcome]] = defaultdict(list)
    for row in _history_rows(db):
        if not is_pattern_signal(str(row.signal_type)):
            continue
        slug = slug_from_signal_type(str(row.signal_type))
        if slug is None:
            continue
        terminal_return = _select_return(row)
        drawdown = _select_drawdown(row)
        if terminal_return is None or drawdown is None:
            continue
        market_regime = normalize_market_regime(row.market_regime)
        outcome = PatternOutcome(
            pattern_slug=slug,
            timeframe=int(row.timeframe),
            market_regime=market_regime,
            terminal_return=terminal_return,
            drawdown=drawdown,
            success=terminal_return > 0,
            age_days=max((utc_now() - ensure_utc(row.candle_timestamp)).days, 0),
            evaluated_at=row.evaluated_at,
        )
        outcomes_by_pattern[(outcome.pattern_slug, outcome.timeframe, market_regime)].append(outcome)
        outcomes_by_pattern[(outcome.pattern_slug, outcome.timeframe, GLOBAL_MARKET_REGIME)].append(outcome)

    outcomes_by_pattern = _rolling_window(outcomes_by_pattern)

    rows: list[dict[str, object]] = []
    lifecycle_updates: list[dict[str, object]] = []
    for entry in PATTERN_CATALOG:
        entry_rows: list[dict[str, object]] = []
        for timeframe in SUPPORTED_STATISTIC_TIMEFRAMES:
            scoped_regimes = {GLOBAL_MARKET_REGIME}
            scoped_regimes.update(
                regime
                for pattern_slug, scoped_timeframe, regime in outcomes_by_pattern
                if pattern_slug == entry.slug and scoped_timeframe == timeframe and regime != GLOBAL_MARKET_REGIME
            )
            for market_regime in sorted(scoped_regimes):
                outcomes = outcomes_by_pattern.get((entry.slug, timeframe, market_regime), [])
                sample_size = len(outcomes)
                successful_signals = sum(1 for item in outcomes if item.success)
                success_rate = successful_signals / sample_size if sample_size else 0.0
                avg_return = sum(item.terminal_return for item in outcomes) / sample_size if sample_size else 0.0
                avg_drawdown = sum(item.drawdown for item in outcomes) / sample_size if sample_size else 0.0
                age_days = min((item.age_days for item in outcomes), default=STATISTICS_LOOKBACK_DAYS)
                last_evaluated_at = max((item.evaluated_at for item in outcomes if item.evaluated_at is not None), default=None)
                temperature = calculate_temperature(
                    success_rate=success_rate,
                    sample_size=sample_size,
                    days_since_sample=age_days,
                )
                enabled = not (
                    sample_size >= MIN_SAMPLE_FOR_DISABLE and success_rate < DISABLE_SUCCESS_RATE
                )
                entry_row = {
                    "pattern_slug": entry.slug,
                    "timeframe": timeframe,
                    "market_regime": market_regime,
                    "sample_size": sample_size,
                    "total_signals": sample_size,
                    "successful_signals": successful_signals,
                    "success_rate": success_rate,
                    "avg_return": avg_return,
                    "avg_drawdown": avg_drawdown,
                    "temperature": temperature,
                    "enabled": enabled,
                    "last_evaluated_at": last_evaluated_at,
                    "updated_at": utc_now(),
                }
                rows.append(entry_row)
                if market_regime == GLOBAL_MARKET_REGIME:
                    entry_rows.append(entry_row)
        temps = [row["temperature"] for row in entry_rows]
        aggregate_sample_size = sum(int(row["sample_size"]) for row in entry_rows)
        aggregate_success_rate = (
            sum(float(row["success_rate"]) * int(row["sample_size"]) for row in entry_rows) / aggregate_sample_size
            if aggregate_sample_size
            else 0.0
        )
        aggregate_temp = sum(float(value) for value in temps) / len(temps) if temps else 0.0
        representative_timeframe = (
            int(max(entry_rows, key=lambda row: int(row["sample_size"]))["timeframe"])
            if entry_rows
            else 15
        )
        registry_row = db.get(PatternRegistry, entry.slug)
        registry_enabled = bool(registry_row.enabled) if registry_row is not None else True
        next_state = resolve_lifecycle_state(aggregate_temp, registry_enabled)
        if aggregate_sample_size >= MIN_SAMPLE_FOR_DISABLE and aggregate_success_rate < DISABLE_SUCCESS_RATE:
            next_state = resolve_lifecycle_state(-1.0, registry_enabled)
        lifecycle_updates.append(
            {
                "slug": entry.slug,
                "timeframe": representative_timeframe,
                "lifecycle_state": next_state.value,
                "success_rate": aggregate_success_rate,
                "sample_size": aggregate_sample_size,
                "temperature": aggregate_temp,
                "enabled": registry_enabled and next_state.value != "DISABLED",
            }
        )

    if rows:
        stmt = insert(PatternStatistic).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["pattern_slug", "timeframe", "market_regime"],
            set_={
                "sample_size": stmt.excluded.sample_size,
                "total_signals": stmt.excluded.total_signals,
                "successful_signals": stmt.excluded.successful_signals,
                "success_rate": stmt.excluded.success_rate,
                "avg_return": stmt.excluded.avg_return,
                "avg_drawdown": stmt.excluded.avg_drawdown,
                "temperature": stmt.excluded.temperature,
                "enabled": stmt.excluded.enabled,
                "last_evaluated_at": stmt.excluded.last_evaluated_at,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        db.execute(stmt)

    for update in lifecycle_updates:
        registry_row = db.get(PatternRegistry, update["slug"])
        if registry_row is None:
            continue
        previous_state = str(registry_row.lifecycle_state)
        registry_row.lifecycle_state = str(update["lifecycle_state"])
        if not emit_events:
            continue
        if previous_state != registry_row.lifecycle_state:
            became_enabled = previous_state == "DISABLED" and registry_row.lifecycle_state != "DISABLED"
            became_disabled = previous_state != "DISABLED" and registry_row.lifecycle_state == "DISABLED"
            if became_enabled:
                publish_pattern_state_event(
                    "pattern_enabled",
                    pattern_slug=registry_row.slug,
                    timeframe=int(update["timeframe"]),
                    success_rate=float(update["success_rate"]),
                    total_signals=int(update["sample_size"]),
                    timestamp=utc_now(),
                )
            elif became_disabled:
                publish_pattern_state_event(
                    "pattern_disabled",
                    pattern_slug=registry_row.slug,
                    timeframe=int(update["timeframe"]),
                    success_rate=float(update["success_rate"]),
                    total_signals=int(update["sample_size"]),
                    timestamp=utc_now(),
                )
        if int(update["sample_size"]) >= MIN_SAMPLE_FOR_DEGRADE:
            if float(update["success_rate"]) > BOOST_SUCCESS_RATE:
                publish_pattern_state_event(
                    "pattern_boosted",
                    pattern_slug=registry_row.slug,
                    timeframe=int(update["timeframe"]),
                    success_rate=float(update["success_rate"]),
                    total_signals=int(update["sample_size"]),
                    timestamp=utc_now(),
                )
            elif float(update["success_rate"]) < DEGRADE_SUCCESS_RATE:
                publish_pattern_state_event(
                    "pattern_degraded",
                    pattern_slug=registry_row.slug,
                    timeframe=int(update["timeframe"]),
                    success_rate=float(update["success_rate"]),
                    total_signals=int(update["sample_size"]),
                    timestamp=utc_now(),
                )
    db.commit()
    return {
        "status": "ok",
        "patterns": len(rows),
        "updated_registry": len(lifecycle_updates),
        "rolling_window": PATTERN_SUCCESS_ROLLING_WINDOW,
    }
