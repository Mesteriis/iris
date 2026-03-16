# ruff: noqa: RUF001


from datetime import UTC, datetime
from types import SimpleNamespace

from src.apps.notifications.api.presenters import notification_read


def test_notification_presenter_localizes_descriptor_backed_row() -> None:
    item = SimpleNamespace(
        id=1,
        coin_id=11,
        symbol="BTCUSDT",
        sector="store_of_value",
        timeframe=15,
        severity="info",
        urgency="medium",
        content_kind="descriptor_bundle",
        content_json={
            "version": 1,
            "kind": "descriptor_bundle",
            "title": {
                "key": "notification.signal.created.title",
                "params": {"symbol": "BTCUSDT"},
            },
            "message": {
                "key": "notification.signal.created.message",
                "params": {"symbol": "BTCUSDT", "signal_type": "breakout", "timeframe": 15},
            },
        },
        refs_json={"source_event_id": "173-0"},
        context_json={},
        provider="local_test",
        model="llama-test",
        prompt_name="notification.signal_created",
        prompt_version=1,
        source_event_type="signal_created",
        source_event_id="173-0",
        source_stream_id=None,
        causation_id=None,
        correlation_id=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    payload = notification_read(item, locale="ru")

    assert payload.title == "BTCUSDT: новый сигнал"
    assert payload.title_key == "notification.signal.created.title"
    assert payload.title_params == {"symbol": "BTCUSDT"}
    assert payload.message == (
        "IRIS зафиксировал сигнал breakout по BTCUSDT на таймфрейме 15м. "
        "Проверь канонический сигнал перед действием."
    )
    assert payload.message_key == "notification.signal.created.message"
    assert payload.message_params == {"symbol": "BTCUSDT", "signal_type": "breakout", "timeframe": 15}
    assert payload.content_kind == "descriptor_bundle"
    assert payload.rendered_locale == "ru"


def test_notification_presenter_reads_generated_text_content_payload() -> None:
    item = SimpleNamespace(
        id=2,
        coin_id=22,
        symbol="ETHUSDT",
        sector="layer1",
        timeframe=60,
        severity="warning",
        urgency="high",
        content_kind="generated_text",
        content_json={
            "version": 1,
            "kind": "generated_text",
            "rendered_locale": "en",
            "title": "ETHUSDT: anomaly detected",
            "message": "IRIS flagged a volatility anomaly for ETHUSDT.",
        },
        refs_json={"source_event_id": "174-0"},
        context_json={},
        provider="local_test",
        model="llama-test",
        prompt_name="notification.anomaly_detected",
        prompt_version=1,
        source_event_type="anomaly_detected",
        source_event_id="174-0",
        source_stream_id=None,
        causation_id=None,
        correlation_id=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    payload = notification_read(item, locale="ru")

    assert payload.title == "ETHUSDT: anomaly detected"
    assert payload.message == "IRIS flagged a volatility anomaly for ETHUSDT."
    assert payload.content_kind == "generated_text"
    assert payload.rendered_locale == "en"
    assert payload.title_key is None
    assert payload.message_key is None
