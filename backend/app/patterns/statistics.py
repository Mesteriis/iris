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


def refresh_pattern_statistics(db: Session) -> dict[str, object]:
    sync_pattern_metadata(db)
    outcomes_by_pattern: dict[tuple[str, int], list[PatternOutcome]] = defaultdict(list)
    for row in _history_rows(db):
        if not is_pattern_signal(str(row.signal_type)):
            continue
        slug = slug_from_signal_type(str(row.signal_type))
        if slug is None:
            continue
        outcome = PatternOutcome(
            pattern_slug=slug,
            timeframe=int(row.timeframe),
            terminal_return=float(row.result_return),
            drawdown=float(row.result_drawdown),
            success=float(row.result_return) > 0,
            age_days=max((utc_now() - ensure_utc(row.candle_timestamp)).days, 0),
        )
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
