from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import delete, select

from src.apps.patterns.domain import decision as decision_domain
from src.apps.patterns.domain import risk as risk_domain
from src.apps.patterns.domain import strategy as strategy_domain
from src.apps.market_data.repos import candle_close_timestamp
from src.apps.patterns.domain.decision import (
    _cycle_alignment,
    _decision_from_score,
    _historical_pattern_success,
    _regime_alignment,
    _sector_strength_factor,
    evaluate_investment_decision,
)
from src.apps.patterns.domain.narrative import SectorNarrative
from src.apps.patterns.domain.risk import _risk_adjusted_decision, update_risk_metrics
from src.apps.patterns.domain.strategy import (
    StrategyCandidate,
    _candidate_definitions,
    _candle_index_map,
    _sharpe_ratio,
    _signal_outcome,
    _signal_stack_bias,
    _upsert_strategy,
    refresh_strategies,
    strategy_alignment,
)
from src.apps.signals.models import InvestmentDecision, RiskMetric, Strategy, StrategyPerformance, StrategyRule
from tests.factories.market_data import build_candle_points


def _signal(
    signal_type: str,
    *,
    confidence: float = 0.8,
    priority_score: float | None = None,
    regime_alignment: float = 1.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        signal_type=signal_type,
        confidence=confidence,
        priority_score=priority_score if priority_score is not None else confidence,
        regime_alignment=regime_alignment,
    )


def test_decision_helpers_cover_guard_and_branch_paths(db_session, seeded_api_state, monkeypatch) -> None:
    btc = seeded_api_state["btc"]
    sol = seeded_api_state["sol"]
    timestamp = datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)

    assert _regime_alignment([]) == 1.0
    assert _regime_alignment([_signal("pattern_bull_flag", regime_alignment=1.2), _signal("pattern_head_shoulders", regime_alignment=0.8)]) == 1.0

    assert _cycle_alignment(None, 1) == 1.0
    assert _cycle_alignment(SimpleNamespace(cycle_phase="LATE_MARKUP"), 1) == 0.95
    assert _cycle_alignment(SimpleNamespace(cycle_phase="LATE_MARKUP"), -1) == 1.06
    assert _cycle_alignment(SimpleNamespace(cycle_phase="MARKDOWN"), -1) == 1.18
    assert _cycle_alignment(SimpleNamespace(cycle_phase="MARKDOWN"), 1) == 0.82
    assert _cycle_alignment(SimpleNamespace(cycle_phase="UNKNOWN"), 1) == 1.0

    assert _sector_strength_factor(sol, SimpleNamespace(market_cap=200_000_000.0), None, None) == 1.0
    assert _sector_strength_factor(
        sol,
        SimpleNamespace(market_cap=200_000_000.0),
        SimpleNamespace(sector_strength=0.01, relative_strength=0.01),
        None,
    ) > 1.0
    assert _sector_strength_factor(
        sol,
        SimpleNamespace(market_cap=200_000_000.0),
        SimpleNamespace(sector_strength=0.0, relative_strength=0.0),
        SectorNarrative(
            timeframe=15,
            top_sector="payments",
            rotation_state="broadening",
            btc_dominance=0.55,
            capital_wave="btc",
        ),
    ) < 1.0
    assert _sector_strength_factor(
        btc,
        SimpleNamespace(market_cap=20_000_000_000.0),
        SimpleNamespace(sector_strength=0.04, relative_strength=0.03),
        SectorNarrative(
            timeframe=15,
            top_sector="store_of_value",
            rotation_state="leaders",
            btc_dominance=0.48,
            capital_wave="large_caps",
        ),
    ) > 1.0
    assert _sector_strength_factor(
        btc,
        SimpleNamespace(market_cap=20_000_000_000.0),
        SimpleNamespace(sector_strength=0.04, relative_strength=0.03),
        SectorNarrative(
            timeframe=15,
            top_sector="store_of_value",
            rotation_state="leaders",
            btc_dominance=0.48,
            capital_wave="sector_leaders",
        ),
    ) > 1.0
    assert _sector_strength_factor(
        sol,
        SimpleNamespace(market_cap=3_000_000_000.0),
        SimpleNamespace(sector_strength=0.04, relative_strength=0.03),
        SectorNarrative(
            timeframe=15,
            top_sector="payments",
            rotation_state="mid_caps",
            btc_dominance=0.48,
            capital_wave="mid_caps",
        ),
    ) > 1.0
    assert _sector_strength_factor(
        sol,
        SimpleNamespace(market_cap=3_000_000_000.0),
        SimpleNamespace(sector_strength=0.04, relative_strength=0.03),
        SectorNarrative(
            timeframe=15,
            top_sector="payments",
            rotation_state="mixed",
            btc_dominance=0.48,
            capital_wave="large_caps",
        ),
    ) > 1.0
    assert _sector_strength_factor(
        sol,
        SimpleNamespace(market_cap=120_000_000.0),
        SimpleNamespace(sector_strength=0.04, relative_strength=0.03),
        SectorNarrative(
            timeframe=15,
            top_sector="payments",
            rotation_state="micro_caps",
            btc_dominance=0.48,
            capital_wave="micro_caps",
        ),
    ) > 1.0

    assert _historical_pattern_success(db_session, {"unknown_pattern_slug"}, 15, "bull_trend") == 0.55
    assert _decision_from_score(0.8, 0.4) == "ACCUMULATE"
    assert _decision_from_score(1.2, 0.4) == "BUY"
    assert _decision_from_score(1.8, -0.7) == "STRONG_SELL"
    assert _decision_from_score(0.8, -0.4) == "REDUCE"

    monkeypatch.setattr(decision_domain, "_latest_pattern_timestamp", lambda *_args, **_kwargs: timestamp)
    monkeypatch.setattr(decision_domain, "_latest_signal_stack", lambda *_args, **_kwargs: [])
    signal_stack_missing = evaluate_investment_decision(db_session, coin_id=int(sol.id), timeframe=15, emit_event=False)
    assert signal_stack_missing["reason"] == "signal_stack_not_found"

    monkeypatch.setattr(
        decision_domain,
        "_latest_signal_stack",
        lambda *_args, **_kwargs: [_signal("pattern_bull_flag", confidence=0.82, priority_score=0.91)],
    )
    coin_missing = evaluate_investment_decision(db_session, coin_id=999999, timeframe=15, emit_event=False)
    assert coin_missing["reason"] == "coin_not_found"

    db_session.execute(
        delete(InvestmentDecision).where(
            InvestmentDecision.coin_id == int(sol.id),
            InvestmentDecision.timeframe == 240,
        )
    )
    db_session.commit()

    monkeypatch.setattr(
        decision_domain,
        "_latest_signal_stack",
        lambda *_args, **_kwargs: [_signal("pattern_unmapped", confidence=0.74, priority_score=0.74)],
    )
    monkeypatch.setattr(
        decision_domain,
        "slug_from_signal_type",
        lambda signal_type: None if signal_type == "pattern_unmapped" else signal_type.removeprefix("pattern_"),
    )
    monkeypatch.setattr(decision_domain, "build_sector_narratives", lambda _db: [])
    monkeypatch.setattr(decision_domain, "strategy_alignment", lambda *args, **kwargs: (1.0, []))
    slug_none_path = evaluate_investment_decision(db_session, coin_id=int(sol.id), timeframe=240, emit_event=False)
    assert slug_none_path["status"] == "ok"


