from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from app.apps.cross_market.models import SectorMetric
from app.apps.indicators.models import CoinMetrics
from app.apps.patterns.domain.context import (
    _cycle_alignment,
    _liquidity_score,
    _pattern_temperature,
    _sector_alignment,
    _signal_regime,
    enrich_signal_context,
)
from app.apps.patterns.models import MarketCycle, PatternStatistic
from app.apps.patterns.domain.registry import sync_pattern_metadata
from app.apps.signals.models import Signal
from tests.cross_market_support import DEFAULT_START
from tests.fusion_support import create_test_coin, upsert_coin_metrics
from tests.portfolio_support import create_sector


def test_context_helper_branches(db_session, monkeypatch) -> None:
    assert _liquidity_score(None) == 1.0
    thin = SimpleNamespace(volume_change_24h=-25.0, market_cap=100_000_000.0)
    assert _liquidity_score(thin) == 0.75
    thick = SimpleNamespace(volume_change_24h=30.0, market_cap=20_000_000_000.0)
    assert _liquidity_score(thick) == 1.25
    assert _sector_alignment(None, 1) == 1.0
    assert _sector_alignment(SimpleNamespace(sector_strength=1.0, relative_strength=0.2), 1) == 1.12
    assert _sector_alignment(SimpleNamespace(sector_strength=-1.0, relative_strength=-0.2), -1) == 1.12
    assert _sector_alignment(SimpleNamespace(sector_strength=0.0, relative_strength=-0.4), 1) == 0.88
    assert _sector_alignment(SimpleNamespace(sector_strength=0.0, relative_strength=0.4), -1) == 0.88
    assert _sector_alignment(SimpleNamespace(sector_strength=0.0, relative_strength=0.0), 1) == 1.0
    assert _cycle_alignment(None, 1) == 1.0
    assert _cycle_alignment(SimpleNamespace(cycle_phase="MARKDOWN"), -1) == 1.15
    assert _cycle_alignment(SimpleNamespace(cycle_phase="LATE_MARKUP"), 1) == 0.92
    assert _cycle_alignment(SimpleNamespace(cycle_phase="UNKNOWN"), 1) == 1.0
    assert _pattern_temperature(db_session, None, 15) == 1.0
    assert _pattern_temperature(db_session, "bull_flag", 15, "bull_trend") == 1.0
    assert _signal_regime(None, 15) is None

    metrics = SimpleNamespace(coin_id=1, market_regime="sideways_range", market_regime_details={"15": {"regime": "bull_trend", "confidence": 0.8}})
    monkeypatch.setattr("app.apps.patterns.domain.context.read_cached_regime", lambda **_: SimpleNamespace(regime="high_volatility"))
    assert _signal_regime(metrics, 15) == "high_volatility"
    monkeypatch.setattr("app.apps.patterns.domain.context.read_cached_regime", lambda **_: None)
    assert _signal_regime(metrics, 15) == "bull_trend"


def test_enrich_signal_context_updates_real_signal_rows(db_session) -> None:
    sync_pattern_metadata(db_session)
    coin = create_test_coin(db_session, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    sector = create_sector(db_session, name="store_of_value")
    coin.sector_id = int(sector.id)
    coin.sector_code = sector.name
    db_session.commit()

    metrics = upsert_coin_metrics(db_session, coin_id=int(coin.id), regime="bull_trend", timeframe=15)
    metrics.market_regime_details = {"15": {"regime": "bull_trend", "confidence": 0.83}}
    metrics.bb_width = 0.03
    metrics.volume_change_24h = -25.0
    metrics.market_cap = 100_000_000.0
    db_session.add(
        SectorMetric(
            sector_id=int(sector.id),
            timeframe=15,
            sector_strength=0.7,
            relative_strength=-0.3,
            capital_flow=0.4,
            avg_price_change_24h=3.0,
            avg_volume_change_24h=-10.0,
            volatility=0.05,
            trend="bullish",
            updated_at=DEFAULT_START,
        )
    )
    db_session.add(
        MarketCycle(
            coin_id=int(coin.id),
            timeframe=15,
            cycle_phase="LATE_MARKUP",
            confidence=0.8,
            detected_at=DEFAULT_START,
        )
    )
    db_session.add(
        PatternStatistic(
            pattern_slug="bull_flag",
            timeframe=15,
            market_regime="bull_trend",
            sample_size=20,
            total_signals=20,
            successful_signals=16,
            success_rate=0.8,
            avg_return=0.03,
            avg_drawdown=-0.02,
            temperature=1.18,
            enabled=True,
        )
    )
    timestamp = DEFAULT_START + timedelta(hours=4)
    db_session.add_all(
        [
            Signal(
                coin_id=int(coin.id),
                timeframe=15,
                signal_type="pattern_cluster_breakout",
                confidence=0.72,
                priority_score=0.72,
                context_score=1.0,
                regime_alignment=1.0,
                candle_timestamp=timestamp,
            ),
            Signal(
                coin_id=int(coin.id),
                timeframe=15,
                signal_type="pattern_bull_flag",
                confidence=0.74,
                priority_score=0.74,
                context_score=1.0,
                regime_alignment=1.0,
                candle_timestamp=timestamp,
            ),
            Signal(
                coin_id=int(coin.id),
                timeframe=15,
                signal_type="pattern_bollinger_squeeze",
                confidence=0.7,
                priority_score=0.7,
                context_score=1.0,
                regime_alignment=1.0,
                candle_timestamp=timestamp,
            ),
        ]
    )
    db_session.commit()

    result = enrich_signal_context(
        db_session,
        coin_id=int(coin.id),
        timeframe=15,
        candle_timestamp=timestamp.isoformat(),
        commit=True,
    )
    db_session.expire_all()
    bull_flag = db_session.scalar(
        db_session.query(Signal).filter_by(coin_id=int(coin.id), timeframe=15, signal_type="pattern_bull_flag").statement
    )
    assert result == {"status": "ok", "coin_id": int(coin.id), "timeframe": 15, "signals": 3}
    assert bull_flag is not None
    assert bull_flag.regime_alignment > 1.0
    assert bull_flag.context_score > 0.0
    assert bull_flag.priority_score > bull_flag.confidence
    assert enrich_signal_context(db_session, coin_id=int(coin.id), timeframe=60)["reason"] == "signals_not_found"
