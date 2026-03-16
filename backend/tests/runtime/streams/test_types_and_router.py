from datetime import UTC, datetime, timezone

import pytest
from iris.runtime.streams import router
from iris.runtime.streams.types import (
    ANOMALY_SECTOR_WORKER_GROUP,
    ANOMALY_WORKER_GROUP,
    FUSION_WORKER_GROUP,
    HYPOTHESIS_WORKER_GROUP,
    INDICATOR_WORKER_GROUP,
    NEWS_CORRELATION_WORKER_GROUP,
    NEWS_NORMALIZATION_WORKER_GROUP,
    IrisEvent,
    build_event_fields,
    deserialize_payload,
    parse_stream_message,
    serialize_payload,
)


def test_stream_payload_serialization_and_parsing_round_trip() -> None:
    timestamp = datetime(2026, 3, 12, 12, 30, tzinfo=UTC)
    payload = {
        "coin_id": 11,
        "timeframe": 60,
        "timestamp": timestamp,
        "source": "polling",
        "nested": {"strength": 0.8},
    }

    assert deserialize_payload(None) == {}
    assert deserialize_payload("[]") == {}
    assert deserialize_payload(serialize_payload({"kind": "ok"})) == {"kind": "ok"}

    fields = build_event_fields("candle_closed", payload)
    event = parse_stream_message("1710000000-1", fields)

    assert fields["coin_id"] == "11"
    assert fields["timeframe"] == "60"
    assert event == IrisEvent(
        stream_id="1710000000-1",
        event_type="candle_closed",
        coin_id=11,
        timeframe=60,
        timestamp=timestamp,
        payload={"source": "polling", "nested": {"strength": 0.8}},
    )
    assert event.idempotency_key.startswith("candle_closed:11:60:")


def test_subscribed_event_types_and_invalid_worker_group() -> None:
    assert router.subscribed_event_types(INDICATOR_WORKER_GROUP) == {"candle_closed"}
    assert router.subscribed_event_types(ANOMALY_WORKER_GROUP) == {"candle_closed"}
    assert router.subscribed_event_types(ANOMALY_SECTOR_WORKER_GROUP) == {"anomaly_detected"}
    assert "news_symbol_correlation_updated" in router.subscribed_event_types(FUSION_WORKER_GROUP)
    assert router.subscribed_event_types(NEWS_NORMALIZATION_WORKER_GROUP) == {"news_item_ingested"}
    assert router.subscribed_event_types(NEWS_CORRELATION_WORKER_GROUP) == {"news_item_normalized"}
    assert "signal_created" in router.subscribed_event_types(HYPOTHESIS_WORKER_GROUP)
    assert "portfolio_balance_updated" in router.subscribed_event_types(HYPOTHESIS_WORKER_GROUP)

    with pytest.raises(ValueError, match="Unsupported event worker group"):
        router.subscribed_event_types("unsupported")
