from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.apps.market_data.domain import ensure_utc, utc_now
from src.apps.market_data.repos import CandlePoint, fetch_candle_points_between, timeframe_delta
from src.apps.signals.history_support import (
    SIGNAL_EVALUATION_HORIZON_BARS,
    SIGNAL_HISTORY_LOOKBACK_DAYS,
    SIGNAL_HISTORY_RECENT_LIMIT,
    SignalOutcome,
    _candle_index_map,
    _close_timestamps,
    _drawdown_for_window,
    _evaluate_signal,
    _index_at_or_after,
    _open_timestamp_from_signal,
    _return_for_index,
    _signal_direction,
)
from src.apps.signals.models import Signal, SignalHistory
from src.apps.signals.services import SignalHistoryRefreshResult
from src.core.db.persistence import PERSISTENCE_LOGGER, sanitize_log_value


def _fetch_signals(
    db: Session,
    *,
    lookback_days: int,
    coin_id: int | None = None,
    timeframe: int | None = None,
    limit_per_scope: int | None = None,
) -> list[Signal]:
    cutoff = utc_now() - timedelta(days=lookback_days)
    stmt = (
        select(Signal)
        .where(Signal.candle_timestamp >= cutoff)
        .order_by(Signal.coin_id.asc(), Signal.timeframe.asc(), Signal.candle_timestamp.asc(), Signal.created_at.asc())
    )
    if coin_id is not None:
        stmt = stmt.where(Signal.coin_id == coin_id)
    if timeframe is not None:
        stmt = stmt.where(Signal.timeframe == timeframe)
    rows = db.scalars(stmt).all()
    if limit_per_scope is None:
        return rows
    grouped: dict[tuple[int, int], list[Signal]] = defaultdict(list)
    for row in rows:
        grouped[(row.coin_id, row.timeframe)].append(row)
    limited: list[Signal] = []
    for scoped_rows in grouped.values():
        limited.extend(scoped_rows[-limit_per_scope:])
    limited.sort(key=lambda row: (row.coin_id, row.timeframe, row.candle_timestamp, row.created_at))
    return limited


