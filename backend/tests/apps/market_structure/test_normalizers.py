from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.apps.market_structure.exceptions import InvalidMarketStructureWebhookPayloadError
from app.apps.market_structure.normalizers import create_market_structure_webhook_normalizer


def test_liqscope_webhook_normalizer_maps_native_payload() -> None:
    normalizer = create_market_structure_webhook_normalizer(provider="liqscope", venue="liqscope")

    result = normalizer.normalize_payload(
        {
            "timestamp": datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc).isoformat(),
            "price": 3150.0,
            "open_interest": 21000.0,
            "liquidations": {"long": 3300.0, "short": 120.0},
        }
    )

    assert len(result.snapshots) == 1
    assert result.snapshots[0].last_price == pytest.approx(3150.0)
    assert result.snapshots[0].open_interest == pytest.approx(21000.0)
    assert result.snapshots[0].liquidations_long == pytest.approx(3300.0)


def test_liquidation_webhook_normalizer_maps_nested_metrics() -> None:
    normalizer = create_market_structure_webhook_normalizer(
        provider="liquidation_webhook",
        venue="liquidations_api",
    )

    result = normalizer.normalize_payload(
        {
            "event_time": datetime(2026, 3, 12, 12, 1, tzinfo=timezone.utc).isoformat(),
            "metrics": {
                "last_price": 3151.0,
                "open_interest": 20800.0,
                "liquidations_long": 4100.0,
                "liquidations_short": 135.0,
            },
        }
    )

    assert result.snapshots[0].venue == "liquidations_api"
    assert result.snapshots[0].liquidations_short == pytest.approx(135.0)


def test_derivatives_webhook_normalizer_maps_derivatives_fields() -> None:
    normalizer = create_market_structure_webhook_normalizer(
        provider="derivatives_webhook",
        venue="derivatives_webhook",
    )

    result = normalizer.normalize_payload(
        {
            "timestamp": datetime(2026, 3, 12, 12, 2, tzinfo=timezone.utc).isoformat(),
            "mark_price": 3152.0,
            "index_price": 3148.0,
            "funding_rate": 0.0008,
            "open_interest": 20500.0,
            "basis": 0.0012,
            "volume": 1205000.0,
            "liquidations": {"long": 900.0, "short": 40.0},
        }
    )

    assert result.snapshots[0].mark_price == pytest.approx(3152.0)
    assert result.snapshots[0].basis == pytest.approx(0.0012)
    assert result.snapshots[0].volume == pytest.approx(1205000.0)


def test_coinglass_webhook_normalizer_maps_collector_payload() -> None:
    normalizer = create_market_structure_webhook_normalizer(
        provider="coinglass",
        venue="coinglass",
    )

    result = normalizer.normalize_payload(
        {
            "data": [
                {
                    "time": datetime(2026, 3, 12, 12, 4, tzinfo=timezone.utc).isoformat(),
                    "price": 3154.0,
                    "oi": 20700.0,
                    "funding": 0.0007,
                    "volume24h": 1100000.0,
                    "longLiquidationUsd": 5100.0,
                    "shortLiquidationUsd": 180.0,
                }
            ]
        }
    )

    assert result.snapshots[0].venue == "coinglass"
    assert result.snapshots[0].liquidations_long == pytest.approx(5100.0)
    assert result.snapshots[0].volume == pytest.approx(1100000.0)


def test_hyblock_webhook_normalizer_maps_event_payload() -> None:
    normalizer = create_market_structure_webhook_normalizer(
        provider="hyblock",
        venue="hyblock",
    )

    result = normalizer.normalize_payload(
        {
            "events": [
                {
                    "ts": datetime(2026, 3, 12, 12, 5, tzinfo=timezone.utc).isoformat(),
                    "market": {
                        "last_price": 3155.0,
                        "mark_price": 3155.4,
                        "open_interest": 20650.0,
                        "funding_rate": 0.00072,
                    },
                    "liquidations": {"longs": 4700.0, "shorts": 220.0},
                }
            ]
        }
    )

    assert result.snapshots[0].mark_price == pytest.approx(3155.4)
    assert result.snapshots[0].liquidations_short == pytest.approx(220.0)


def test_coinalyze_webhook_normalizer_maps_derivatives_snapshot() -> None:
    normalizer = create_market_structure_webhook_normalizer(
        provider="coinalyze",
        venue="coinalyze",
    )

    result = normalizer.normalize_payload(
        {
            "updateTime": datetime(2026, 3, 12, 12, 6, tzinfo=timezone.utc).isoformat(),
            "price": {"last": 3156.0, "mark": 3156.2, "index": 3152.1},
            "openInterest": 20620.0,
            "fundingRate": 0.00074,
            "basisPct": 0.0013,
            "liquidation": {"long": 1600.0, "short": 80.0},
            "volume": 990000.0,
        }
    )

    assert result.snapshots[0].last_price == pytest.approx(3156.0)
    assert result.snapshots[0].basis == pytest.approx(0.0013)
    assert result.snapshots[0].liquidations_short == pytest.approx(80.0)


def test_webhook_normalizer_rejects_missing_timestamp() -> None:
    normalizer = create_market_structure_webhook_normalizer(provider="liqscope", venue="liqscope")

    with pytest.raises(InvalidMarketStructureWebhookPayloadError):
        normalizer.normalize_payload({"price": 3150.0})
