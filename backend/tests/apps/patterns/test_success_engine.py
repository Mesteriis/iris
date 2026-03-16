from datetime import datetime, timezone

from redis import Redis

from src.apps.patterns.domain.base import PatternDetection
from src.apps.patterns.domain.success import (
    GLOBAL_MARKET_REGIME,
    PatternSuccessSnapshot,
    apply_pattern_success_validation,
    build_pattern_success_cache,
)
from src.runtime.streams.publisher import flush_publisher


def _snapshot(
    *,
    slug: str,
    timeframe: int,
    market_regime: str,
    success_rate: float,
    total_signals: int,
    enabled: bool = True,
) -> PatternSuccessSnapshot:
    successful_signals = int(round(success_rate * total_signals))
    return PatternSuccessSnapshot(
        pattern_slug=slug,
        timeframe=timeframe,
        market_regime=market_regime,
        total_signals=total_signals,
        successful_signals=successful_signals,
        success_rate=success_rate,
        avg_return=0.03 if success_rate >= 0.5 else -0.02,
        avg_drawdown=-0.02,
        temperature=0.8 if success_rate >= 0.5 else -0.6,
        enabled=enabled,
    )


def test_pattern_success_engine_prefers_regime_specific_statistics() -> None:
    cache = build_pattern_success_cache(
        [
            _snapshot(
                slug="bull_flag",
                timeframe=15,
                market_regime=GLOBAL_MARKET_REGIME,
                success_rate=0.32,
                total_signals=40,
                enabled=False,
            ),
            _snapshot(
                slug="bull_flag",
                timeframe=15,
                market_regime="bull_trend",
                success_rate=0.82,
                total_signals=40,
                enabled=True,
            ),
        ]
    )
    detection = PatternDetection(
        slug="bull_flag",
        signal_type="pattern_bull_flag",
        confidence=0.72,
        candle_timestamp=datetime(2026, 3, 11, 14, 0, tzinfo=timezone.utc),
        category="continuation",
        attributes={"regime": "bull_trend"},
    )

    adjusted = apply_pattern_success_validation(
        detection=detection,
        timeframe=15,
        market_regime="bull_trend",
        coin_id=1,
        emit_events=False,
        snapshot_cache=cache,
    )
    assert adjusted is not None
    assert adjusted.confidence > detection.confidence
    assert adjusted.attributes["pattern_success_regime"] == "bull_trend"


def test_pattern_success_engine_degrades_and_suppresses(settings) -> None:
    cache = build_pattern_success_cache(
        [
            _snapshot(
                slug="head_shoulders",
                timeframe=60,
                market_regime="bull_trend",
                success_rate=0.50,
                total_signals=20,
                enabled=True,
            ),
            _snapshot(
                slug="head_shoulders",
                timeframe=60,
                market_regime="bear_trend",
                success_rate=0.30,
                total_signals=25,
                enabled=True,
            ),
        ]
    )

    degraded = apply_pattern_success_validation(
        detection=PatternDetection(
            slug="head_shoulders",
            signal_type="pattern_head_shoulders",
            confidence=0.8,
            candle_timestamp=datetime(2026, 3, 11, 15, 0, tzinfo=timezone.utc),
            category="structural",
            attributes={"regime": "bull_trend"},
        ),
        timeframe=60,
        market_regime="bull_trend",
        coin_id=1,
        emit_events=True,
        snapshot_cache=cache,
    )
    assert degraded is not None
    assert degraded.confidence < 0.8

    suppressed = apply_pattern_success_validation(
        detection=PatternDetection(
            slug="head_shoulders",
            signal_type="pattern_head_shoulders",
            confidence=0.75,
            candle_timestamp=datetime(2026, 3, 11, 16, 0, tzinfo=timezone.utc),
            category="structural",
            attributes={"regime": "bear_trend"},
        ),
        timeframe=60,
        market_regime="bear_trend",
        coin_id=1,
        emit_events=True,
        snapshot_cache=cache,
    )
    assert suppressed is None
    assert flush_publisher(timeout=5.0)

    client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        event_types = [fields["event_type"] for _, fields in client.xrange(settings.event_stream_name, "-", "+")]
        assert "pattern_degraded" in event_types
        assert "pattern_disabled" in event_types
    finally:
        client.close()
