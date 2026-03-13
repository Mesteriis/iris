from __future__ import annotations

from src.apps.patterns.query_builders import signal_select


def _signal_select():
    return signal_select()


__all__ = ["_signal_select"]
