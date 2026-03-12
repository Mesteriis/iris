from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import delete

from src.apps.patterns.domain.statistics import (
    _select_drawdown,
    _select_return,
    calculate_temperature,
    refresh_pattern_statistics,
)
from src.apps.patterns.models import PatternRegistry, PatternStatistic
from src.apps.signals.models import SignalHistory
from src.apps.patterns.domain.registry import sync_pattern_metadata
from src.apps.market_data.domain import utc_now


def _history_row(
    *,
    coin_id: int,
    timeframe: int,
    signal_type: str,
    market_regime: str,
    candle_timestamp,
    result_return: float | None,
    result_drawdown: float | None,
    profit_after_24h: float | None = None,
    profit_after_72h: float | None = None,
    maximum_drawdown: float | None = None,
) -> SignalHistory:
    return SignalHistory(
        coin_id=coin_id,
        timeframe=timeframe,
        signal_type=signal_type,
        confidence=0.75,
        market_regime=market_regime,
        candle_timestamp=candle_timestamp,
        profit_after_24h=profit_after_24h,
        profit_after_72h=profit_after_72h,
        maximum_drawdown=maximum_drawdown,
        result_return=result_return,
        result_drawdown=result_drawdown,
        evaluated_at=candle_timestamp + timedelta(hours=24),
    )


def test_pattern_statistics_helper_fallbacks() -> None:
    row = _history_row(
        coin_id=1,
        timeframe=15,
        signal_type="pattern_bull_flag",
        market_regime="bull_trend",
        candle_timestamp=utc_now(),
        result_return=0.01,
        result_drawdown=-0.02,
        profit_after_24h=0.02,
        profit_after_72h=0.03,
        maximum_drawdown=-0.01,
    )
    assert calculate_temperature(success_rate=0.7, sample_size=0, days_since_sample=1) == 0.0
    assert _select_return(row) == 0.03
    row.profit_after_72h = None
    assert _select_return(row) == 0.02
    row.profit_after_24h = None
    assert _select_return(row) == 0.01
    assert _select_drawdown(row) == -0.01
    row.maximum_drawdown = None
    assert _select_drawdown(row) == -0.02
    row.result_return = None
    row.result_drawdown = None
    assert _select_return(row) is None
    assert _select_drawdown(row) is None


def test_pattern_statistics_emits_lifecycle_events_and_skips_invalid_rows(db_session, monkeypatch, seeded_market) -> None:
    sync_pattern_metadata(db_session)
    db_session.execute(delete(SignalHistory))
    db_session.execute(delete(PatternStatistic))
    db_session.commit()

    coin_id = int(seeded_market["BTCUSD_EVT"]["coin_id"])
    start = utc_now() - timedelta(days=10)
    bull_registry = db_session.get(PatternRegistry, "bull_flag")
    bear_registry = db_session.get(PatternRegistry, "head_shoulders")
    assert bull_registry is not None and bear_registry is not None
    bull_registry.lifecycle_state = "DISABLED"
    bear_registry.lifecycle_state = "ACTIVE"
    db_session.commit()

    rows = []
    for index in range(25):
        rows.append(
            _history_row(
                coin_id=coin_id,
                timeframe=15,
                signal_type="pattern_bull_flag",
                market_regime="bull_trend",
                candle_timestamp=start + timedelta(minutes=15 * index),
                result_return=0.05,
                result_drawdown=-0.01,
            )
        )
        rows.append(
            _history_row(
                coin_id=coin_id,
                timeframe=60,
                signal_type="pattern_head_shoulders",
                market_regime="bear_trend",
                candle_timestamp=start + timedelta(hours=index),
                result_return=-0.04,
                result_drawdown=-0.03,
            )
        )
    rows.append(
        _history_row(
            coin_id=coin_id,
            timeframe=15,
            signal_type="golden_cross",
            market_regime="bull_trend",
            candle_timestamp=start,
            result_return=0.04,
            result_drawdown=-0.02,
        )
    )
    rows.append(
        _history_row(
            coin_id=coin_id,
            timeframe=15,
            signal_type="pattern_bull_flag",
            market_regime="bull_trend",
            candle_timestamp=start + timedelta(days=1),
            result_return=None,
            result_drawdown=-0.02,
        )
    )
    db_session.add_all(rows)
    db_session.commit()

    published: list[str] = []
    monkeypatch.setattr("src.apps.patterns.domain.statistics.publish_pattern_state_event", lambda event_type, **kwargs: published.append(event_type))
    result = refresh_pattern_statistics(db_session, emit_events=True)

    global_bull = db_session.get(PatternStatistic, ("bull_flag", 15, "all"))
    global_bear = db_session.get(PatternStatistic, ("head_shoulders", 60, "all"))
    assert result["status"] == "ok"
    assert global_bull is not None and global_bear is not None
    assert global_bull.success_rate == 1.0
    assert global_bear.success_rate == 0.0
    assert "pattern_enabled" in published
    assert "pattern_boosted" in published
    assert "pattern_disabled" in published
    assert "pattern_degraded" in published


