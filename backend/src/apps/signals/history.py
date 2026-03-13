from __future__ import annotations

"""Pure signal-history helpers kept for deterministic unit coverage only.

Active signal-history persistence lives in ``services.py`` and ``repositories.py``
under the shared async unit of work. This module intentionally contains no
direct session queries or transaction ownership.
"""

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

__all__ = [
    "SIGNAL_EVALUATION_HORIZON_BARS",
    "SIGNAL_HISTORY_LOOKBACK_DAYS",
    "SIGNAL_HISTORY_RECENT_LIMIT",
    "SignalOutcome",
    "_candle_index_map",
    "_close_timestamps",
    "_drawdown_for_window",
    "_evaluate_signal",
    "_index_at_or_after",
    "_open_timestamp_from_signal",
    "_return_for_index",
    "_signal_direction",
]