def test_risk_helpers_cover_fallbacks_and_bearish_paths(db_session, seeded_api_state, monkeypatch) -> None:
    btc = seeded_api_state["btc"]

    db_session.execute(
        delete(RiskMetric).where(
            RiskMetric.coin_id == int(btc.id),
            RiskMetric.timeframe == 15,
        )
    )
    db_session.commit()

    monkeypatch.setattr(risk_domain, "_latest_indicator_value", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(risk_domain, "_latest_close", lambda *_args, **_kwargs: None)

    payload = update_risk_metrics(db_session, coin_id=int(btc.id), timeframe=15, commit=False)
    assert payload["status"] == "ok"
    db_session.flush()
    assert db_session.get(RiskMetric, (int(btc.id), 15)) is not None

    assert _risk_adjusted_decision("BUY", 0.9) == "BUY"
    assert _risk_adjusted_decision("STRONG_BUY", 1.4) == "STRONG_BUY"
    assert _risk_adjusted_decision("SELL", 0.9) == "SELL"
    assert _risk_adjusted_decision("SELL", 0.2) == "HOLD"
    assert _risk_adjusted_decision("STRONG_SELL", 1.4) == "STRONG_SELL"
    assert _risk_adjusted_decision("REDUCE", 0.5) == "REDUCE"
    assert _risk_adjusted_decision("UNKNOWN", 0.9) == "HOLD"


def test_strategy_helpers_cover_alignment_and_update_paths(db_session) -> None:
    bullish_signal = _signal("pattern_bull_flag", confidence=0.81, priority_score=0.9)
    bearish_signal = _signal("pattern_head_shoulders", confidence=0.78, priority_score=0.85)

    assert _signal_stack_bias([_signal("market_snapshot", confidence=0.0, priority_score=0.0)]) == 1
    assert _signal_stack_bias([bearish_signal]) == -1

    candles = build_candle_points(closes=[100.0 + index for index in range(20)], volumes=[1000.0] * 20)
    assert _signal_outcome(
        signals=[bullish_signal],
        candles=candles,
        index_map={},
        timeframe=15,
        candle_timestamp=candle_close_timestamp(candles[5].timestamp, 15),
    ) is None
    assert _signal_outcome(
        signals=[bullish_signal],
        candles=candles,
        index_map=_candle_index_map(candles),
        timeframe=15,
        candle_timestamp=candle_close_timestamp(candles[-1].timestamp, 15),
    ) is None

    descending = build_candle_points(closes=[140.0 - (index * 2.0) for index in range(20)], volumes=[1000.0] * 20)
    bearish_outcome = _signal_outcome(
        signals=[bearish_signal],
        candles=descending,
        index_map=_candle_index_map(descending),
        timeframe=15,
        candle_timestamp=candle_close_timestamp(descending[5].timestamp, 15),
    )
    assert bearish_outcome is not None
    assert bearish_outcome[0] > 0
    assert bearish_outcome[2] is True

    assert _candidate_definitions(
        timeframe=15,
        signals=[_signal("market_snapshot", confidence=0.0, priority_score=0.0)],
        regime="bull_trend",
        sector="store_of_value",
        cycle="MARKUP",
    ) == []
    assert len(
        _candidate_definitions(
            timeframe=15,
            signals=[bullish_signal],
            regime="*",
            sector="*",
            cycle="*",
        )
    ) == 1
    assert len(
        _candidate_definitions(
            timeframe=15,
            signals=[bullish_signal],
            regime="bull_trend",
            sector="store_of_value",
            cycle="MARKUP",
        )
    ) == 4

    candidates = _candidate_definitions(
        timeframe=15,
        signals=[bullish_signal, bullish_signal, _signal("pattern_breakout_retest", confidence=0.76, priority_score=0.82)],
        regime="bull_trend",
        sector="store_of_value",
        cycle="MARKUP",
    )
    assert len(candidates) == 7
    assert _sharpe_ratio([0.04]) == 0.0
    assert _sharpe_ratio([0.03, 0.03, 0.03]) == 0.0

    candidate = StrategyCandidate(
        timeframe=15,
        tokens=("bull_flag",),
        regime="bull_trend",
        sector="store_of_value",
        cycle="MARKUP",
        min_confidence=0.75,
    )
    strategy_id = _upsert_strategy(
        db_session,
        candidate=candidate,
        sample_size=12,
        win_rate=0.68,
        avg_return=0.04,
        sharpe_ratio=0.91,
        max_drawdown=-0.08,
        enabled=True,
    )
    strategy_id_updated = _upsert_strategy(
        db_session,
        candidate=candidate,
        sample_size=16,
        win_rate=0.64,
        avg_return=0.03,
        sharpe_ratio=0.72,
        max_drawdown=-0.11,
        enabled=False,
    )
    db_session.commit()
    assert strategy_id == strategy_id_updated
    stored = db_session.get(Strategy, strategy_id)
    assert stored is not None and stored.enabled is False
    performance = db_session.get(StrategyPerformance, strategy_id)
    assert performance is not None and performance.sample_size == 16

    skipped = Strategy(name="No Perf", description="missing performance", enabled=True)
    db_session.add(skipped)
    db_session.flush()
    db_session.add(
        StrategyRule(
            strategy_id=skipped.id,
            pattern_slug="bull_flag",
            regime="bull_trend",
            sector="store_of_value",
            cycle="MARKUP",
            min_confidence=0.7,
        )
    )

    matched = Strategy(name="Exact Match", description="fully specified", enabled=True)
    db_session.add(matched)
    db_session.flush()
    db_session.add(
        StrategyRule(
            strategy_id=matched.id,
            pattern_slug="bull_flag",
            regime="bull_trend",
            sector="store_of_value",
            cycle="MARKUP",
            min_confidence=0.8,
        )
    )
    db_session.add(
        StrategyPerformance(
            strategy_id=matched.id,
            sample_size=16,
            win_rate=0.7,
            avg_return=0.04,
            sharpe_ratio=0.9,
            max_drawdown=-0.08,
        )
    )
    db_session.commit()

    assert strategy_alignment(
        db_session,
        tokens={"breakout_retest"},
        token_confidence={"breakout_retest": 0.95},
        regime="bull_trend",
        sector="store_of_value",
        cycle="MARKUP",
    ) == (1.0, [])
    assert strategy_alignment(
        db_session,
        tokens={"bull_flag"},
        token_confidence={"bull_flag": 0.95},
        regime="bear_trend",
        sector="store_of_value",
        cycle="MARKUP",
    ) == (1.0, [])
    assert strategy_alignment(
        db_session,
        tokens={"bull_flag"},
        token_confidence={"bull_flag": 0.95},
        regime="bull_trend",
        sector="payments",
        cycle="MARKUP",
    ) == (1.0, [])
    assert strategy_alignment(
        db_session,
        tokens={"bull_flag"},
        token_confidence={"bull_flag": 0.95},
        regime="bull_trend",
        sector="store_of_value",
        cycle="MARKDOWN",
    ) == (1.0, [])
    assert strategy_alignment(
        db_session,
        tokens={"bull_flag"},
        token_confidence={"bull_flag": 0.6},
        regime="bull_trend",
        sector="store_of_value",
        cycle="MARKUP",
    ) == (1.0, [])

    aligned_score, aligned_names = strategy_alignment(
        db_session,
        tokens={"bull_flag"},
        token_confidence={"bull_flag": 0.95},
        regime="bull_trend",
        sector="store_of_value",
        cycle="MARKUP",
    )
    assert aligned_score > 1.0
    assert aligned_names == ["Exact Match"]


def test_refresh_strategies_guard_paths_disable_unseen_rows(db_session, seeded_api_state, monkeypatch) -> None:
    btc = seeded_api_state["btc"]
    stale = Strategy(name="Stale Strategy", description="to disable", enabled=True)
    db_session.add(stale)
    db_session.commit()

    timestamp = seeded_api_state["signal_timestamp"]
    candles = build_candle_points(closes=[100.0 + index for index in range(40)], volumes=[1000.0] * 40)

    monkeypatch.setattr(strategy_domain, "_signal_groups", lambda _db: {(int(btc.id), 15): {}})
    disabled = refresh_strategies(db_session)
    assert disabled["strategies"] == 0
    assert db_session.scalar(select(Strategy.enabled).where(Strategy.id == stale.id)) is False

    monkeypatch.setattr(
        strategy_domain,
        "_signal_groups",
        lambda _db: {(int(btc.id), 15): {timestamp: [_signal("pattern_bull_flag")]}}
    )
    monkeypatch.setattr(strategy_domain, "fetch_candle_points_between", lambda *args, **kwargs: candles[:10])
    short_candles = refresh_strategies(db_session)
    assert short_candles["strategies"] == 0

    monkeypatch.setattr(strategy_domain, "fetch_candle_points_between", lambda *args, **kwargs: candles)
    monkeypatch.setattr(strategy_domain, "_signal_outcome", lambda **kwargs: None)
    skipped_outcome = refresh_strategies(db_session)
    assert skipped_outcome["strategies"] == 0

    open_timestamp = candles[2].timestamp
    monkeypatch.setattr(
        strategy_domain,
        "_signal_groups",
        lambda _db: {(int(btc.id), 15): {candle_close_timestamp(open_timestamp, 15): [_signal("pattern_bull_flag")]}}
    )
    monkeypatch.setattr(strategy_domain, "_signal_outcome", lambda **kwargs: (0.05, -0.01, True))
    earlier_open_timestamp = candles[0].timestamp - (candles[1].timestamp - candles[0].timestamp)
    monkeypatch.setattr(
        strategy_domain,
        "_signal_groups",
        lambda _db: {(int(btc.id), 15): {candle_close_timestamp(earlier_open_timestamp, 15): [_signal("pattern_bull_flag")]}}
    )
    missing_index = refresh_strategies(db_session)
    assert missing_index["strategies"] == 0

    monkeypatch.setattr(
        strategy_domain,
        "_signal_groups",
        lambda _db: {(int(btc.id), 15): {candle_close_timestamp(open_timestamp, 15): [_signal("pattern_bull_flag")]}}
    )
    short_window = refresh_strategies(db_session)
    assert short_window["strategies"] == 0