def test_pattern_statistics_skip_cluster_rows(db_session, seeded_market) -> None:
    sync_pattern_metadata(db_session)
    db_session.execute(delete(SignalHistory))
    db_session.execute(delete(PatternStatistic))
    db_session.commit()

    coin_id = int(seeded_market["BTCUSD_EVT"]["coin_id"])
    timestamp = utc_now() - timedelta(days=2)
    db_session.add(
        _history_row(
            coin_id=coin_id,
            timeframe=15,
            signal_type="pattern_cluster_breakout",
            market_regime="bull_trend",
            candle_timestamp=timestamp,
            result_return=0.04,
            result_drawdown=-0.01,
        )
    )
    db_session.commit()

    refresh_pattern_statistics(db_session, emit_events=False)
    cluster_row = db_session.get(PatternStatistic, ("cluster_breakout", 15, "all"))
    assert cluster_row is None


def test_pattern_statistics_tolerates_missing_registry_rows(monkeypatch) -> None:
    class Result:
        def __init__(self, *, rows=None) -> None:
            self._rows = rows or []

        def all(self):
            return self._rows

    class SessionStub:
        def execute(self, _stmt):
            return Result(rows=[])

        def get(self, _model, _slug):
            return None

        def commit(self) -> None:
            return None

    monkeypatch.setattr("src.apps.patterns.domain.statistics.sync_pattern_metadata", lambda db: None)
    monkeypatch.setattr(
        "src.apps.patterns.domain.statistics.PATTERN_CATALOG",
        [SimpleNamespace(slug="ghost_pattern")],
    )
    monkeypatch.setattr("src.apps.patterns.domain.statistics.SUPPORTED_STATISTIC_TIMEFRAMES", (15,))
    monkeypatch.setattr("src.apps.patterns.domain.statistics._history_rows", lambda db: [])

    result = refresh_pattern_statistics(SessionStub(), emit_events=False)
    assert result["status"] == "ok"
    assert result["updated_registry"] == 1


def test_pattern_statistics_no_rows_and_unchanged_state_branches(db_session, monkeypatch, seeded_market) -> None:
    sync_pattern_metadata(db_session)
    db_session.execute(delete(SignalHistory))
    db_session.execute(delete(PatternStatistic))
    db_session.commit()

    original_catalog = __import__("src.apps.patterns.domain.statistics", fromlist=["PATTERN_CATALOG"]).PATTERN_CATALOG
    monkeypatch.setattr("src.apps.patterns.domain.statistics.PATTERN_CATALOG", [])
    result = refresh_pattern_statistics(db_session, emit_events=False)
    assert result["patterns"] == 0

    monkeypatch.setattr("src.apps.patterns.domain.statistics.PATTERN_CATALOG", original_catalog)
    sync_pattern_metadata(db_session)
    coin_id = int(seeded_market["BTCUSD_EVT"]["coin_id"])
    start = utc_now() - timedelta(days=3)
    registry = db_session.get(PatternRegistry, "bull_flag")
    assert registry is not None
    registry.lifecycle_state = "ACTIVE"
    db_session.add_all(
        [
            _history_row(
                coin_id=coin_id,
                timeframe=15,
                signal_type="pattern_bull_flag",
                market_regime="bull_trend",
                candle_timestamp=start + timedelta(minutes=15 * index),
                result_return=0.02 if index < 9 else -0.01,
                result_drawdown=-0.01,
            )
            for index in range(15)
        ]
    )
    db_session.commit()

    published: list[str] = []
    monkeypatch.setattr("src.apps.patterns.domain.statistics.publish_pattern_state_event", lambda event_type, **kwargs: published.append(event_type))
    unchanged = refresh_pattern_statistics(db_session, emit_events=True)
    assert unchanged["status"] == "ok"
    assert "pattern_enabled" not in published
    assert "pattern_disabled" not in published
    assert "pattern_boosted" not in published
    assert "pattern_degraded" not in published


def test_pattern_statistics_unchanged_lifecycle_branch_with_stub(monkeypatch) -> None:
    class Result:
        def __init__(self, *, rows=None) -> None:
            self._rows = rows or []

        def all(self):
            return self._rows

    class RegistryRow:
        slug = "ghost_pattern"
        enabled = True
        lifecycle_state = "ACTIVE"

    class SessionStub:
        def __init__(self) -> None:
            self.registry_row = RegistryRow()

        def execute(self, _stmt):
            return Result(rows=[])

        def get(self, model, key):
            if model is PatternRegistry and key == "ghost_pattern":
                return self.registry_row
            return None

        def commit(self) -> None:
            return None

    monkeypatch.setattr("src.apps.patterns.domain.statistics.sync_pattern_metadata", lambda db: None)
    monkeypatch.setattr("src.apps.patterns.domain.statistics._history_rows", lambda db: [])
    monkeypatch.setattr("src.apps.patterns.domain.statistics.PATTERN_CATALOG", [SimpleNamespace(slug="ghost_pattern")])
    monkeypatch.setattr("src.apps.patterns.domain.statistics.SUPPORTED_STATISTIC_TIMEFRAMES", (15,))
    monkeypatch.setattr("src.apps.patterns.domain.statistics.resolve_lifecycle_state", lambda temperature, enabled: SimpleNamespace(value="ACTIVE"))

    published: list[str] = []
    monkeypatch.setattr("src.apps.patterns.domain.statistics.publish_pattern_state_event", lambda event_type, **kwargs: published.append(event_type))
    result = refresh_pattern_statistics(SessionStub(), emit_events=True)
    assert result["status"] == "ok"
    assert published == []
