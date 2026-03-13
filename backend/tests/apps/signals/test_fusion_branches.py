from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import select

from src.apps.patterns.models import PatternStatistic
from src.apps.patterns.domain.registry import sync_pattern_metadata
from src.apps.signals.fusion import (
    _decision_from_scores,
    _fuse_signals,
    _recent_signals,
    _regime_weight,
    _signal_archetype,
    _signal_regime,
    _signal_success_rate,
    evaluate_market_decision,
)
from src.apps.signals.models import MarketDecision, Signal
from src.core.db.persistence import PERSISTENCE_LOGGER
from tests.cross_market_support import DEFAULT_START
from tests.fusion_support import create_test_coin, replace_pattern_statistics, upsert_coin_metrics
from tests.portfolio_support import create_market_decision


def test_fusion_helper_branches(db_session) -> None:
    sync_pattern_metadata(db_session)
    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    timestamp = DEFAULT_START
    db_session.add_all(
        [
            Signal(coin_id=int(coin.id), timeframe=15, signal_type="pattern_bull_flag", confidence=0.8, priority_score=1.0, context_score=1.0, regime_alignment=1.0, candle_timestamp=timestamp),
            Signal(coin_id=int(coin.id), timeframe=15, signal_type="pattern_head_shoulders", confidence=0.75, priority_score=1.0, context_score=1.0, regime_alignment=1.0, candle_timestamp=timestamp + timedelta(minutes=15)),
            Signal(coin_id=int(coin.id), timeframe=15, signal_type="pattern_cluster_breakout", confidence=0.7, priority_score=1.0, context_score=1.0, regime_alignment=1.0, candle_timestamp=timestamp + timedelta(minutes=30)),
            Signal(coin_id=int(coin.id), timeframe=15, signal_type="pattern_hierarchy_trend", confidence=0.7, priority_score=1.0, context_score=1.0, regime_alignment=1.0, candle_timestamp=timestamp + timedelta(minutes=45)),
        ]
    )
    db_session.add(
        PatternStatistic(
            pattern_slug="bull_flag",
            timeframe=15,
            market_regime="all",
            sample_size=20,
            total_signals=20,
            successful_signals=15,
            success_rate=0.75,
            avg_return=0.03,
            avg_drawdown=-0.02,
            temperature=0.8,
            enabled=True,
        )
    )
    db_session.commit()

    recent = _recent_signals(db_session, coin_id=int(coin.id), timeframe=15)
    assert len(recent) == 3
    assert _signal_success_rate(db_session, recent[0], "bull_trend") >= 0.35
    assert _signal_success_rate(db_session, SimpleNamespace(signal_type="pattern_cluster_breakout", timeframe=15), None) == 0.55
    assert _signal_success_rate(db_session, SimpleNamespace(signal_type="custom_unknown", timeframe=15), None) == 0.55
    assert _signal_archetype("pattern_bollinger_squeeze") == "breakout"
    assert _signal_archetype("pattern_head_shoulders") == "reversal"
    assert _signal_archetype("pattern_rsi_divergence") == "mean_reversion"
    assert _regime_weight(SimpleNamespace(signal_type="pattern_bull_flag", confidence=0.8), "bull_trend") > 1.0
    assert _regime_weight(SimpleNamespace(signal_type="pattern_head_shoulders", confidence=0.8), "bear_trend") > 1.0
    assert _regime_weight(SimpleNamespace(signal_type="pattern_bollinger_squeeze", confidence=0.8), "high_volatility") > 1.0
    assert _decision_from_scores(bullish_score=0.0, bearish_score=0.0, total_score=0.1)[0] == "WATCH"
    assert _decision_from_scores(bullish_score=1.0, bearish_score=0.95, total_score=2.1)[0] == "HOLD"
    assert _decision_from_scores(bullish_score=0.2, bearish_score=1.3, total_score=1.5)[0] == "SELL"
    assert _fuse_signals(db_session, signals=[], regime="bull_trend") is None


