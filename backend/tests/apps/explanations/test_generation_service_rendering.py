# ruff: noqa: RUF001

from __future__ import annotations

from src.apps.explanations.contracts import ExplainKind
from src.apps.explanations.services.generation_service import render_deterministic_explanation


def test_render_deterministic_signal_explanation_uses_shared_catalog_for_ru() -> None:
    payload = render_deterministic_explanation(
        {
            "explain_kind": ExplainKind.SIGNAL.value,
            "symbol": "BTCUSDT",
            "timeframe": 60,
            "signal_type": "long_entry",
            "confidence": 0.82,
            "priority_score": 0.91,
            "context_score": 0.74,
            "regime_alignment": 0.63,
            "market_regime": "bullish",
            "cycle_phase": "expansion",
            "cluster_membership": ["momentum", "breakout"],
        },
        effective_language="ru",
    )

    assert payload["title"] == "BTCUSDT: объяснение сигнала"
    assert payload["explanation"] == (
        "Сигнал long entry на таймфрейме 60м появился с уверенностью 0.82. "
        "Это каноническое наблюдение, а не подтвержденное действие."
    )
    assert payload["bullets"] == [
        "Приоритет сигнала: 0.91.",
        "Контекстный скор: 0.74, выравнивание с режимом: 0.63.",
        "Рыночный режим в snapshot: bullish.",
        "Фаза цикла: expansion.",
        "Кластерные сигналы: momentum, breakout.",
    ]


def test_render_deterministic_decision_explanation_falls_back_to_en() -> None:
    payload = render_deterministic_explanation(
        {
            "explain_kind": ExplainKind.DECISION.value,
            "symbol": "ETHUSDT",
            "timeframe": 15,
            "decision": "buy",
            "confidence": 0.67,
            "score": 0.72,
            "sector": "layer1",
        },
        effective_language="es",
    )

    assert payload["title"] == "ETHUSDT: decision explanation"
    assert payload["explanation"] == (
        "The BUY decision for 15m was stored with confidence 0.67 and score 0.72. "
        "It is a canonical decision artifact, not personalized advice."
    )
    assert payload["bullets"] == [
        "Machine reason: no reason provided.",
        "Confidence and score snapshot: 0.67 / 0.72.",
        "Sector context: layer1.",
    ]
