from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.apps.market_data.domain import (
    align_timestamp,
    ensure_utc,
    history_window_start,
    interval_delta,
    latest_completed_timestamp,
    normalize_interval,
)


def test_market_data_domain_normalizes_intervals_and_utc_values() -> None:
    naive = datetime(2026, 3, 12, 9, 7)
    aware = datetime(2026, 3, 12, 9, 7, tzinfo=timezone(timedelta(hours=2)))

    assert ensure_utc(naive) == datetime(2026, 3, 12, 9, 7, tzinfo=timezone.utc)
    assert ensure_utc(aware) == datetime(2026, 3, 12, 7, 7, tzinfo=timezone.utc)
    assert normalize_interval(" 1H ") == "1h"
    assert interval_delta("4h") == timedelta(hours=4)

    with pytest.raises(ValueError, match="Unsupported interval '5m'"):
        normalize_interval("5m")


def test_market_data_domain_aligns_completed_windows() -> None:
    reference = datetime(2026, 3, 12, 9, 7, 31, tzinfo=timezone.utc)

    assert align_timestamp(reference, "15m") == datetime(2026, 3, 12, 9, 0, tzinfo=timezone.utc)
    assert latest_completed_timestamp("15m", reference) == datetime(2026, 3, 12, 8, 45, tzinfo=timezone.utc)
    assert history_window_start(
        datetime(2026, 3, 12, 9, 0, tzinfo=timezone.utc),
        "1h",
        5,
    ) == datetime(2026, 3, 12, 5, 0, tzinfo=timezone.utc)
    assert history_window_start(
        datetime(2026, 3, 12, 9, 0, tzinfo=timezone.utc),
        "1d",
        0,
    ) == datetime(2026, 3, 12, 9, 0, tzinfo=timezone.utc)