class SignalHistoryCompatibilityService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _log(self, level: int, event: str, /, **fields: Any) -> None:
        PERSISTENCE_LOGGER.log(
            level,
            event,
            extra={
                "persistence": {
                    "event": event,
                    "component_type": "compatibility_service",
                    "domain": "signals",
                    "component": "SignalHistoryCompatibilityService",
                    **{key: sanitize_log_value(value) for key, value in fields.items()},
                }
            },
        )

    def refresh_signal_history(
        self,
        *,
        lookback_days: int = SIGNAL_HISTORY_LOOKBACK_DAYS,
        coin_id: int | None = None,
        timeframe: int | None = None,
        limit_per_scope: int | None = None,
        commit: bool = True,
    ) -> dict[str, object]:
        signals = _fetch_signals(
            self._db,
            lookback_days=lookback_days,
            coin_id=coin_id,
            timeframe=timeframe,
            limit_per_scope=limit_per_scope,
        )
        if not signals:
            return SignalHistoryRefreshResult(
                status="ok",
                rows=0,
                evaluated=0,
                coin_id=coin_id,
                timeframe=timeframe,
            ).to_summary()

        groups: dict[tuple[int, int], list[Signal]] = defaultdict(list)
        for signal in signals:
            groups[(signal.coin_id, signal.timeframe)].append(signal)

        rows: list[dict[str, object]] = []
        evaluated = 0
        for (group_coin_id, group_timeframe), scoped_signals in groups.items():
            if not scoped_signals:
                continue
            start = _open_timestamp_from_signal(scoped_signals[0])
            end = ensure_utc(scoped_signals[-1].candle_timestamp) + timedelta(hours=72) + timeframe_delta(group_timeframe)
            candles = fetch_candle_points_between(self._db, group_coin_id, group_timeframe, start, end)
            if not candles:
                for signal in scoped_signals:
                    rows.append(
                        {
                            "coin_id": signal.coin_id,
                            "timeframe": signal.timeframe,
                            "signal_type": signal.signal_type,
                            "confidence": float(signal.confidence),
                            "market_regime": signal.market_regime,
                            "candle_timestamp": signal.candle_timestamp,
                            "profit_after_24h": None,
                            "profit_after_72h": None,
                            "maximum_drawdown": None,
                            "result_return": None,
                            "result_drawdown": None,
                            "evaluated_at": None,
                        }
                    )
                continue

            close_timestamps = _close_timestamps(candles, group_timeframe)
            close_index_map = {timestamp: index for index, timestamp in enumerate(close_timestamps)}
            for signal in scoped_signals:
                outcome = _evaluate_signal(signal, candles, close_timestamps, close_index_map)
                if outcome.evaluated_at is not None:
                    evaluated += 1
                rows.append(
                    {
                        "coin_id": signal.coin_id,
                        "timeframe": signal.timeframe,
                        "signal_type": signal.signal_type,
                        "confidence": float(signal.confidence),
                        "market_regime": signal.market_regime,
                        "candle_timestamp": signal.candle_timestamp,
                        "profit_after_24h": outcome.profit_after_24h,
                        "profit_after_72h": outcome.profit_after_72h,
                        "maximum_drawdown": outcome.maximum_drawdown,
                        "result_return": outcome.result_return,
                        "result_drawdown": outcome.result_drawdown,
                        "evaluated_at": outcome.evaluated_at,
                    }
                )

        if rows:
            stmt = insert(SignalHistory).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["coin_id", "timeframe", "signal_type", "candle_timestamp"],
                set_={
                    "confidence": stmt.excluded.confidence,
                    "market_regime": stmt.excluded.market_regime,
                    "profit_after_24h": stmt.excluded.profit_after_24h,
                    "profit_after_72h": stmt.excluded.profit_after_72h,
                    "maximum_drawdown": stmt.excluded.maximum_drawdown,
                    "result_return": stmt.excluded.result_return,
                    "result_drawdown": stmt.excluded.result_drawdown,
                    "evaluated_at": stmt.excluded.evaluated_at,
                },
            )
            self._db.execute(stmt)
        if commit:
            self._db.commit()
        return SignalHistoryRefreshResult(
            status="ok",
            rows=len(rows),
            evaluated=evaluated,
            coin_id=coin_id,
            timeframe=timeframe,
        ).to_summary()

    def refresh_recent_signal_history(
        self,
        *,
        coin_id: int,
        timeframe: int,
        commit: bool = True,
    ) -> dict[str, object]:
        return self.refresh_signal_history(
            lookback_days=SIGNAL_HISTORY_LOOKBACK_DAYS,
            coin_id=coin_id,
            timeframe=timeframe,
            limit_per_scope=SIGNAL_HISTORY_RECENT_LIMIT,
            commit=commit,
        )


def refresh_signal_history(
    db: Session,
    *,
    lookback_days: int = SIGNAL_HISTORY_LOOKBACK_DAYS,
    coin_id: int | None = None,
    timeframe: int | None = None,
    limit_per_scope: int | None = None,
    commit: bool = True,
) -> dict[str, object]:
    service = SignalHistoryCompatibilityService(db)
    service._log(
        logging.WARNING,
        "compat.refresh_signal_history.deprecated",
        mode="write",
        lookback_days=lookback_days,
        coin_id=coin_id,
        timeframe=timeframe,
        limit_per_scope=limit_per_scope,
        commit=commit,
    )
    return service.refresh_signal_history(
        lookback_days=lookback_days,
        coin_id=coin_id,
        timeframe=timeframe,
        limit_per_scope=limit_per_scope,
        commit=commit,
    )


def refresh_recent_signal_history(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    commit: bool = True,
) -> dict[str, object]:
    service = SignalHistoryCompatibilityService(db)
    service._log(
        logging.WARNING,
        "compat.refresh_recent_signal_history.deprecated",
        mode="write",
        coin_id=coin_id,
        timeframe=timeframe,
        commit=commit,
    )
    return service.refresh_recent_signal_history(
        coin_id=coin_id,
        timeframe=timeframe,
        commit=commit,
    )


__all__ = [
    "SignalHistoryCompatibilityService",
    "_candle_index_map",
    "_close_timestamps",
    "_drawdown_for_window",
    "_evaluate_signal",
    "_fetch_signals",
    "_index_at_or_after",
    "_open_timestamp_from_signal",
    "_return_for_index",
    "_signal_direction",
    "refresh_recent_signal_history",
    "refresh_signal_history",
]
