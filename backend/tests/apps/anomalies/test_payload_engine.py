from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from src.apps.anomalies.contracts import AnomalyDetectionContext, DetectorFinding
from src.apps.anomalies.engines import build_anomaly_payload, build_enriched_anomaly_projection
from src.apps.market_data.candles import CandlePoint


@pytest.fixture(autouse=True)
def isolated_event_stream() -> None:
    yield


def _context() -> AnomalyDetectionContext:
    timestamp = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)
    return AnomalyDetectionContext(
        coin_id=7,
        symbol="ETHUSD_EVT",
        timeframe=15,
        timestamp=timestamp,
        candles=[
            CandlePoint(
                timestamp=timestamp - timedelta(minutes=15),
                open=100.0,
                high=101.0,
                low=99.5,
                close=100.5,
                volume=1000.0,
            ),
            CandlePoint(
                timestamp=timestamp,
                open=100.5,
                high=114.0,
                low=100.0,
                close=113.0,
                volume=7000.0,
            ),
        ],
        market_regime="bull_trend",
        sector="smart_contracts",
        portfolio_relevant=True,
    )


def test_payload_engine_builds_detection_payload() -> None:
    payload = build_anomaly_payload(
        _context(),
        DetectorFinding(
            anomaly_type="price_spike",
            summary="Price spike detected",
            component_scores={"price_displacement": 0.92},
            metrics={"price_change": 0.14},
            confidence=0.87,
            explainability={"what_happened": "ETH moved sharply", "unusualness": "6 sigma move"},
            affected_symbols=["ETHUSD_EVT"],
        ),
        source_pipeline="fast_path",
        extra_payload={"source": "unit_test"},
    )

    assert payload["source_pipeline"] == "fast_path"
    assert payload["context"]["portfolio_relevant"] is True
    assert payload["source"] == "unit_test"


def test_payload_engine_builds_enrichment_projection() -> None:
    projection = build_enriched_anomaly_projection(
        payload_json={"context": {"scope": "asset"}, "explainability": {"what_happened": "test"}},
        portfolio_relevant=True,
        market_wide=False,
        enrichment_source="enrichment",
    )

    assert projection.portfolio_relevant is True
    assert projection.market_wide is False
    assert projection.payload_json["context"]["portfolio_relevant"] is True
    assert projection.payload_json["explainability"]["enriched_by"] == "enrichment"