def test_evaluate_market_decision_skip_and_unchanged_branches(db_session, monkeypatch) -> None:
    coin = create_test_coin(db_session, symbol="ETHUSD_EVT", name="Ethereum Event Test")
    upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=15)

    monkeypatch.setattr("src.apps.signals.fusion.enrich_signal_context", lambda *args, **kwargs: {"status": "ok"})
    skipped = evaluate_market_decision(db_session, coin_id=int(coin.id), timeframe=15, emit_event=False)
    assert skipped["reason"] == "signals_not_found"

    timestamp = DEFAULT_START + timedelta(hours=1)
    replace_pattern_statistics(
        db_session,
        timeframe=15,
        rows=[("bull_flag", "all", 0.72, 60)],
    )
    db_session.add(
        Signal(
            coin_id=int(coin.id),
            timeframe=15,
            signal_type="pattern_bull_flag",
            confidence=0.82,
            priority_score=1.0,
            context_score=1.0,
            regime_alignment=1.0,
            candle_timestamp=timestamp,
        )
    )
    db_session.commit()

    first = evaluate_market_decision(db_session, coin_id=int(coin.id), timeframe=15, emit_event=False)
    unchanged = evaluate_market_decision(db_session, coin_id=int(coin.id), timeframe=15, emit_event=False)
    assert first["status"] == "ok"
    assert unchanged["reason"] == "decision_unchanged"


def test_evaluate_market_decision_disables_nested_context_commit(db_session, monkeypatch) -> None:
    coin = create_test_coin(db_session, symbol="LINKUSD_EVT", name="Chainlink Event Test")
    upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=15)
    captured: dict[str, object] = {}

    def _capture_context(*args, **kwargs):
        del args
        captured.update(kwargs)
        return {"status": "ok"}

    monkeypatch.setattr("src.apps.signals.fusion.enrich_signal_context", _capture_context)
    skipped = evaluate_market_decision(db_session, coin_id=int(coin.id), timeframe=15, emit_event=False)

    assert skipped["reason"] == "signals_not_found"
    assert captured["commit"] is False
    assert int(captured["coin_id"]) == int(coin.id)
    assert int(captured["timeframe"]) == 15


def test_evaluate_market_decision_emits_compatibility_execution_logs(db_session, monkeypatch) -> None:
    coin = create_test_coin(db_session, symbol="ATOMUSD_EVT", name="Cosmos Event Test")
    upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=15)
    events: list[str] = []

    def _log(level: int, message: str, *args, **kwargs) -> None:
        del level, args, kwargs
        events.append(message)

    monkeypatch.setattr(PERSISTENCE_LOGGER, "log", _log)
    monkeypatch.setattr("src.apps.signals.fusion.enrich_signal_context", lambda *args, **kwargs: {"status": "ok"})

    result = evaluate_market_decision(db_session, coin_id=int(coin.id), timeframe=15, emit_event=False)

    assert result["reason"] == "signals_not_found"
    assert "compat.evaluate_market_decision.deprecated" in events
    assert "compat.evaluate_market_decision.execute" in events
    assert "compat.evaluate_market_decision.result" in events


def test_evaluate_market_decision_handles_null_fusion_window(db_session, monkeypatch) -> None:
    coin = create_test_coin(db_session, symbol="SOLUSD_EVT", name="Solana Event Test")
    upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=15)
    db_session.add(
        Signal(
            coin_id=int(coin.id),
            timeframe=15,
            signal_type="pattern_bull_flag",
            confidence=0.8,
            priority_score=1.0,
            context_score=1.0,
            regime_alignment=1.0,
            candle_timestamp=DEFAULT_START,
        )
    )
    db_session.commit()
    monkeypatch.setattr("src.apps.signals.fusion.enrich_signal_context", lambda *args, **kwargs: {"status": "ok"})
    monkeypatch.setattr("src.apps.signals.fusion._fuse_signals", lambda *args, **kwargs: None)
    result = evaluate_market_decision(db_session, coin_id=int(coin.id), timeframe=15, emit_event=False)
    assert result["reason"] == "fusion_window_empty"


