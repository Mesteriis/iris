from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from src.apps.market_data.domain import ensure_utc, utc_now
from src.apps.patterns.domain.lifecycle import resolve_lifecycle_state
from src.apps.patterns.domain.semantics import is_pattern_signal, slug_from_signal_type
from src.apps.patterns.domain.statistics import (
    STATISTICS_LOOKBACK_DAYS,
    SUPPORTED_STATISTIC_TIMEFRAMES,
    PatternOutcome,
    _rolling_window,
    calculate_temperature,
)
from src.apps.patterns.domain.success import (
    BOOST_SUCCESS_RATE,
    DEGRADE_SUCCESS_RATE,
    DISABLE_SUCCESS_RATE,
    GLOBAL_MARKET_REGIME,
    MIN_SAMPLE_FOR_DEGRADE,
    MIN_SAMPLE_FOR_DISABLE,
    publish_pattern_state_event,
)
from src.apps.patterns.models import PatternRegistry
from src.apps.signals.history_support import SIGNAL_HISTORY_LOOKBACK_DAYS
from src.apps.signals.models import SignalHistory
from src.apps.signals.services import SignalHistoryService


class PatternHistoryStatisticsMixin:
    async def _refresh_signal_history(
        self,
        *,
        lookback_days: int = SIGNAL_HISTORY_LOOKBACK_DAYS,
        coin_id: int | None = None,
        timeframe: int | None = None,
        limit_per_scope: int | None = None,
    ) -> dict[str, object]:
        return (
            await SignalHistoryService(self._uow).refresh_history(
                lookback_days=lookback_days,
                coin_id=coin_id,
                timeframe=timeframe,
                limit_per_scope=limit_per_scope,
            )
        ).to_summary()

    async def _refresh_pattern_statistics(self, *, emit_events: bool = True) -> dict[str, object]:
        from src.apps.patterns.domain.registry import PATTERN_CATALOG

        await self._ensure_catalog_metadata()
        cutoff = utc_now() - timedelta(days=STATISTICS_LOOKBACK_DAYS)
        history_rows = (
            (
                await self.session.execute(
                    select(SignalHistory)
                    .where(
                        SignalHistory.candle_timestamp >= cutoff,
                        SignalHistory.signal_type.like("pattern_%"),
                        SignalHistory.result_return.is_not(None),
                        SignalHistory.result_drawdown.is_not(None),
                    )
                    .order_by(SignalHistory.timeframe.asc(), SignalHistory.candle_timestamp.asc())
                )
            )
            .scalars()
            .all()
        )

        outcomes_by_pattern: dict[tuple[str, int, str], list[PatternOutcome]] = defaultdict(list)
        for row in history_rows:
            if not is_pattern_signal(str(row.signal_type)):
                continue
            slug = slug_from_signal_type(str(row.signal_type))
            if slug is None:
                continue
            terminal_return = (
                float(row.profit_after_72h)
                if row.profit_after_72h is not None
                else float(row.profit_after_24h)
                if row.profit_after_24h is not None
                else float(row.result_return)
                if row.result_return is not None
                else None
            )
            drawdown = (
                float(row.maximum_drawdown)
                if row.maximum_drawdown is not None
                else float(row.result_drawdown)
                if row.result_drawdown is not None
                else None
            )
            if terminal_return is None or drawdown is None:
                continue
            market_regime = GLOBAL_MARKET_REGIME if not row.market_regime else str(row.market_regime)
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
                    last_evaluated_at = max(
                        (item.evaluated_at for item in outcomes if item.evaluated_at is not None),
                        default=None,
                    )
                    temperature = calculate_temperature(
                        success_rate=success_rate,
                        sample_size=sample_size,
                        days_since_sample=age_days,
                    )
                    enabled = not (sample_size >= MIN_SAMPLE_FOR_DISABLE and success_rate < DISABLE_SUCCESS_RATE)
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
            temps = [float(row["temperature"]) for row in entry_rows]
            aggregate_sample_size = sum(int(row["sample_size"]) for row in entry_rows)
            aggregate_success_rate = (
                sum(float(row["success_rate"]) * int(row["sample_size"]) for row in entry_rows) / aggregate_sample_size
                if aggregate_sample_size
                else 0.0
            )
            aggregate_temp = sum(temps) / len(temps) if temps else 0.0
            representative_timeframe = (
                int(max(entry_rows, key=lambda row: int(row["sample_size"]))["timeframe"]) if entry_rows else 15
            )
            registry_row = await self.session.get(PatternRegistry, entry.slug)
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
                }
            )

        await self._upsert_pattern_statistics(rows=rows)
        for update in lifecycle_updates:
            registry_row = await self.session.get(PatternRegistry, str(update["slug"]))
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
        await self._uow.flush()
        return {
            "status": "ok",
            "patterns": len(rows),
            "updated_registry": len(lifecycle_updates),
            "rolling_window": 200,
        }


__all__ = ["PatternHistoryStatisticsMixin"]
