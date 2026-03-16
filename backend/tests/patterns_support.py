from datetime import UTC, datetime, timedelta, timezone

from iris.apps.cross_market.models import SectorMetric
from iris.apps.indicators.models import CoinMetrics
from iris.apps.market_data.models import Candle
from iris.apps.patterns.domain.registry import PATTERN_CATALOG, SUPPORTED_PATTERN_FEATURES
from iris.apps.patterns.models import DiscoveredPattern, MarketCycle, PatternFeature, PatternRegistry, PatternStatistic
from iris.apps.signals.models import Signal
from sqlalchemy import delete
from sqlalchemy.orm import Session

from tests.fusion_support import create_test_coin, upsert_coin_metrics
from tests.portfolio_support import create_sector


def _ensure_pattern_feature(db: Session, feature_slug: str, *, enabled: bool) -> PatternFeature:
    row = db.get(PatternFeature, feature_slug)
    if row is None:
        row = PatternFeature(feature_slug=feature_slug, enabled=enabled)
        db.add(row)
    else:
        row.enabled = enabled
    return row


def _ensure_pattern_registry(
    db: Session,
    slug: str,
    *,
    category: str,
    enabled: bool,
    cpu_cost: int,
    lifecycle_state: str,
) -> PatternRegistry:
    row = db.get(PatternRegistry, slug)
    if row is None:
        row = PatternRegistry(
            slug=slug,
            category=category,
            enabled=enabled,
            cpu_cost=cpu_cost,
            lifecycle_state=lifecycle_state,
        )
        db.add(row)
    else:
        row.category = category
        row.enabled = enabled
        row.cpu_cost = cpu_cost
        row.lifecycle_state = lifecycle_state
    return row


def _replace_pattern_stat(
    db: Session,
    *,
    pattern_slug: str,
    timeframe: int,
    market_regime: str,
    sample_size: int,
    successful_signals: int,
    success_rate: float,
    avg_return: float,
    avg_drawdown: float,
    temperature: float,
) -> PatternStatistic:
    row = db.get(PatternStatistic, (pattern_slug, timeframe, market_regime))
    payload = {
        "sample_size": sample_size,
        "total_signals": sample_size,
        "successful_signals": successful_signals,
        "success_rate": success_rate,
        "avg_return": avg_return,
        "avg_drawdown": avg_drawdown,
        "temperature": temperature,
        "enabled": True,
    }
    if row is None:
        row = PatternStatistic(
            pattern_slug=pattern_slug,
            timeframe=timeframe,
            market_regime=market_regime,
            **payload,
        )
        db.add(row)
    else:
        for key, value in payload.items():
            setattr(row, key, value)
    return row


def _merge_signal(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    signal_type: str,
    confidence: float,
    priority_score: float,
    context_score: float,
    regime_alignment: float,
    candle_timestamp: datetime,
    created_at: datetime,
    market_regime: str | None = None,
) -> Signal:
    row = Signal(
        coin_id=coin_id,
        timeframe=timeframe,
        signal_type=signal_type,
        confidence=confidence,
        priority_score=priority_score,
        context_score=context_score,
        regime_alignment=regime_alignment,
        market_regime=market_regime,
        candle_timestamp=candle_timestamp,
        created_at=created_at,
    )
    db.add(row)
    return row


def _merge_candles(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    start: datetime,
    closes: list[float],
) -> None:
    db.execute(delete(Candle).where(Candle.coin_id == coin_id, Candle.timeframe == timeframe))
    for index, close in enumerate(closes):
        timestamp = start + timedelta(minutes=timeframe * index)
        open_price = close - 0.6
        db.add(
            Candle(
                coin_id=coin_id,
                timeframe=timeframe,
                timestamp=timestamp,
                open=open_price,
                high=close + 0.9,
                low=open_price - 0.5,
                close=close,
                volume=1_000.0 + index * 5.0,
            )
        )


