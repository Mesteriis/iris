# ruff: noqa: RUF001


from datetime import UTC, datetime
from types import SimpleNamespace

from src.apps.explanations.api.presenters import explanation_read
from src.apps.explanations.contracts import ExplainKind


def test_explanation_presenter_localizes_descriptor_backed_row() -> None:
    now = datetime.now(UTC)
    item = SimpleNamespace(
        id=1,
        explain_kind=ExplainKind.SIGNAL,
        subject_id=99,
        coin_id=11,
        symbol="BTCUSDT",
        timeframe=60,
        content_kind="descriptor_bundle",
        content_json={
            "version": 1,
            "kind": "descriptor_bundle",
            "title": {
                "key": "brief.explanation.signal.title",
                "params": {
                    "symbol": "BTCUSDT",
                    "timeframe": 60,
                    "signal_type": "breakout",
                    "confidence": 0.82,
                    "priority_score": 0.91,
                    "context_score": 0.74,
                    "regime_alignment": 0.63,
                    "market_regime": "bullish",
                    "cycle_phase": "expansion",
                    "cluster_membership": "momentum, breakout",
                },
            },
            "explanation": {
                "key": "brief.explanation.signal.body",
                "params": {
                    "symbol": "BTCUSDT",
                    "timeframe": 60,
                    "signal_type": "breakout",
                    "confidence": 0.82,
                    "priority_score": 0.91,
                    "context_score": 0.74,
                    "regime_alignment": 0.63,
                    "market_regime": "bullish",
                    "cycle_phase": "expansion",
                    "cluster_membership": "momentum, breakout",
                },
            },
            "bullets": [
                {
                    "key": "brief.explanation.signal.bullet.priority",
                    "params": {"priority_score": 0.91},
                },
                {
                    "key": "brief.explanation.signal.bullet.context",
                    "params": {"context_score": 0.74, "regime_alignment": 0.63},
                },
            ],
        },
        refs_json={"subject_id": 99},
        context_json={},
        provider="local_test",
        model="llama-test",
        prompt_name="explain.signal",
        prompt_version=1,
        subject_updated_at=now,
        created_at=now,
        updated_at=now,
    )

    payload = explanation_read(item, locale="ru")

    assert payload.title == "BTCUSDT: объяснение сигнала"
    assert payload.title_key == "brief.explanation.signal.title"
    assert payload.explanation == (
        "Сигнал breakout на таймфрейме 60м появился с уверенностью 0.82. "
        "Это каноническое наблюдение, а не подтвержденное действие."
    )
    assert payload.explanation_key == "brief.explanation.signal.body"
    assert payload.bullets == [
        "Приоритет сигнала: 0.91.",
        "Контекстный скор: 0.74, выравнивание с режимом: 0.63.",
    ]
    assert payload.bullet_keys == [
        "brief.explanation.signal.bullet.priority",
        "brief.explanation.signal.bullet.context",
    ]
    assert payload.bullet_params == [
        {"priority_score": 0.91},
        {"context_score": 0.74, "regime_alignment": 0.63},
    ]
    assert payload.content_kind == "descriptor_bundle"
    assert payload.rendered_locale == "ru"


def test_explanation_presenter_reads_generated_text_content_payload() -> None:
    now = datetime.now(UTC)
    item = SimpleNamespace(
        id=2,
        explain_kind=ExplainKind.DECISION,
        subject_id=42,
        coin_id=11,
        symbol="ETHUSDT",
        timeframe=15,
        content_kind="generated_text",
        content_json={
            "version": 1,
            "kind": "generated_text",
            "rendered_locale": "en",
            "title": "ETHUSDT: decision explanation",
            "explanation": "The BUY decision for 15m was stored with confidence 0.67 and score 0.72.",
            "bullets": [
                "Machine reason: no reason provided.",
                "Confidence and score snapshot: 0.67 / 0.72.",
            ],
        },
        refs_json={"subject_id": 42},
        context_json={},
        provider="local_test",
        model="llama-test",
        prompt_name="explain.decision",
        prompt_version=1,
        subject_updated_at=now,
        created_at=now,
        updated_at=now,
    )

    payload = explanation_read(item, locale="ru")

    assert payload.title == "ETHUSDT: decision explanation"
    assert payload.explanation == "The BUY decision for 15m was stored with confidence 0.67 and score 0.72."
    assert payload.bullets == [
        "Machine reason: no reason provided.",
        "Confidence and score snapshot: 0.67 / 0.72.",
    ]
    assert payload.content_kind == "generated_text"
    assert payload.rendered_locale == "en"
    assert payload.title_key is None
    assert payload.explanation_key is None
