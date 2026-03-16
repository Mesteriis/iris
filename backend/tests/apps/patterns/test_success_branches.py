from datetime import UTC, datetime, timezone

from src.apps.patterns.domain.success import (
    GLOBAL_MARKET_REGIME,
    PatternSuccessSnapshot,
    apply_pattern_success_validation,
    assess_pattern_success,
    build_pattern_success_cache,
    load_pattern_success_snapshot,
    normalize_market_regime,
    publish_pattern_state_event,
)

from tests.factories.patterns import PatternDetectionFactory


def _snapshot(
    *,
    slug: str,
    timeframe: int,
    market_regime: str,
    success_rate: float,
    total_signals: int,
    enabled: bool = True,
) -> PatternSuccessSnapshot:
    successful_signals = round(success_rate * total_signals)
    return PatternSuccessSnapshot(
        pattern_slug=slug,
        timeframe=timeframe,
        market_regime=market_regime,
        total_signals=total_signals,
        successful_signals=successful_signals,
        success_rate=success_rate,
        avg_return=0.03,
        avg_drawdown=-0.02,
        temperature=0.8 if success_rate >= 0.5 else -0.4,
        enabled=enabled,
    )


def test_pattern_success_cache_and_assessment_branches() -> None:
    cache = build_pattern_success_cache(
        [
            _snapshot(
                slug="breakout_retest",
                timeframe=15,
                market_regime=GLOBAL_MARKET_REGIME,
                success_rate=0.8,
                total_signals=25,
            ),
            _snapshot(
                slug="high_tight_flag",
                timeframe=15,
                market_regime=GLOBAL_MARKET_REGIME,
                success_rate=0.0,
                total_signals=0,
            ),
            _snapshot(
                slug="head_shoulders",
                timeframe=60,
                market_regime="bull_trend",
                success_rate=0.6,
                total_signals=25,
                enabled=False,
            ),
        ]
    )

    assert normalize_market_regime(None) == GLOBAL_MARKET_REGIME
    assert normalize_market_regime("  ") == GLOBAL_MARKET_REGIME
    assert build_pattern_success_cache([]) == {}

    cached = load_pattern_success_snapshot(
        slug="breakout_retest",
        timeframe=15,
        market_regime="bull_trend",
        snapshot_cache=cache,
    )
    assert cached is not None
    assert cached.market_regime == GLOBAL_MARKET_REGIME

    assert assess_pattern_success(slug="missing", timeframe=15, snapshot_cache=cache).action == "neutral"
    assert assess_pattern_success(slug="high_tight_flag", timeframe=15, snapshot_cache=cache).action == "neutral"
    disabled = assess_pattern_success(
        slug="head_shoulders",
        timeframe=60,
        market_regime="bull_trend",
        snapshot_cache=cache,
    )
    assert disabled.action == "disabled"
    assert disabled.suppress is True
    boosted = assess_pattern_success(
        slug="breakout_retest",
        timeframe=15,
        market_regime="bull_trend",
        snapshot_cache=cache,
    )
    assert boosted.action == "boosted"
    assert boosted.factor > 1.0


def test_pattern_success_publish_and_low_confidence_degrade(monkeypatch) -> None:
    cache = build_pattern_success_cache(
        [
            _snapshot(
                slug="bull_flag",
                timeframe=15,
                market_regime="bull_trend",
                success_rate=0.46,
                total_signals=20,
            )
        ]
    )

    published: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr("src.runtime.streams.publisher.publish_event", lambda event_type, payload: published.append((event_type, payload)))
    publish_pattern_state_event("pattern_tested", pattern_slug="bull_flag", timeframe=15)
    assert published[-1][1]["pattern_slug"] == "bull_flag"
    assert "confidence" not in published[-1][1]

    detection = PatternDetectionFactory.build(
        slug="bull_flag",
        signal_type="pattern_bull_flag",
        confidence=0.36,
        candle_timestamp=datetime(2026, 3, 12, 12, 0, tzinfo=UTC),
        category="continuation",
    )
    adjusted = apply_pattern_success_validation(
        detection=detection,
        timeframe=15,
        market_regime="bull_trend",
        coin_id=1,
        emit_events=True,
        snapshot_cache=cache,
    )
    assert adjusted is None
    assert published[-1][0] == "pattern_degraded"


def test_pattern_success_exact_cache_hit_and_neutral_action() -> None:
    cache = build_pattern_success_cache(
        [
            _snapshot(
                slug="bull_flag",
                timeframe=15,
                market_regime="bull_trend",
                success_rate=0.6,
                total_signals=15,
            )
        ]
    )
    snapshot = load_pattern_success_snapshot(
        slug="bull_flag",
        timeframe=15,
        market_regime="bull_trend",
        snapshot_cache=cache,
    )
    assert snapshot is not None
    assert snapshot.market_regime == "bull_trend"

    decision = assess_pattern_success(
        slug="bull_flag",
        timeframe=15,
        market_regime="bull_trend",
        snapshot_cache=cache,
    )
    assert decision.action == "neutral"
    assert decision.factor == 1.0


def test_pattern_success_suppressed_and_missing_snapshot_without_events() -> None:
    cache = build_pattern_success_cache(
        [
            _snapshot(
                slug="head_shoulders",
                timeframe=15,
                market_regime="bear_trend",
                success_rate=0.2,
                total_signals=25,
            )
        ]
    )

    suppressed = apply_pattern_success_validation(
        detection=PatternDetectionFactory.build(
            slug="head_shoulders",
            signal_type="pattern_head_shoulders",
            confidence=0.75,
            candle_timestamp=datetime(2026, 3, 12, 13, 0, tzinfo=UTC),
            category="structural",
        ),
        timeframe=15,
        market_regime="bear_trend",
        coin_id=1,
        emit_events=False,
        snapshot_cache=cache,
    )
    assert suppressed is None

    missing_snapshot = apply_pattern_success_validation(
        detection=PatternDetectionFactory.build(
            slug="unknown_pattern",
            signal_type="pattern_unknown_pattern",
            confidence=0.64,
            candle_timestamp=datetime(2026, 3, 12, 14, 0, tzinfo=UTC),
            category="structural",
            attributes={"source": "test"},
        ),
        timeframe=15,
        market_regime="bull_trend",
        coin_id=1,
        emit_events=True,
        snapshot_cache=cache,
    )
    assert missing_snapshot is not None
    assert missing_snapshot.attributes["pattern_success_action"] == "neutral"
    assert "pattern_success_rate" not in missing_snapshot.attributes


def test_pattern_success_low_confidence_degrade_without_events() -> None:
    cache = build_pattern_success_cache(
        [
            _snapshot(
                slug="bull_flag",
                timeframe=15,
                market_regime="bull_trend",
                success_rate=0.46,
                total_signals=20,
            )
        ]
    )

    adjusted = apply_pattern_success_validation(
        detection=PatternDetectionFactory.build(
            slug="bull_flag",
            signal_type="pattern_bull_flag",
            confidence=0.36,
            candle_timestamp=datetime(2026, 3, 12, 15, 0, tzinfo=UTC),
            category="continuation",
        ),
        timeframe=15,
        market_regime="bull_trend",
        coin_id=1,
        emit_events=False,
        snapshot_cache=cache,
    )
    assert adjusted is None