def seed_pattern_catalog_metadata(db: Session, *, include_context_engine: bool = False) -> None:
    for feature_slug in SUPPORTED_PATTERN_FEATURES:
        _ensure_pattern_feature(db, feature_slug, enabled=True)
    if include_context_engine:
        _ensure_pattern_feature(db, "pattern_context_engine", enabled=True)
    for entry in PATTERN_CATALOG:
        _ensure_pattern_registry(
            db,
            entry.slug,
            category=entry.category,
            enabled=True,
            cpu_cost=entry.cpu_cost,
            lifecycle_state="ACTIVE",
        )
    db.commit()


def seed_pattern_api_state(db: Session) -> dict[str, object]:
    signal_timestamp = datetime(2026, 3, 12, 12, 0, tzinfo=UTC)
    candle_start = signal_timestamp - timedelta(minutes=15 * 39)
    candle_start_60 = signal_timestamp - timedelta(minutes=60 * 29)
    candle_start_240 = signal_timestamp - timedelta(minutes=240 * 1)
    candle_start_1440 = signal_timestamp - timedelta(minutes=1440 * 1)
    later_signal_timestamp = signal_timestamp + timedelta(hours=1)

    btc = create_test_coin(db, symbol="BTCUSD_EVT", name="Bitcoin Event Test")
    eth = create_test_coin(db, symbol="ETHUSD_EVT", name="Ethereum Event Test")
    sol = create_test_coin(db, symbol="SOLUSD_EVT", name="Solana Event Test")

    btc_sector = create_sector(db, name="store_of_value", description="Store of value assets")
    eth_sector = create_sector(db, name="smart_contract", description="Smart contract platforms")
    sol_sector = create_sector(db, name="high_beta", description="High beta assets")
    btc.sector_id = int(btc_sector.id)
    btc.sector_code = str(btc_sector.name)
    eth.sector_id = int(eth_sector.id)
    eth.sector_code = str(eth_sector.name)
    sol.sector_id = int(sol_sector.id)
    sol.sector_code = str(sol_sector.name)
    db.commit()

    btc_metrics = upsert_coin_metrics(db, coin_id=int(btc.id), regime="bull_trend", timeframe=15)
    eth_metrics = upsert_coin_metrics(db, coin_id=int(eth.id), regime="sideways_range", timeframe=15)
    sol_metrics = upsert_coin_metrics(db, coin_id=int(sol.id), regime="high_volatility", timeframe=15)

    for metrics, market_cap, price_current, volume_change_24h, activity_score in (
        (btc_metrics, 900_000_000_000.0, 112_000.0, 21.0, 95.0),
        (eth_metrics, 350_000_000_000.0, 4_500.0, 14.0, 82.0),
        (sol_metrics, 95_000_000_000.0, 220.0, 6.0, 68.0),
    ):
        metrics.market_cap = market_cap
        metrics.price_current = price_current
        metrics.price_change_24h = 6.2 if metrics is btc_metrics else 3.1 if metrics is eth_metrics else -1.4
        metrics.price_change_7d = 12.4 if metrics is btc_metrics else 7.4 if metrics is eth_metrics else 2.2
        metrics.volume_change_24h = volume_change_24h
        metrics.volatility = 0.055 if metrics is btc_metrics else 0.048 if metrics is eth_metrics else 0.083
        metrics.activity_score = activity_score
        metrics.market_regime_details = {
            "15": {"regime": metrics.market_regime, "confidence": 0.81},
            "60": {"regime": metrics.market_regime, "confidence": 0.79},
        }

    _ensure_pattern_feature(db, "market_regime_engine", enabled=True)
    _ensure_pattern_feature(db, "pattern_context_engine", enabled=True)
    _ensure_pattern_registry(db, "bull_flag", category="continuation", enabled=True, cpu_cost=2, lifecycle_state="ACTIVE")
    _ensure_pattern_registry(
        db,
        "breakout_retest",
        category="structural",
        enabled=True,
        cpu_cost=3,
        lifecycle_state="ACTIVE",
    )
    _replace_pattern_stat(
        db,
        pattern_slug="bull_flag",
        timeframe=15,
        market_regime="all",
        sample_size=40,
        successful_signals=28,
        success_rate=0.7,
        avg_return=0.042,
        avg_drawdown=-0.018,
        temperature=0.76,
    )
    _replace_pattern_stat(
        db,
        pattern_slug="breakout_retest",
        timeframe=15,
        market_regime="bull_trend",
        sample_size=22,
        successful_signals=15,
        success_rate=0.68,
        avg_return=0.036,
        avg_drawdown=-0.021,
        temperature=0.61,
    )

    db.merge(
        DiscoveredPattern(
            structure_hash="cluster:bull_flag:15",
            timeframe=15,
            sample_size=18,
            avg_return=0.031,
            avg_drawdown=-0.017,
            confidence=0.83,
        )
    )
    db.merge(
        MarketCycle(
            coin_id=int(btc.id),
            timeframe=15,
            cycle_phase="markup",
            confidence=0.84,
            detected_at=signal_timestamp,
        )
    )
    db.merge(
        MarketCycle(
            coin_id=int(eth.id),
            timeframe=60,
            cycle_phase="accumulation",
            confidence=0.72,
            detected_at=signal_timestamp,
        )
    )

    _merge_signal(
        db,
        coin_id=int(btc.id),
        timeframe=15,
        signal_type="pattern_bull_flag",
        confidence=0.84,
        priority_score=999.0,
        context_score=1.08,
        regime_alignment=0.97,
        candle_timestamp=signal_timestamp,
        created_at=signal_timestamp,
    )
    _merge_signal(
        db,
        coin_id=int(btc.id),
        timeframe=15,
        signal_type="pattern_cluster_breakout",
        confidence=0.74,
        priority_score=998.0,
        context_score=1.02,
        regime_alignment=0.9,
        candle_timestamp=signal_timestamp,
        created_at=signal_timestamp,
    )
    _merge_signal(
        db,
        coin_id=int(eth.id),
        timeframe=60,
        signal_type="golden_cross",
        confidence=0.79,
        priority_score=997.0,
        context_score=1.01,
        regime_alignment=0.92,
        candle_timestamp=later_signal_timestamp,
        created_at=later_signal_timestamp,
    )

    db.merge(
        SectorMetric(
            sector_id=int(btc_sector.id),
            timeframe=60,
            sector_strength=0.84,
            relative_strength=0.72,
            capital_flow=0.61,
            avg_price_change_24h=4.3,
            avg_volume_change_24h=17.0,
            volatility=0.052,
            trend="up",
            updated_at=signal_timestamp,
        )
    )
    db.merge(
        SectorMetric(
            sector_id=int(eth_sector.id),
            timeframe=60,
            sector_strength=0.66,
            relative_strength=0.51,
            capital_flow=0.43,
            avg_price_change_24h=2.6,
            avg_volume_change_24h=12.0,
            volatility=0.049,
            trend="up",
            updated_at=signal_timestamp,
        )
    )

    btc_closes = [100.0 + index * 1.4 for index in range(40)]
    eth_closes = [50.0 + index * 0.6 for index in range(40)]
    sol_closes = [20.0 + index * 0.2 for index in range(40)]
    _merge_candles(db, coin_id=int(btc.id), timeframe=15, start=candle_start, closes=btc_closes)
    _merge_candles(db, coin_id=int(eth.id), timeframe=15, start=candle_start, closes=eth_closes)
    _merge_candles(db, coin_id=int(sol.id), timeframe=15, start=candle_start, closes=sol_closes)
    _merge_candles(db, coin_id=int(btc.id), timeframe=60, start=candle_start_60, closes=[150.0 + index * 2.0 for index in range(30)])
    _merge_candles(db, coin_id=int(eth.id), timeframe=60, start=candle_start_60, closes=[80.0 + index * 0.8 for index in range(30)])
    _merge_candles(db, coin_id=int(sol.id), timeframe=60, start=candle_start_60, closes=[30.0 + index * 0.3 for index in range(30)])
    _merge_candles(db, coin_id=int(btc.id), timeframe=240, start=candle_start_240, closes=[200.0, 208.0])
    _merge_candles(db, coin_id=int(btc.id), timeframe=1440, start=candle_start_1440, closes=[250.0, 262.0])

    db.commit()
    return {
        "btc": btc,
        "eth": eth,
        "sol": sol,
        "signal_timestamp": signal_timestamp,
        "later_signal_timestamp": later_signal_timestamp,
    }


__all__ = ["seed_pattern_api_state", "seed_pattern_catalog_metadata"]
