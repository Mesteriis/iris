from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from src.apps.patterns.runtime_results import (
    PatternIncrementalDetectionStepResult,
    PatternIncrementalSignalsResult,
    PatternRegimeRefreshResult,
    PatternSignalDerivationResult,
)
from src.runtime.control_plane.worker import build_delivery_stream_name
from src.runtime.streams import workers
from src.runtime.streams.types import (
    ANALYSIS_SCHEDULER_WORKER_GROUP,
    ANOMALY_SECTOR_WORKER_GROUP,
    ANOMALY_WORKER_GROUP,
    CROSS_MARKET_WORKER_GROUP,
    DECISION_WORKER_GROUP,
    FUSION_WORKER_GROUP,
    HYPOTHESIS_WORKER_GROUP,
    INDICATOR_WORKER_GROUP,
    NEWS_CORRELATION_WORKER_GROUP,
    NEWS_NORMALIZATION_WORKER_GROUP,
    PATTERN_WORKER_GROUP,
    PORTFOLIO_WORKER_GROUP,
    REGIME_WORKER_GROUP,
    IrisEvent,
)


@pytest.fixture(autouse=True)
def isolated_event_stream() -> None:
    yield


def _event(
    *,
    event_type: str = "candle_closed",
    coin_id: int = 7,
    timeframe: int = 15,
    payload: dict[str, object] | None = None,
) -> IrisEvent:
    return IrisEvent(
        stream_id="1-0",
        event_type=event_type,
        coin_id=coin_id,
        timeframe=timeframe,
        timestamp=datetime(2026, 3, 12, 12, 0, tzinfo=UTC),
        payload=payload or {},
    )


