from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from sqlalchemy import select

from src.apps.cross_market.engine import (
    _best_lagged_correlation,
    _candidate_leaders,
    _latest_leader_decision,
    _pearson,
    cross_market_alignment_weight,
    detect_market_leader,
    process_cross_market_event,
    refresh_sector_momentum,
    update_coin_relations,
)
from src.apps.indicators.models import CoinMetrics
from src.apps.cross_market.models import CoinRelation, SectorMetric
from src.apps.market_data.repos import CandlePoint
from src.apps.signals.models import MarketDecision
from tests.cross_market_support import (
    DEFAULT_START,
    correlated_close_series,
    create_cross_market_coin,
    generate_close_series,
    seed_candles,
    set_market_metrics,
)


def _points_from_closes(closes: list[float]) -> list[CandlePoint]:
    points: list[CandlePoint] = []
    previous = closes[0]
    for index, close in enumerate(closes):
        points.append(
            CandlePoint(
                timestamp=DEFAULT_START + timedelta(hours=index),
                open=previous,
                high=max(previous, close) * 1.01,
                low=min(previous, close) * 0.99,
                close=close,
                volume=1_000.0 + index,
            )
        )
        previous = close
    return points


def test_cross_market_helper_math_and_alignment_branches(db_session, monkeypatch) -> None:
    assert _pearson([1.0, 1.0, 1.0], [2.0, 2.0, 2.0]) == 0.0
    assert _pearson([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0

    leader_returns = [0.009 if index % 5 else -0.002 for index in range(80)]
    leader_closes = generate_close_series(start_price=100.0, returns=leader_returns)
    follower_closes = correlated_close_series(leader_returns=leader_returns, lag_bars=2, start_price=60.0)
    correlation, lag_hours, sample_size = _best_lagged_correlation(
        _points_from_closes(leader_closes),
        _points_from_closes(follower_closes),
        timeframe=60,
    )
    assert correlation > 0.4
    assert lag_hours >= 1
    assert sample_size >= 48

    follower = create_cross_market_coin(
        db_session,
        symbol="SOLUSD_EVT",
        name="Solana Event Test",
        sector_name="smart_contract",
    )
    leader = create_cross_market_coin(
        db_session,
        symbol="BTCUSD_EVT",
        name="Bitcoin Event Test",
        sector_name="store_of_value",
    )
    relation = CoinRelation(
        leader_coin_id=int(leader.id),
        follower_coin_id=int(follower.id),
        correlation=0.81,
        lag_hours=4,
        confidence=0.72,
        updated_at=DEFAULT_START,
    )
    db_session.add(relation)
    db_session.add(
        SectorMetric(
            sector_id=int(follower.sector_id),
            timeframe=60,
            sector_strength=0.8,
            relative_strength=0.6,
            capital_flow=0.4,
            avg_price_change_24h=5.0,
            avg_volume_change_24h=12.0,
            volatility=0.05,
            trend="bullish",
            updated_at=DEFAULT_START,
        )
    )
    db_session.commit()
    set_market_metrics(
        db_session,
        coin_id=int(leader.id),
        regime="bull_trend",
        price_change_24h=5.5,
        volume_change_24h=18.0,
    )

    monkeypatch.setattr("src.apps.cross_market.engine.read_cached_correlation", lambda **_: None)
    assert cross_market_alignment_weight(db_session, coin_id=int(follower.id), timeframe=60, directional_bias=0) == 1.0
    assert cross_market_alignment_weight(db_session, coin_id=int(follower.id), timeframe=60, directional_bias=1) > 1.0
    assert cross_market_alignment_weight(db_session, coin_id=int(follower.id), timeframe=60, directional_bias=-1) < 1.0

    decision, confidence = _latest_leader_decision(db_session, leader_coin_id=int(leader.id), timeframe=60)
    assert decision == "BUY"
    assert confidence >= 0.25


def test_cross_market_relation_and_sector_skip_paths(db_session, monkeypatch) -> None:
    assert update_coin_relations(db_session, follower_coin_id=999999, timeframe=60, emit_events=False)["reason"] == "follower_not_found"
    assert refresh_sector_momentum(db_session, timeframe=137, emit_events=False)["status"] in {"ok", "skipped"}

    empty_coin = create_cross_market_coin(
        db_session,
        symbol="ADAUSD_EVT",
        name="Cardano Event Test",
        sector_name="layer1",
    )
    assert update_coin_relations(db_session, follower_coin_id=int(empty_coin.id), timeframe=60, emit_events=False)["reason"] == "insufficient_follower_candles"

    follower = create_cross_market_coin(
        db_session,
        symbol="ETHUSD_EVT",
        name="Ethereum Event Test",
        sector_name="smart_contract",
    )
    leader = create_cross_market_coin(
        db_session,
        symbol="BTCUSD_EVT",
        name="Bitcoin Event Test",
        sector_name="store_of_value",
    )
    leader_closes = generate_close_series(start_price=100.0, returns=[0.01] * 80)
    follower_closes = generate_close_series(start_price=50.0, returns=[-0.01] * 80)
    seed_candles(db_session, coin=leader, interval="1h", closes=leader_closes, start=DEFAULT_START)
    seed_candles(db_session, coin=follower, interval="1h", closes=follower_closes, start=DEFAULT_START)

    relations_result = update_coin_relations(db_session, follower_coin_id=int(follower.id), timeframe=60, emit_events=False)
    assert relations_result["reason"] == "relations_not_found"

    captured: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr("src.apps.cross_market.engine.publish_event", lambda event_type, payload: captured.append((event_type, payload)))
    monkeypatch.setattr(
        "src.apps.cross_market.engine._create_market_predictions_impl",
        lambda *args, **kwargs: {"status": "ok", "created": 1},
    )
    set_market_metrics(
        db_session,
        coin_id=int(follower.id),
        regime="sideways_range",
        price_change_24h=0.5,
        volume_change_24h=5.0,
    )
    assert detect_market_leader(
        db_session,
        coin_id=int(follower.id),
        timeframe=60,
        payload={"activity_bucket": "COLD"},
        emit_events=True,
    )["reason"] == "leader_threshold_not_met"

    bear = create_cross_market_coin(
        db_session,
        symbol="XRPUSD_EVT",
        name="Ripple Event Test",
        sector_name="payments",
    )
    set_market_metrics(
        db_session,
        coin_id=int(bear.id),
        regime="bear_trend",
        price_change_24h=-4.5,
        volume_change_24h=20.0,
    )
    result = detect_market_leader(
        db_session,
        coin_id=int(bear.id),
        timeframe=60,
        payload={"activity_bucket": "HOT", "price_change_24h": -4.5, "market_regime": "bear_trend"},
        emit_events=True,
    )
    assert result["status"] == "ok"
    assert result["direction"] == "down"
    assert captured[-1][0] == "market_leader_detected"


def test_sector_rotation_and_process_dispatch(db_session, monkeypatch) -> None:
    smart = create_cross_market_coin(
        db_session,
        symbol="SOLUSD_EVT",
        name="Solana Event Test",
        sector_name="smart_contract",
    )
    defi = create_cross_market_coin(
        db_session,
        symbol="UNIUSD_EVT",
        name="Uniswap Event Test",
        sector_name="defi",
    )
    set_market_metrics(
        db_session,
        coin_id=int(smart.id),
        regime="bull_trend",
        price_change_24h=6.0,
        volume_change_24h=25.0,
    )
    set_market_metrics(
        db_session,
        coin_id=int(defi.id),
        regime="bull_trend",
        price_change_24h=2.0,
        volume_change_24h=8.0,
    )
    isolated_timeframe = 137
    first = refresh_sector_momentum(db_session, timeframe=isolated_timeframe, emit_events=False)
    assert first["status"] == "ok"

    set_market_metrics(
        db_session,
        coin_id=int(smart.id),
        regime="bear_trend",
        price_change_24h=-90.0,
        volume_change_24h=-40.0,
    )
    set_market_metrics(
        db_session,
        coin_id=int(defi.id),
        regime="bull_trend",
        price_change_24h=120.0,
        volume_change_24h=80.0,
    )
    published: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr("src.apps.cross_market.engine.publish_event", lambda event_type, payload: published.append((event_type, payload)))
    second = refresh_sector_momentum(db_session, timeframe=isolated_timeframe, emit_events=True)
    assert second["status"] == "ok"
    assert second["updated"] >= 2

    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        "src.apps.cross_market.engine.update_coin_relations",
        lambda *args, **kwargs: calls.append(("relations", kwargs["emit_events"])) or {"status": "ok"},
    )
    monkeypatch.setattr(
        "src.apps.cross_market.engine.refresh_sector_momentum",
        lambda *args, **kwargs: calls.append(("sectors", kwargs["emit_events"])) or {"status": "ok"},
    )
    monkeypatch.setattr(
        "src.apps.cross_market.engine.detect_market_leader",
        lambda *args, **kwargs: calls.append(("leader", kwargs["emit_events"])) or {"status": "ok"},
    )

    candle_result = process_cross_market_event(
        db_session,
        coin_id=int(smart.id),
        timeframe=60,
        event_type="candle_closed",
        payload={},
        emit_events=True,
    )
    indicator_result = process_cross_market_event(
        db_session,
        coin_id=int(smart.id),
        timeframe=60,
        event_type="indicator_updated",
        payload={"market_regime": "bull_trend"},
        emit_events=True,
    )
    assert candle_result["leader"]["reason"] == "leader_detection_not_requested"
    assert indicator_result["leader"]["status"] == "ok"
    assert calls == [
        ("relations", True),
        ("sectors", False),
        ("relations", False),
        ("sectors", True),
        ("leader", True),
    ]


def test_cross_market_candidate_publish_and_fallback_branches(db_session, monkeypatch) -> None:
    short_points = _points_from_closes(generate_close_series(start_price=100.0, returns=[0.01] * 10))
    assert _best_lagged_correlation(short_points, short_points, timeframe=60) == (0.0, 0, 10)
    exact_points = _points_from_closes(generate_close_series(start_price=100.0, returns=[0.01] * 48))
    exact_correlation, _, exact_size = _best_lagged_correlation(exact_points, exact_points, timeframe=60)
    assert exact_correlation > 0.99
    assert exact_size == 48

    follower = create_cross_market_coin(
        db_session,
        symbol="FOLUSD_EVT",
        name="Follower Event Test",
        sector_name="smart_contract",
    )
    preferred = create_cross_market_coin(
        db_session,
        symbol="BTCUSD_EVT",
        name="Bitcoin Event Test",
        sector_name="store_of_value",
    )
    same_sector_short = create_cross_market_coin(
        db_session,
        symbol="ALTUSD_EVT",
        name="Alt Event Test",
        sector_name="smart_contract",
    )
    monkeypatch.setattr("src.apps.cross_market.engine.LEADER_SYMBOLS", ("BTCUSD_EVT",))
    set_market_metrics(
        db_session,
        coin_id=int(preferred.id),
        regime="bull_trend",
        price_change_24h=6.0,
        volume_change_24h=22.0,
        market_cap=10_000_000_000.0,
    )
    set_market_metrics(
        db_session,
        coin_id=int(same_sector_short.id),
        regime="bull_trend",
        price_change_24h=4.0,
        volume_change_24h=18.0,
        market_cap=500_000_000.0,
    )
    set_market_metrics(
        db_session,
        coin_id=int(follower.id),
        regime="bull_trend",
        price_change_24h=3.0,
        volume_change_24h=15.0,
        market_cap=3_000_000_000.0,
    )
    leader_returns = [0.008 if index % 6 else -0.002 for index in range(90)]
    follower_closes = correlated_close_series(leader_returns=leader_returns, lag_bars=3, start_price=60.0)
    seed_candles(db_session, coin=preferred, interval="1h", closes=generate_close_series(start_price=100.0, returns=leader_returns), start=DEFAULT_START)
    seed_candles(db_session, coin=follower, interval="1h", closes=follower_closes, start=DEFAULT_START)
    seed_candles(
        db_session,
        coin=same_sector_short,
        interval="1h",
        closes=generate_close_series(start_price=20.0, returns=[0.01] * 10),
        start=DEFAULT_START,
    )

    leaders = _candidate_leaders(db_session, follower=follower, limit=200)
    assert leaders[0].symbol == "BTCUSD_EVT"
    assert any(int(coin.sector_id or 0) == int(follower.sector_id or 0) for coin in leaders[1:])
    assert any(int(coin.id) == int(same_sector_short.id) for coin in leaders)

    published: list[str] = []
    monkeypatch.setattr("src.apps.cross_market.engine.publish_event", lambda event_type, payload: published.append(event_type))
    first = update_coin_relations(db_session, follower_coin_id=int(follower.id), timeframe=60, emit_events=True)
    second = update_coin_relations(db_session, follower_coin_id=int(follower.id), timeframe=60, emit_events=True)
    assert first["status"] == "ok"
    assert first["published"] >= 1
    assert second["published"] == 0
    assert published.count("correlation_updated") >= 1

    follower_without_sector = create_cross_market_coin(
        db_session,
        symbol="NOSCTR_EVT",
        name="No Sector Event Test",
        sector_name="payments",
    )
    follower_without_sector.sector_id = None
    db_session.commit()
    orphan_preferred = create_cross_market_coin(
        db_session,
        symbol="NOMETRICS_EVT",
        name="No Metrics Event Test",
        sector_name="payments",
    )
    monkeypatch.setattr("src.apps.cross_market.engine.LEADER_SYMBOLS", ("BTCUSD_EVT", "NOMETRICS_EVT"))
    no_sector_leaders = _candidate_leaders(db_session, follower=follower_without_sector)
    assert orphan_preferred not in no_sector_leaders
    assert no_sector_leaders[0].symbol == "BTCUSD_EVT"


def test_cross_market_decision_and_alignment_fallback_branches(db_session, monkeypatch) -> None:
    assert detect_market_leader(db_session, coin_id=999999, timeframe=60, payload={}, emit_events=False)["reason"] == "coin_metrics_not_found"

    follower = create_cross_market_coin(
        db_session,
        symbol="ETHUSD_EVT",
        name="Ethereum Event Test",
        sector_name="smart_contract",
    )
    bearish_leader = create_cross_market_coin(
        db_session,
        symbol="BTCUSD_EVT",
        name="Bitcoin Event Test",
        sector_name="store_of_value",
    )
    bearish_metrics_leader = create_cross_market_coin(
        db_session,
        symbol="BNBUSD_EVT",
        name="BNB Event Test",
        sector_name="store_of_value",
    )
    missing_leader = create_cross_market_coin(
        db_session,
        symbol="SOLUSD_EVT",
        name="Solana Event Test",
        sector_name="layer1",
    )
    set_market_metrics(
        db_session,
        coin_id=int(bearish_leader.id),
        regime="bear_trend",
        price_change_24h=-5.5,
        volume_change_24h=24.0,
    )
    set_market_metrics(
        db_session,
        coin_id=int(bearish_metrics_leader.id),
        regime="bear_trend",
        price_change_24h=-5.5,
        volume_change_24h=24.0,
    )
    metrics_row = db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(missing_leader.id)).limit(1))
    if metrics_row is not None:
        db_session.delete(metrics_row)
    db_session.commit()

    db_session.add(
        MarketDecision(
            coin_id=int(bearish_leader.id),
            timeframe=240,
            decision="BUY",
            confidence=0.91,
            signal_count=3,
        )
    )
    db_session.commit()

    assert _latest_leader_decision(db_session, leader_coin_id=int(bearish_leader.id), timeframe=240) == ("BUY", 0.91)
    assert _latest_leader_decision(db_session, leader_coin_id=int(bearish_metrics_leader.id), timeframe=60)[0] == "SELL"
    assert _latest_leader_decision(db_session, leader_coin_id=int(missing_leader.id), timeframe=60) == (None, 0.0)
    success_without_event = detect_market_leader(
        db_session,
        coin_id=int(bearish_metrics_leader.id),
        timeframe=60,
        payload={"activity_bucket": "HOT", "price_change_24h": -5.5, "market_regime": "bear_trend"},
        emit_events=False,
    )
    assert success_without_event["status"] == "ok"
    neutral = create_cross_market_coin(
        db_session,
        symbol="XRPUSD_EVT",
        name="Ripple Event Test",
        sector_name="payments",
    )
    set_market_metrics(
        db_session,
        coin_id=int(neutral.id),
        regime="sideways_range",
        price_change_24h=0.0,
        volume_change_24h=14.0,
    )
    assert _latest_leader_decision(db_session, leader_coin_id=int(neutral.id), timeframe=60) == ("HOLD", 0.3)

    db_session.add_all(
        [
            CoinRelation(
                leader_coin_id=int(bearish_metrics_leader.id),
                follower_coin_id=int(follower.id),
                correlation=0.8,
                lag_hours=4,
                confidence=0.8,
                updated_at=DEFAULT_START,
            ),
            CoinRelation(
                leader_coin_id=int(missing_leader.id),
                follower_coin_id=int(follower.id),
                correlation=0.8,
                lag_hours=4,
                confidence=0.8,
                updated_at=DEFAULT_START,
            ),
            SectorMetric(
                sector_id=int(follower.sector_id),
                timeframe=60,
                sector_strength=-4.0,
                relative_strength=-2.0,
                capital_flow=-0.4,
                avg_price_change_24h=-4.0,
                avg_volume_change_24h=-12.0,
                volatility=0.07,
                trend="bearish",
                updated_at=DEFAULT_START,
            ),
        ]
    )
    db_session.commit()

    monkeypatch.setattr("src.apps.cross_market.engine.read_cached_correlation", lambda **_: None)
    bearish_weight = cross_market_alignment_weight(db_session, coin_id=int(follower.id), timeframe=240, directional_bias=-1)
    bullish_weight = cross_market_alignment_weight(db_session, coin_id=int(follower.id), timeframe=240, directional_bias=1)
    assert bearish_weight > 1.0
    assert bullish_weight < 1.0

    follower_without_sector = create_cross_market_coin(
        db_session,
        symbol="NOSECTOR_EVT",
        name="No Sector Follower Test",
        sector_name="payments",
    )
    follower_without_sector.sector_id = None
    db_session.add(
        CoinRelation(
            leader_coin_id=int(neutral.id),
            follower_coin_id=int(follower_without_sector.id),
            correlation=0.8,
            lag_hours=4,
            confidence=0.8,
            updated_at=DEFAULT_START,
        )
    )
    db_session.commit()
    assert 0.75 <= cross_market_alignment_weight(db_session, coin_id=int(follower_without_sector.id), timeframe=240, directional_bias=1) <= 1.35

    follower_with_sideways_sector = create_cross_market_coin(
        db_session,
        symbol="SIDEWAYS_EVT",
        name="Sideways Follower Test",
        sector_name="payments",
    )
    db_session.add_all(
        [
            CoinRelation(
                leader_coin_id=int(neutral.id),
                follower_coin_id=int(follower_with_sideways_sector.id),
                correlation=0.8,
                lag_hours=4,
                confidence=0.8,
                updated_at=DEFAULT_START,
            ),
            SectorMetric(
                sector_id=int(follower_with_sideways_sector.sector_id),
                timeframe=60,
                sector_strength=0.0,
                relative_strength=0.0,
                capital_flow=0.0,
                avg_price_change_24h=0.0,
                avg_volume_change_24h=0.0,
                volatility=0.04,
                trend="sideways",
                updated_at=DEFAULT_START,
            ),
        ]
    )
    db_session.commit()
    assert 0.75 <= cross_market_alignment_weight(db_session, coin_id=int(follower_with_sideways_sector.id), timeframe=240, directional_bias=1) <= 1.35

    follower_without_sector_metric = create_cross_market_coin(
        db_session,
        symbol="NSMUSD_EVT",
        name="No Sector Metric Test",
        sector_name="unique_payments",
    )
    db_session.add(
        CoinRelation(
            leader_coin_id=int(neutral.id),
            follower_coin_id=int(follower_without_sector_metric.id),
            correlation=0.8,
            lag_hours=4,
            confidence=0.8,
            updated_at=DEFAULT_START,
        )
    )
    db_session.commit()
    assert 0.75 <= cross_market_alignment_weight(db_session, coin_id=int(follower_without_sector_metric.id), timeframe=240, directional_bias=1) <= 1.35


