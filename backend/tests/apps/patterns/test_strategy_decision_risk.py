from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from app.apps.cross_market.models import SectorMetric
from app.apps.indicators.models import CoinMetrics
from app.apps.market_data.repos import candle_close_timestamp, fetch_candle_points
from app.apps.patterns.domain.decision import (
    _decision_confidence,
    _decision_from_score,
    _historical_pattern_success,
    _sector_strength_factor,
    calculate_decision_score,
    evaluate_investment_decision,
    refresh_investment_decisions,
)
from app.apps.patterns.domain.narrative import SectorNarrative
from app.apps.patterns.domain.risk import (
    calculate_liquidity_score,
    calculate_risk_adjusted_score,
    calculate_slippage_risk,
    calculate_volatility_risk,
    evaluate_final_signal,
    refresh_final_signals,
    update_risk_metrics,
)
from app.apps.patterns.domain.strategy import (
    _candle_index_map,
    _candidate_definitions,
    _round_confidence,
    _sharpe_ratio,
    _signal_tokens,
    _strategy_enabled,
    _trend_score_from_indicators,
    refresh_strategies,
    strategy_alignment,
)
from app.apps.signals.models import FinalSignal, InvestmentDecision, Signal
from tests.factories.market_data import build_candle_points
from tests.fusion_support import insert_signals


def test_strategy_domain_helpers_and_refresh_real_signal_groups(db_session, seeded_market, seeded_api_state, monkeypatch) -> None:
    btc = seeded_api_state["btc"]
    btc_metrics = db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(btc.id)))
    assert btc_metrics is not None

    candles = build_candle_points(closes=[100.0 + 0.4 * index for index in range(12)], volumes=[1000.0] * 12)
    assert _round_confidence(0.87) == 0.85
    assert _candle_index_map(candles)[candles[0].timestamp] == 0
    assert _trend_score_from_indicators(
        {
            "price_current": 110.0,
            "sma_200": 100.0,
            "ema_20": 108.0,
            "ema_50": 104.0,
            "macd_histogram": 0.5,
            "adx_14": 24.0,
        }
    ) > 50
    assert _trend_score_from_indicators(
        {
            "price_current": 90.0,
            "sma_200": 100.0,
            "ema_20": 94.0,
            "ema_50": 98.0,
            "macd_histogram": -0.5,
            "adx_14": 18.0,
        }
    ) < 50

    seed_signals = db_session.scalars(
        select(Signal).where(Signal.coin_id == int(btc.id), Signal.timeframe == 15).order_by(Signal.created_at.asc())
    ).all()
    ordered_tokens, best_confidence = _signal_tokens(seed_signals)
    assert ordered_tokens[0] == "bull_flag"
    assert best_confidence["bull_flag"] >= 0.74

    candidates = _candidate_definitions(
        timeframe=15,
        signals=seed_signals,
        regime="bull_trend",
        sector="store_of_value",
        cycle="MARKUP",
    )
    assert candidates
    assert any(candidate.tokens == ("bull_flag",) for candidate in candidates)
    assert _sharpe_ratio([0.03, 0.01, 0.04, 0.02]) > 0
    assert _strategy_enabled(12, 0.61, 0.02, 0.8, -0.12)
    assert not _strategy_enabled(4, 0.61, 0.02, 0.8, -0.12)

    alignment, names = strategy_alignment(
        db_session,
        tokens={"bull_flag"},
        token_confidence={"bull_flag": 0.83},
        regime="bull_trend",
        sector="store_of_value",
        cycle="markup",
    )
    assert alignment > 1.0
    assert names

    db_session.add(
        SectorMetric(
            sector_id=int(btc.sector_id),
            timeframe=15,
            sector_strength=0.85,
            relative_strength=0.71,
            capital_flow=0.44,
            avg_price_change_24h=4.2,
            avg_volume_change_24h=15.0,
            volatility=0.041,
            trend="up",
            updated_at=seeded_api_state["signal_timestamp"],
        )
    )
    synthetic_candles = build_candle_points(
        closes=[100.0 + 0.35 * index for index in range(320)],
        volumes=[1000.0 + (index % 6) * 120.0 for index in range(320)],
        start=seeded_api_state["signal_timestamp"] - timedelta(minutes=15 * 319),
    )
    signal_indices = range(240, 248)
    for index in signal_indices:
        timestamp = candle_close_timestamp(synthetic_candles[index].timestamp, 15)
        insert_signals(
            db_session,
            coin_id=int(btc.id),
            timeframe=15,
            candle_timestamp=timestamp,
            items=[
                ("pattern_bull_flag", 0.84),
                ("pattern_breakout_retest", 0.81),
            ],
        )
    db_session.commit()

    monkeypatch.setattr("app.apps.patterns.domain.strategy.fetch_candle_points_between", lambda db, coin_id, timeframe, start, end: synthetic_candles)
    refreshed = refresh_strategies(db_session)
    assert refreshed["status"] == "ok"
    assert refreshed["strategies"] > 0
    assert refreshed["enabled"] > 0