@pytest.mark.asyncio
async def test_pattern_runtime_helper_functions(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    published: list[tuple[str, dict[str, object]]] = []

    class FakeUow:
        session = "pattern-db"

        async def __aenter__(self):
            calls.append(("enter", self.session))
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            calls.append(("exit", self.session))
            return False

        async def commit(self):
            calls.append(("commit", self.session))

    class FakePatternRealtimeService:
        def __init__(self, uow):
            calls.append(("service_session", uow.session))

        async def detect_incremental_signals(self, **kwargs):
            calls.append(("detect", (kwargs["coin_id"], kwargs["timeframe"])))
            return PatternIncrementalSignalsResult(
                status="ok",
                coin_id=kwargs["coin_id"],
                timeframe=kwargs["timeframe"],
                new_signal_types=("pattern_breakout",),
                requires_commit=True,
                detection=PatternIncrementalDetectionStepResult(
                    status="ok",
                    coin_id=kwargs["coin_id"],
                    timeframe=kwargs["timeframe"],
                    detections=1,
                    created=1,
                ),
                clusters=PatternSignalDerivationResult(status="ok", created=0),
                hierarchy=PatternSignalDerivationResult(status="ok", created=0),
            )

        async def refresh_regime_state(self, **kwargs):
            calls.append(("regime", (kwargs["coin_id"], kwargs["timeframe"])))
            return PatternRegimeRefreshResult(
                status="ok",
                requires_commit=True,
                regime=kwargs["regime"],
                regime_confidence=kwargs["regime_confidence"],
                next_cycle="distribution",
                previous_cycle="accumulation",
            )

    monkeypatch.setattr(workers, "AsyncUnitOfWork", FakeUow)
    monkeypatch.setattr(
        workers,
        "_pattern_realtime_service_factory",
        lambda uow: FakePatternRealtimeService(uow),
    )
    monkeypatch.setattr(workers, "publish_event", lambda event_type, payload: published.append((event_type, payload)))

    result = await workers._run_pattern_detection(_event(event_type="analysis_requested"))
    regime = await workers._run_regime_refresh(
        _event(event_type="indicator_updated", payload={"market_regime": "bull_trend", "regime_confidence": 0.77})
    )
    workers._emit_signal_created_events(
        coin_id=7,
        timeframe=15,
        timestamp=_event().timestamp,
        signal_types=["pattern_a", "pattern_b"],
    )

    assert result == ["pattern_breakout"]
    assert regime is not None
    assert regime.next_cycle == "distribution"
    assert ("detect", (7, 15)) in calls
    assert ("regime", (7, 15)) in calls
    assert ("commit", "pattern-db") in calls
    assert published[0][0] == "signal_created"


@pytest.mark.asyncio
async def test_indicator_pattern_decision_fusion_cross_market_and_portfolio_handlers(monkeypatch) -> None:
    published: list[tuple[str, dict[str, object]]] = []
    emitted: list[tuple[int, int, object, list[str]]] = []
    calls: list[tuple[str, object]] = []
    snapshots: list[dict[str, object]] = []

    monkeypatch.setattr(workers, "publish_event", lambda event_type, payload: published.append((event_type, payload)))
    monkeypatch.setattr(
        workers,
        "_emit_signal_created_events",
        lambda *, coin_id, timeframe, timestamp, signal_types: emitted.append(
            (coin_id, timeframe, timestamp, signal_types)
        ),
    )

    async def process_indicator(_event_obj):
        del _event_obj
        return SimpleNamespace(
            status="ok",
            items=(
                SimpleNamespace(
                    coin_id=7,
                    timeframe=15,
                    timestamp=_event().timestamp,
                    feature_source="candles",
                    activity_score=None,
                    activity_bucket="HOT",
                    analysis_priority=None,
                    market_regime=None,
                    regime_confidence=None,
                    price_change_24h=None,
                    price_change_7d=None,
                    volatility=None,
                    classic_signals=("rsi_reversal",),
                ),
            ),
        )

    monkeypatch.setattr(workers, "_process_indicator_event", process_indicator)
    await workers._handle_indicator_event(_event())
    assert published[0][0] == "indicator_updated"
    assert emitted == [(7, 15, _event().timestamp, ["rsi_reversal"])]

    published.clear()
    monkeypatch.setattr(
        workers,
        "_process_indicator_event",
        lambda _event_obj: __import__("asyncio").sleep(0, result=SimpleNamespace(status="skipped", items=())),
    )
    await workers._handle_indicator_event(_event())
    assert published == []

    async def run_pattern(_event_obj):
        return ["pattern_cluster_breakout", "pattern_head_shoulders"]

    monkeypatch.setattr(workers, "_run_pattern_detection", run_pattern)
    await workers._handle_pattern_event(_event(event_type="analysis_requested"))
    assert {event_type for event_type, _ in published} == {"pattern_cluster_detected", "pattern_detected"}

    published.clear()
    monkeypatch.setattr(workers, "_run_pattern_detection", lambda _event_obj: __import__("asyncio").sleep(0, result=[]))
    await workers._handle_pattern_event(_event(event_type="analysis_requested"))
    assert published == []

    monkeypatch.setattr(
        workers,
        "_capture_feature_snapshot_async",
        lambda **kwargs: __import__("asyncio").sleep(0, result=snapshots.append(kwargs)),
    )

    class FakeDecisionUow:
        _index = 0

        def __init__(self) -> None:
            type(self)._index += 1
            self.session = f"decision-db-{type(self)._index}"

        async def __aenter__(self):
            calls.append(("decision_uow_enter", self.session))
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            calls.append(("decision_uow_exit", self.session))
            return False

        async def commit(self):
            calls.append(("decision_history_commit", self.session))

    class FakePatternSignalContextService:
        def __init__(self, uow):
            calls.append(("context_session", uow.session))

        async def enrich(self, **kwargs):
            calls.append(("context_enrich", (kwargs["coin_id"], kwargs["timeframe"])))
            return {
                "status": "ok",
                "decision": {"status": "ok", "decision": "BUY", "score": 0.91},
                "_feature_snapshot": {
                    "coin_id": 7,
                    "timeframe": 15,
                    "timestamp": _event().timestamp,
                    "price_current": 101.0,
                    "rsi_14": 52.0,
                    "macd": 1.5,
                },
            }

    class FakeSignalHistoryService:
        def __init__(self, uow):
            calls.append(("history_session", uow.session))

        async def refresh_recent_history(self, *, coin_id, timeframe):
            calls.append(("history_refresh", (coin_id, timeframe)))
            return {"status": "ok"}

    monkeypatch.setattr(workers, "AsyncUnitOfWork", FakeDecisionUow)
    monkeypatch.setattr(
        workers,
        "_pattern_signal_context_service_factory",
        lambda uow: FakePatternSignalContextService(uow),
    )
    monkeypatch.setattr(workers, "SignalHistoryService", FakeSignalHistoryService)
    await workers._handle_decision_event(_event(event_type="pattern_detected"))
    assert published[-1][0] == "decision_generated"
    assert snapshots[-1]["price_current"] == 101.0
    assert ("context_session", "decision-db-1") in calls
    assert ("context_enrich", (7, 15)) in calls
    assert ("history_session", "decision-db-2") in calls
    assert ("history_refresh", (7, 15)) in calls
    assert ("decision_history_commit", "decision-db-2") in calls

    published.clear()
    calls.clear()
    FakeDecisionUow._index = 0

    class FakePatternSignalContextServiceSkip:
        def __init__(self, uow):
            calls.append(("context_session", uow.session))

        async def enrich(self, **kwargs):
            calls.append(("context_enrich", (kwargs["coin_id"], kwargs["timeframe"])))
            return {
                "status": "ok",
                "decision": {"status": "skip"},
                "_feature_snapshot": {
                    "coin_id": 7,
                    "timeframe": 15,
                    "timestamp": _event().timestamp,
                    "price_current": None,
                    "rsi_14": None,
                    "macd": None,
                },
            }

    monkeypatch.setattr(
        workers,
        "_pattern_signal_context_service_factory",
        lambda uow: FakePatternSignalContextServiceSkip(uow),
    )
    await workers._handle_decision_event(_event(event_type="pattern_detected"))
    assert published == []
    assert ("history_refresh", (7, 15)) in calls

    calls.clear()

    class FakeFusionUow:
        session = "fusion-db"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        async def commit(self):
            calls.append(("fusion_commit", self.session))

    class FakeSignalFusionService:
        def __init__(self, uow):
            calls.append(("fusion_session", uow.session))

        async def evaluate_market_decision(self, **kwargs):
            calls.append(("trigger_timestamp", kwargs["trigger_timestamp"]))
            return ("market", kwargs["trigger_timestamp"])

        async def evaluate_news_fusion_event(self, **kwargs):
            calls.append(("news_reference", kwargs["reference_timestamp"]))
            return ("news", kwargs["reference_timestamp"])

    class FakeFusionDispatcher:
        async def apply(self, result):
            calls.append(("dispatcher", result))

    monkeypatch.setattr(workers, "AsyncUnitOfWork", lambda: FakeFusionUow())
    monkeypatch.setattr(workers, "SignalFusionService", FakeSignalFusionService)
    monkeypatch.setattr(workers, "SignalFusionSideEffectDispatcher", lambda: FakeFusionDispatcher())
    await workers._handle_fusion_event(_event(event_type="market_regime_changed"))
    await workers._handle_fusion_event(_event(event_type="pattern_detected"))
    await workers._handle_fusion_event(_event(event_type="news_symbol_correlation_updated", timeframe=0))
    assert calls == [
        ("fusion_session", "fusion-db"),
        ("trigger_timestamp", None),
        ("fusion_commit", "fusion-db"),
        ("dispatcher", ("market", None)),
        ("fusion_session", "fusion-db"),
        ("trigger_timestamp", _event().timestamp),
        ("fusion_commit", "fusion-db"),
        ("dispatcher", ("market", _event().timestamp)),
        ("fusion_session", "fusion-db"),
        ("news_reference", _event().timestamp),
        ("fusion_commit", "fusion-db"),
        ("dispatcher", ("news", _event().timestamp)),
    ]

    calls.clear()

    class FakeUow:
        session = "async-db"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        async def commit(self):
            calls.append(("cross_market_commit", self.session))

    class FakeCrossMarketService:
        def __init__(self, uow):
            calls.append(("cross_market_session", uow.session))

        async def process_event(self, **kwargs):
            calls.append(("cross_market", kwargs["coin_id"]))
            return {"status": "ok"}

    monkeypatch.setattr(workers, "AsyncUnitOfWork", lambda: FakeUow())
    monkeypatch.setattr(workers, "CrossMarketService", FakeCrossMarketService)
    await workers._handle_cross_market_event(_event(coin_id=-1))
    await workers._handle_cross_market_event(_event(coin_id=9))
    assert calls == [
        ("cross_market_session", "async-db"),
        ("cross_market", 9),
        ("cross_market_commit", "async-db"),
    ]

    calls.clear()

    class FakePortfolioUow:
        session = "portfolio-db"

        async def __aenter__(self):
            calls.append(("portfolio_uow_enter", self.session))
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            calls.append(("portfolio_uow_exit", self.session))
            return False

        async def commit(self):
            calls.append(("portfolio_commit", self.session))

    class FakePortfolioService:
        def __init__(self, uow):
            calls.append(("portfolio_session", uow.session))

        async def evaluate_portfolio_action(self, **kwargs):
            calls.append(("portfolio", kwargs["timeframe"]))
            return "portfolio-result"

    class FakePortfolioDispatcher:
        async def apply_action_result(self, result):
            calls.append(("portfolio_dispatcher", result))

    monkeypatch.setattr(workers, "AsyncUnitOfWork", lambda: FakePortfolioUow())
    monkeypatch.setattr(workers, "PortfolioService", FakePortfolioService)
    monkeypatch.setattr(workers, "PortfolioSideEffectDispatcher", FakePortfolioDispatcher)
    await workers._handle_portfolio_event(_event(event_type="decision_generated", payload={"source": "manual"}))
    await workers._handle_portfolio_event(_event(event_type="market_regime_changed", timeframe=0))
    await workers._handle_portfolio_event(_event(event_type="decision_generated", payload={"source": "signal_fusion"}))
    assert calls == [
        ("portfolio_uow_enter", "portfolio-db"),
        ("portfolio_session", "portfolio-db"),
        ("portfolio", 15),
        ("portfolio_commit", "portfolio-db"),
        ("portfolio_uow_exit", "portfolio-db"),
        ("portfolio_dispatcher", "portfolio-result"),
    ]


@pytest.mark.asyncio
async def test_analysis_scheduler_and_regime_handlers(monkeypatch) -> None:
    published: list[tuple[str, dict[str, object]]] = []
    cached: list[dict[str, object]] = []
    commits: list[str] = []

    class FakeSchedulerUow:
        session = "analysis-db"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        async def commit(self) -> None:
            commits.append("commit")

    results = iter(
        [
            SimpleNamespace(should_publish=False, activity_bucket="WARM", state_updated=False),
            SimpleNamespace(should_publish=True, activity_bucket="WARM", state_updated=True),
            SimpleNamespace(should_publish=True, activity_bucket=None, state_updated=False),
        ]
    )

    class FakeAnalysisSchedulerService:
        def __init__(self, _uow):
            pass

        async def evaluate_indicator_update(self, **_kwargs):
            return next(results)

    monkeypatch.setattr(workers, "AsyncUnitOfWork", lambda: FakeSchedulerUow())
    monkeypatch.setattr(workers, "AnalysisSchedulerService", FakeAnalysisSchedulerService)
    monkeypatch.setattr(workers, "publish_event", lambda event_type, payload: published.append((event_type, payload)))

    event = _event(event_type="indicator_updated")
    await workers._handle_analysis_scheduler_event(event)
    assert published == []
    assert commits == []

    await workers._handle_analysis_scheduler_event(
        _event(event_type="indicator_updated", payload={"activity_score": 88.0})
    )
    assert published[-1][0] == "analysis_requested"
    assert commits == ["commit"]

    published.clear()
    await workers._handle_analysis_scheduler_event(
        _event(event_type="indicator_updated", payload={"activity_score": 55.0})
    )
    assert published[-1][1]["activity_bucket"] is None
    assert commits == ["commit"]

    published.clear()
    monkeypatch.setattr(
        workers,
        "read_cached_regime_async",
        lambda **kwargs: __import__("asyncio").sleep(0, result=SimpleNamespace(regime="bull_trend")),
    )
    monkeypatch.setattr(workers, "_run_regime_refresh", lambda _event_obj: __import__("asyncio").sleep(0, result=None))
    monkeypatch.setattr(
        workers,
        "cache_regime_snapshot_async",
        lambda **kwargs: __import__("asyncio").sleep(0, result=cached.append(kwargs)),
    )
    await workers._handle_regime_event(
        _event(event_type="indicator_updated", payload={"market_regime": "bull_trend", "regime_confidence": 0.8})
    )
    assert published == []

    async def changed_cycle(_event_obj):
        return PatternRegimeRefreshResult(
            status="ok",
            requires_commit=True,
            regime="bear_trend",
            regime_confidence=0.66,
            next_cycle="distribution",
            previous_cycle="accumulation",
        )

    monkeypatch.setattr(workers, "_run_regime_refresh", changed_cycle)
    await workers._handle_regime_event(
        _event(event_type="indicator_updated", payload={"market_regime": "bear_trend", "regime_confidence": 0.66})
    )
    assert {event_type for event_type, _ in published} == {"market_regime_changed", "market_cycle_changed"}
    assert cached[-1]["regime"] == "bear_trend"

    published.clear()

    async def same_cycle_without_regime(_event_obj):
        return PatternRegimeRefreshResult(
            status="ok",
            requires_commit=True,
            regime=None,
            regime_confidence=0.0,
            next_cycle="distribution",
            previous_cycle="distribution",
        )

    monkeypatch.setattr(
        workers, "read_cached_regime_async", lambda **kwargs: __import__("asyncio").sleep(0, result=None)
    )
    monkeypatch.setattr(workers, "_run_regime_refresh", same_cycle_without_regime)
    await workers._handle_regime_event(_event(event_type="indicator_updated"))
    assert published == []


@pytest.mark.asyncio
async def test_anomaly_and_news_handlers_delegate_to_domain_consumers(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        workers._ANOMALY_CONSUMER,
        "handle_event",
        lambda event: __import__("asyncio").sleep(0, result=calls.append(("fast", event.event_type))),
    )
    monkeypatch.setattr(
        workers._ANOMALY_SECTOR_CONSUMER,
        "handle_event",
        lambda event: __import__("asyncio").sleep(0, result=calls.append(("sector", event.event_type))),
    )
    monkeypatch.setattr(
        workers._NEWS_NORMALIZATION_CONSUMER,
        "handle_event",
        lambda event: __import__("asyncio").sleep(0, result=calls.append(("normalize", event.event_type))),
    )
    monkeypatch.setattr(
        workers._NEWS_CORRELATION_CONSUMER,
        "handle_event",
        lambda event: __import__("asyncio").sleep(0, result=calls.append(("correlate", event.event_type))),
    )

    await workers._handle_anomaly_event(_event(event_type="candle_closed"))
    await workers._handle_anomaly_sector_event(_event(event_type="anomaly_detected"))
    await workers._handle_news_normalization_event(_event(event_type="news_item_ingested"))
    await workers._handle_news_correlation_event(_event(event_type="news_item_normalized"))

    assert calls == [
        ("fast", "candle_closed"),
        ("sector", "anomaly_detected"),
        ("normalize", "news_item_ingested"),
        ("correlate", "news_item_normalized"),
    ]


def test_worker_domain_helpers_and_factory(monkeypatch) -> None:
    created: list[tuple[str, object, object]] = []

    class FakeConsumer:
        def __init__(self, config, *, handler, interested_event_types, **kwargs):
            del kwargs
            created.append((config.group_name, config.stream_name, handler, interested_event_types))

    monkeypatch.setattr(
        workers,
        "get_settings",
        lambda: SimpleNamespace(
            event_stream_name="iris:test:events",
            event_worker_batch_size=5,
            event_worker_block_milliseconds=250,
            event_worker_pending_idle_milliseconds=500,
        ),
    )
    monkeypatch.setattr(workers, "default_consumer_name", lambda group_name: f"default-{group_name}")
    monkeypatch.setattr(workers, "EventConsumer", FakeConsumer)

    for group_name in (
        INDICATOR_WORKER_GROUP,
        ANALYSIS_SCHEDULER_WORKER_GROUP,
        PATTERN_WORKER_GROUP,
        REGIME_WORKER_GROUP,
        DECISION_WORKER_GROUP,
        FUSION_WORKER_GROUP,
        CROSS_MARKET_WORKER_GROUP,
        PORTFOLIO_WORKER_GROUP,
        ANOMALY_WORKER_GROUP,
        ANOMALY_SECTOR_WORKER_GROUP,
        NEWS_NORMALIZATION_WORKER_GROUP,
        NEWS_CORRELATION_WORKER_GROUP,
        HYPOTHESIS_WORKER_GROUP,
    ):
        workers.create_worker(group_name)

    assert [group_name for group_name, _, _, _ in created] == [
        INDICATOR_WORKER_GROUP,
        ANALYSIS_SCHEDULER_WORKER_GROUP,
        PATTERN_WORKER_GROUP,
        REGIME_WORKER_GROUP,
        DECISION_WORKER_GROUP,
        FUSION_WORKER_GROUP,
        CROSS_MARKET_WORKER_GROUP,
        PORTFOLIO_WORKER_GROUP,
        ANOMALY_WORKER_GROUP,
        ANOMALY_SECTOR_WORKER_GROUP,
        NEWS_NORMALIZATION_WORKER_GROUP,
        NEWS_CORRELATION_WORKER_GROUP,
        HYPOTHESIS_WORKER_GROUP,
    ]
    assert [stream_name for _, stream_name, _, _ in created] == [
        build_delivery_stream_name(INDICATOR_WORKER_GROUP),
        build_delivery_stream_name(ANALYSIS_SCHEDULER_WORKER_GROUP),
        build_delivery_stream_name(PATTERN_WORKER_GROUP),
        build_delivery_stream_name(REGIME_WORKER_GROUP),
        build_delivery_stream_name(DECISION_WORKER_GROUP),
        build_delivery_stream_name(FUSION_WORKER_GROUP),
        build_delivery_stream_name(CROSS_MARKET_WORKER_GROUP),
        build_delivery_stream_name(PORTFOLIO_WORKER_GROUP),
        build_delivery_stream_name(ANOMALY_WORKER_GROUP),
        build_delivery_stream_name(ANOMALY_SECTOR_WORKER_GROUP),
        build_delivery_stream_name(NEWS_NORMALIZATION_WORKER_GROUP),
        build_delivery_stream_name(NEWS_CORRELATION_WORKER_GROUP),
        build_delivery_stream_name(HYPOTHESIS_WORKER_GROUP),
    ]
    interested_by_group = {group_name: interested for group_name, _, _, interested in created}
    assert interested_by_group[PATTERN_WORKER_GROUP] == {"analysis_requested", "indicator_updated", "candle_closed"}
    assert interested_by_group[REGIME_WORKER_GROUP] == {"indicator_updated"}
    for group_name in (
        INDICATOR_WORKER_GROUP,
        ANALYSIS_SCHEDULER_WORKER_GROUP,
        DECISION_WORKER_GROUP,
        FUSION_WORKER_GROUP,
        CROSS_MARKET_WORKER_GROUP,
        PORTFOLIO_WORKER_GROUP,
        ANOMALY_WORKER_GROUP,
        ANOMALY_SECTOR_WORKER_GROUP,
        NEWS_NORMALIZATION_WORKER_GROUP,
        NEWS_CORRELATION_WORKER_GROUP,
        HYPOTHESIS_WORKER_GROUP,
    ):
        assert interested_by_group[group_name] is None

    with pytest.raises(ValueError, match="Unsupported event worker group"):
        workers.create_worker("unsupported")


@pytest.mark.asyncio
async def test_pattern_handler_non_pattern_signal_branch(monkeypatch) -> None:
    published: list[tuple[str, dict[str, object]]] = []
    emitted: list[list[str]] = []

    monkeypatch.setattr(workers, "publish_event", lambda event_type, payload: published.append((event_type, payload)))
    monkeypatch.setattr(
        workers,
        "_emit_signal_created_events",
        lambda *, coin_id, timeframe, timestamp, signal_types: emitted.append(signal_types),
    )
    monkeypatch.setattr(
        workers,
        "_run_pattern_detection",
        lambda _event_obj: __import__("asyncio").sleep(0, result=["macd_cross"]),
    )

    await workers._handle_pattern_event(_event(event_type="analysis_requested"))

    assert published == []
    assert emitted == [["macd_cross"]]


@pytest.mark.asyncio
async def test_hypothesis_handler_delegates_to_consumer(monkeypatch) -> None:
    calls: list[IrisEvent] = []

    class FakeConsumer:
        async def handle_event(self, event: IrisEvent) -> None:
            calls.append(event)

    monkeypatch.setattr(workers, "_HYPOTHESIS_CONSUMER", FakeConsumer())

    event = _event(event_type="signal_created", payload={"signal_type": "bull_breakout"})
    await workers._handle_hypothesis_event(event)

    assert calls == [event]