def test_cross_market_refresh_sector_momentum_edge_branches(monkeypatch) -> None:
    class Result:
        def __init__(self, *, first=None, rows=None) -> None:
            self._first = first
            self._rows = rows or []

        def first(self):
            return self._first

        def all(self):
            return self._rows

    class SessionStub:
        def __init__(self, responses: list[Result]) -> None:
            self._responses = iter(responses)

        def execute(self, _stmt):
            return next(self._responses)

        def commit(self) -> None:
            return None

    empty_session = SessionStub([Result(first=None), Result(rows=[])])
    assert refresh_sector_momentum(empty_session, timeframe=60, emit_events=False)["reason"] == "sector_rows_not_found"

    rotating_rows = [
        SimpleNamespace(
            sector_id=1,
            avg_price_change_24h=-3.0,
            avg_volume_change_24h=-12.0,
            avg_volatility=0.05,
            sector_strength=-3.0,
            capital_flow=-0.3,
        ),
        SimpleNamespace(
            sector_id=2,
            avg_price_change_24h=5.0,
            avg_volume_change_24h=18.0,
            avg_volatility=0.07,
            sector_strength=5.0,
            capital_flow=0.6,
        ),
    ]
    published: list[str] = []
    monkeypatch.setattr("src.apps.cross_market.engine.publish_event", lambda event_type, payload: published.append(event_type))
    rotating_session = SessionStub(
        [
            Result(first=SimpleNamespace(sector_id=1, name="old_sector", relative_strength=-1.0)),
            Result(rows=rotating_rows),
            Result(),
            Result(first=SimpleNamespace(sector_id=2, name="new_sector", relative_strength=2.5)),
        ]
    )
    result = refresh_sector_momentum(rotating_session, timeframe=60, emit_events=True)
    assert result["updated"] == 2
    assert published == ["sector_rotation_detected"]