def test_fusion_additional_regime_and_event_branches(db_session, monkeypatch) -> None:
    assert _signal_regime(None, 15) is None
    assert _regime_weight(SimpleNamespace(signal_type="pattern_inverse_head_shoulders", confidence=0.8), "bull_trend") == 1.05
    assert _regime_weight(SimpleNamespace(signal_type="pattern_bull_flag", confidence=0.8), "bear_trend") == 0.8
    assert _regime_weight(SimpleNamespace(signal_type="pattern_bear_flag", confidence=0.8), "bear_trend") == 1.2
    assert _regime_weight(SimpleNamespace(signal_type="pattern_custom", confidence=0.8), "bear_trend") == 1.0
    assert _regime_weight(SimpleNamespace(signal_type="pattern_rsi_divergence", confidence=0.8), "sideways_range") == 1.2
    assert _regime_weight(SimpleNamespace(signal_type="pattern_bull_flag", confidence=0.8), "sideways_range") == 0.85
    assert _regime_weight(SimpleNamespace(signal_type="pattern_custom", confidence=0.8), "sideways_range") == 1.0
    assert _regime_weight(SimpleNamespace(signal_type="pattern_rsi_divergence", confidence=0.8), "high_volatility") == 0.9
    assert _regime_weight(SimpleNamespace(signal_type="pattern_custom", confidence=0.8), "high_volatility") == 1.0
    assert _regime_weight(SimpleNamespace(signal_type="pattern_bollinger_squeeze", confidence=0.8), "low_volatility") == 0.9
    assert _regime_weight(SimpleNamespace(signal_type="pattern_bull_flag", confidence=0.8), "low_volatility") == 1.05
    assert _regime_weight(SimpleNamespace(signal_type="pattern_custom", confidence=0.8), "low_volatility") == 1.0

    monkeypatch.setattr("src.apps.signals.fusion.cross_market_alignment_weight", lambda *args, **kwargs: 1.0)
    neutral_fused = _fuse_signals(
        db_session,
        signals=[
            Signal(
                coin_id=1,
                timeframe=15,
                signal_type="pattern_bull_flag",
                confidence=0.8,
                priority_score=1.0,
                context_score=1.0,
                regime_alignment=1.0,
                candle_timestamp=DEFAULT_START,
            ),
            Signal(
                coin_id=1,
                timeframe=15,
                signal_type="pattern_custom",
                confidence=0.5,
                priority_score=1.0,
                context_score=1.0,
                regime_alignment=1.0,
                candle_timestamp=DEFAULT_START + timedelta(minutes=15),
            ),
        ],
        regime="bull_trend",
    )
    assert neutral_fused is not None
    assert neutral_fused.signal_count == 2
    assert neutral_fused.bullish_score > 0

    coin = create_test_coin(db_session, symbol="AVAXUSD_EVT", name="Avalanche Event Test")
    timestamp = DEFAULT_START + timedelta(hours=2)
    upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=15)
    replace_pattern_statistics(
        db_session,
        timeframe=15,
        rows=[("bull_flag", "all", 0.72, 60)],
    )
    db_session.add(
        Signal(
            coin_id=int(coin.id),
            timeframe=15,
            signal_type="pattern_bull_flag",
            confidence=0.82,
            priority_score=1.0,
            context_score=1.0,
            regime_alignment=1.0,
            candle_timestamp=timestamp,
        )
    )
    db_session.commit()

    published: list[str] = []
    monkeypatch.setattr("src.apps.signals.fusion.publish_event", lambda event_type, payload: published.append(event_type))
    monkeypatch.setattr("src.apps.signals.fusion.enrich_signal_context", lambda *args, **kwargs: {"status": "ok"})
    result = evaluate_market_decision(db_session, coin_id=int(coin.id), timeframe=15, emit_event=True)
    assert result["status"] == "ok"
    assert published[-1] == "decision_generated"