def test_decision_and_risk_domains_cover_real_business_flow(db_session, seeded_api_state, monkeypatch) -> None:
    btc = seeded_api_state["btc"]
    sol = seeded_api_state["sol"]

    assert calculate_decision_score(
        signal_priority=1.2,
        regime_alignment=1.1,
        sector_strength=1.05,
        cycle_alignment=1.08,
        historical_pattern_success=0.72,
        strategy_alignment=1.04,
    ) > 1.0
    assert _decision_from_score(0.2, 0.0) == "HOLD"
    assert _decision_from_score(1.8, 0.7) == "STRONG_BUY"
    assert _decision_from_score(1.2, -0.4) == "SELL"
    assert _decision_confidence(
        score=1.4,
        bias_ratio=0.62,
        factors=SimpleNamespace(
            regime_alignment=1.1,
            cycle_alignment=1.0,
            historical_pattern_success=0.7,
            sector_strength=1.05,
            strategy_alignment=1.08,
        ),
    ) > 0.3
    assert _historical_pattern_success(db_session, set(), 15) == 0.55
    assert _historical_pattern_success(db_session, {"bull_flag"}, 15, "bull_trend") > 0.55
    assert _sector_strength_factor(
        btc,
        SimpleNamespace(market_cap=20_000_000_000),
        SimpleNamespace(sector_strength=0.04, relative_strength=0.03),
        SectorNarrative(timeframe=15, top_sector="store_of_value", rotation_state=None, btc_dominance=0.5, capital_wave="large_caps"),
    ) > 1.0

    db_session.execute(delete(InvestmentDecision))
    db_session.commit()

    published_decisions: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.apps.patterns.domain.decision.publish_investment_decision_message",
        lambda coin, timeframe, decision, confidence, score, reason: published_decisions.append(
            {
                "coin": coin.symbol,
                "timeframe": timeframe,
                "decision": decision,
                "confidence": confidence,
                "score": score,
            }
        ),
    )
    decision = evaluate_investment_decision(db_session, coin_id=int(btc.id), timeframe=15, emit_event=True)
    assert decision["status"] == "ok"
    assert decision["decision"] in {"ACCUMULATE", "BUY", "STRONG_BUY"}
    assert published_decisions and published_decisions[0]["coin"] == "BTCUSD_EVT"
    unchanged = evaluate_investment_decision(db_session, coin_id=int(btc.id), timeframe=15, emit_event=False)
    assert unchanged["reason"] == "decision_unchanged"
    assert evaluate_investment_decision(db_session, coin_id=int(sol.id), timeframe=15, emit_event=False)["reason"] == "pattern_signals_not_found"

    decision_refresh = refresh_investment_decisions(db_session, lookback_days=30, emit_events=False)
    assert decision_refresh["status"] == "ok"
    assert decision_refresh["candidates"] >= 1

    assert calculate_liquidity_score(volume_24h=0.0, market_cap=0.0) == 0.1
    assert calculate_liquidity_score(volume_24h=5_000_000.0, market_cap=50_000_000_000.0) > 0.5
    assert 0.02 <= calculate_slippage_risk(volume_24h=1_000_000.0, market_cap=3_000_000_000.0) <= 0.98
    assert calculate_volatility_risk(atr_14=0.0, price=0.0) == 0.5
    assert calculate_risk_adjusted_score(
        decision_score=1.4,
        liquidity_score=0.8,
        slippage_risk=0.2,
        volatility_risk=0.1,
    ) > 0.0

    assert update_risk_metrics(db_session, coin_id=999999, timeframe=15)["reason"] == "coin_not_found"
    risk_metrics = update_risk_metrics(db_session, coin_id=int(btc.id), timeframe=15)
    assert risk_metrics["status"] == "ok"
    assert risk_metrics["liquidity_score"] > 0.0

    db_session.execute(delete(FinalSignal))
    db_session.commit()

    published_final_signals: list[dict[str, object]] = []
    monkeypatch.setattr(
        "app.apps.patterns.domain.risk.publish_investment_signal_message",
        lambda coin, timeframe, decision, confidence, risk_score, reason: published_final_signals.append(
            {
                "coin": coin.symbol,
                "timeframe": timeframe,
                "decision": decision,
                "confidence": confidence,
                "risk_score": risk_score,
            }
        ),
    )
    assert evaluate_final_signal(db_session, coin_id=999999, timeframe=15)["reason"] == "coin_not_found"
    assert evaluate_final_signal(db_session, coin_id=int(sol.id), timeframe=15)["reason"] == "decision_not_found"
    final_signal = evaluate_final_signal(db_session, coin_id=int(btc.id), timeframe=15, emit_event=True)
    assert final_signal["status"] == "ok"
    assert final_signal["decision"] in {"ACCUMULATE", "BUY", "STRONG_BUY", "HOLD"}
    assert published_final_signals and published_final_signals[0]["coin"] == "BTCUSD_EVT"
    assert evaluate_final_signal(db_session, coin_id=int(btc.id), timeframe=15, emit_event=False)["reason"] == "final_signal_unchanged"

    final_refresh = refresh_final_signals(db_session, lookback_days=30, emit_events=False)
    assert final_refresh["status"] == "ok"
    assert final_refresh["candidates"] >= 1
