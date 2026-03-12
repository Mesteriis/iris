from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.apps.anomalies.detectors import (
    CompressionExpansionDetector,
    CorrelationBreakdownDetector,
    CrossExchangeDislocationDetector,
    FailedBreakoutDetector,
    FundingOpenInterestDetector,
    LiquidationCascadeDetector,
    PriceSpikeDetector,
    PriceVolumeDivergenceDetector,
    RelativeDivergenceDetector,
    VolumeSpikeDetector,
    VolatilityBreakDetector,
)
from app.apps.anomalies.scoring import AnomalyScorer
from app.apps.anomalies.schemas import AnomalyDetectionContext, BenchmarkSeries, DetectorFinding, MarketStructurePoint
from app.apps.market_data.repos import CandlePoint


def _build_candles(
    *,
    closes: list[float],
    volumes: list[float] | None = None,
    wick_multiplier: float = 0.012,
) -> list[CandlePoint]:
    volumes = volumes or [1000.0 for _ in closes]
    start = datetime(2026, 3, 12, 9, 0, tzinfo=timezone.utc)
    candles: list[CandlePoint] = []
    for index, (close, volume) in enumerate(zip(closes, volumes, strict=False)):
        timestamp = start + timedelta(minutes=15 * index)
        high = close * (1 + wick_multiplier)
        low = close * (1 - wick_multiplier)
        candles.append(
            CandlePoint(
                timestamp=timestamp,
                open=closes[index - 1] if index > 0 else close,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
    return candles


def _build_candles_from_returns(
    *,
    start_price: float,
    returns: list[float],
    wick_multiplier: float = 0.012,
    base_volume: float = 1000.0,
) -> list[CandlePoint]:
    closes = [start_price]
    for value in returns:
        closes.append(closes[-1] * (1.0 + value))
    volumes = [base_volume for _ in closes]
    return _build_candles(closes=closes, volumes=volumes, wick_multiplier=wick_multiplier)


def _context(
    *,
    candles: list[CandlePoint],
    benchmark: list[CandlePoint] | None = None,
    sector_peers: dict[str, list[CandlePoint]] | None = None,
    related_peers: dict[str, list[CandlePoint]] | None = None,
    venue_snapshots: dict[str, list[MarketStructurePoint]] | None = None,
) -> AnomalyDetectionContext:
    return AnomalyDetectionContext(
        coin_id=7,
        symbol="RNDR",
        timeframe=15,
        timestamp=candles[-1].timestamp,
        candles=candles,
        market_regime="bull_trend",
        sector="ai",
        portfolio_relevant=False,
        benchmark=BenchmarkSeries(symbol="BTCUSD", candles=benchmark) if benchmark is not None else None,
        sector_peer_candles=sector_peers or {},
        related_peer_candles=related_peers or {},
        venue_snapshots=venue_snapshots or {},
    )


def _structure_series(
    *,
    venue: str,
    timestamps: list[datetime],
    last_prices: list[float],
    funding_rates: list[float] | None = None,
    open_interests: list[float] | None = None,
    basis_values: list[float] | None = None,
    liquidations_long: list[float] | None = None,
    liquidations_short: list[float] | None = None,
) -> list[MarketStructurePoint]:
    funding_rates = funding_rates or [0.0 for _ in timestamps]
    open_interests = open_interests or [0.0 for _ in timestamps]
    basis_values = basis_values or [0.0 for _ in timestamps]
    liquidations_long = liquidations_long or [0.0 for _ in timestamps]
    liquidations_short = liquidations_short or [0.0 for _ in timestamps]
    return [
        MarketStructurePoint(
            venue=venue,
            timestamp=timestamp,
            last_price=last_price,
            mark_price=last_price * (1.0 + basis),
            index_price=last_price,
            funding_rate=funding,
            open_interest=open_interest,
            basis=basis,
            liquidations_long=liq_long,
            liquidations_short=liq_short,
            volume=1000.0,
        )
        for timestamp, last_price, funding, open_interest, basis, liq_long, liq_short in zip(
            timestamps,
            last_prices,
            funding_rates,
            open_interests,
            basis_values,
            liquidations_long,
            liquidations_short,
            strict=False,
        )
    ]


def test_price_anomaly_detector_detects_large_displacement() -> None:
    closes = [100.0 + (index * 0.25) for index in range(40)] + [118.0]
    volumes = [1000.0 for _ in range(40)] + [6400.0]
    candles = _build_candles(closes=closes, volumes=volumes, wick_multiplier=0.025)

    finding = PriceSpikeDetector().detect(_context(candles=candles))

    assert finding is not None
    assert finding.component_scores["price"] > 0.7
    assert finding.metrics["return_zscore"] > 3.0
    assert finding.metrics["atr_ratio"] > 2.0


def test_volume_anomaly_detector_detects_abnormal_participation() -> None:
    closes = [50.0 + (index * 0.1) for index in range(41)]
    volumes = [900.0 + (index * 5.0) for index in range(40)] + [9800.0]
    candles = _build_candles(closes=closes, volumes=volumes)

    finding = VolumeSpikeDetector().detect(_context(candles=candles))

    assert finding is not None
    assert finding.component_scores["volume"] > 0.7
    assert finding.metrics["volume_ratio"] > 5.0
    assert finding.metrics["volume_zscore"] > 3.0


def test_failed_breakout_detector_detects_rejection_after_local_break() -> None:
    closes = [100.0 + (index * 0.16) for index in range(30)]
    volumes = [950.0 + (index * 8.0) for index in range(30)]
    candles = _build_candles(closes=closes, volumes=volumes, wick_multiplier=0.004)
    latest = candles[-1]
    candles.append(
        CandlePoint(
            timestamp=latest.timestamp + timedelta(minutes=15),
            open=float(latest.close) * 1.001,
            high=float(latest.close) * 1.035,
            low=float(latest.close) * 0.997,
            close=float(latest.close) * 0.998,
            volume=3600.0,
        )
    )

    finding = FailedBreakoutDetector().detect(_context(candles=candles))

    assert finding is not None
    assert finding.component_scores["price"] > 0.55
    assert finding.metrics["breakout_excursion"] > 0.02
    assert finding.metrics["rejection_depth"] > 0.001


def test_volatility_break_detector_detects_regime_shift() -> None:
    closes = [200.0]
    for _ in range(34):
        closes.append(closes[-1] * 1.001)
    closes.extend(
        [
            closes[-1] * 1.035,
            closes[-1] * 0.972,
            closes[-1] * 1.028,
            closes[-1] * 0.965,
            closes[-1] * 1.024,
        ]
    )
    candles = _build_candles(closes=closes, wick_multiplier=0.03)

    finding = VolatilityBreakDetector().detect(_context(candles=candles))

    assert finding is not None
    assert finding.component_scores["volatility"] > 0.55
    assert finding.metrics["rolling_volatility_ratio"] > 2.0
    assert finding.confirmation_hits >= 2


def test_compression_expansion_detector_detects_squeeze_release() -> None:
    closes = [200.0]
    for index in range(24):
        closes.append(closes[-1] * (1.0009 if index % 2 == 0 else 0.9992))
    for index in range(8):
        closes.append(closes[-1] * (1.00012 if index % 2 == 0 else 0.99992))
    candles = _build_candles(closes=closes, wick_multiplier=0.0015)
    latest = candles[-1]
    candles.append(
        CandlePoint(
            timestamp=latest.timestamp + timedelta(minutes=15),
            open=float(latest.close),
            high=float(latest.close) * 1.042,
            low=float(latest.close) * 0.998,
            close=float(latest.close) * 1.031,
            volume=1400.0,
        )
    )

    finding = CompressionExpansionDetector().detect(_context(candles=candles))

    assert finding is not None
    assert finding.component_scores["volatility"] > 0.55
    assert finding.metrics["compression_ratio"] < 0.5
    assert finding.metrics["range_expansion_ratio"] > 2.0


def test_relative_divergence_detector_detects_beta_adjusted_decoupling() -> None:
    asset_closes = [100.0]
    benchmark_closes = [100.0]
    for _ in range(38):
        asset_closes.append(asset_closes[-1] * 1.002)
        benchmark_closes.append(benchmark_closes[-1] * 1.0015)
    asset_closes.extend([asset_closes[-1] * 1.004, asset_closes[-1] * 1.071])
    benchmark_closes.extend([benchmark_closes[-1] * 1.002, benchmark_closes[-1] * 1.004])

    asset = _build_candles(closes=asset_closes)
    benchmark = _build_candles(closes=benchmark_closes)
    peers = {
        "FET": _build_candles(closes=[90.0 + (index * 0.12) for index in range(len(asset_closes))]),
        "TAO": _build_candles(closes=[80.0 + (index * 0.08) for index in range(len(asset_closes))]),
    }

    finding = RelativeDivergenceDetector().detect(_context(candles=asset, benchmark=benchmark, sector_peers=peers))

    assert finding is not None
    assert finding.component_scores["relative"] > 0.5
    assert finding.metrics["beta_adjusted_deviation"] > 0.03
    assert finding.explainability["relative_to_btc"] == "outperform"


def test_price_volume_divergence_detector_detects_price_without_volume_confirmation() -> None:
    closes = [50.0 + (index * 0.09) for index in range(40)] + [54.8]
    volumes = [980.0 + (index * 4.0) for index in range(40)] + [1080.0]
    candles = _build_candles(closes=closes, volumes=volumes, wick_multiplier=0.01)

    finding = PriceVolumeDivergenceDetector().detect(_context(candles=candles))

    assert finding is not None
    assert finding.component_scores["price"] > 0.5
    assert finding.metrics["price_return_zscore"] > 3.0
    assert finding.metrics["volume_ratio"] < 1.3


def test_correlation_breakdown_detector_detects_decoupling_from_benchmark() -> None:
    baseline_returns = [0.0020, -0.0010, 0.0016, -0.0008] * 8
    recent_benchmark = [0.0011, 0.0009, 0.0012, 0.0010, 0.0008, 0.0013]
    recent_asset = [-0.0042, 0.0036, -0.0045, 0.0034, -0.0048, 0.0039]

    asset = _build_candles_from_returns(start_price=100.0, returns=baseline_returns + recent_asset)
    benchmark = _build_candles_from_returns(start_price=100.0, returns=baseline_returns + recent_benchmark)
    peers = {
        "FET": _build_candles_from_returns(
            start_price=90.0,
            returns=baseline_returns + [0.0012, 0.0010, 0.0008, 0.0011, 0.0010, 0.0012],
        ),
        "TAO": _build_candles_from_returns(
            start_price=80.0,
            returns=baseline_returns + [0.0010, 0.0011, 0.0010, 0.0012, 0.0009, 0.0011],
        ),
    }

    finding = CorrelationBreakdownDetector().detect(_context(candles=asset, benchmark=benchmark, sector_peers=peers))

    assert finding is not None
    assert finding.component_scores["relative"] > 0.45
    assert finding.metrics["correlation_drop"] > 0.6
    assert finding.confirmation_hits >= 2


def test_funding_open_interest_detector_detects_leveraged_positioning_shift() -> None:
    candles = _build_candles(closes=[100.0 + (index * 0.2) for index in range(40)] + [103.6], wick_multiplier=0.012)
    timestamps = [candle.timestamp for candle in candles[-18:]]
    venue_snapshots = {
        "binance": _structure_series(
            venue="binance",
            timestamps=timestamps,
            last_prices=[float(candle.close) for candle in candles[-18:]],
            funding_rates=[0.00008 for _ in range(17)] + [0.00125],
            open_interests=[15000.0 + (index * 140.0) for index in range(17)] + [23800.0],
            basis_values=[0.0003 for _ in range(17)] + [0.0048],
        ),
        "bybit": _structure_series(
            venue="bybit",
            timestamps=timestamps,
            last_prices=[float(candle.close) * 1.0005 for candle in candles[-18:]],
            funding_rates=[0.00009 for _ in range(17)] + [0.00110],
            open_interests=[14800.0 + (index * 120.0) for index in range(17)] + [23000.0],
            basis_values=[0.0004 for _ in range(17)] + [0.0043],
        ),
    }

    finding = FundingOpenInterestDetector().detect(_context(candles=candles, venue_snapshots=venue_snapshots))

    assert finding is not None
    assert finding.component_scores["derivatives"] > 0.5
    assert finding.metrics["funding_zscore"] > 3.0
    assert finding.metrics["open_interest_ratio"] > 1.3


def test_cross_exchange_dislocation_detector_detects_venue_spread() -> None:
    candles = _build_candles(closes=[100.0 + (index * 0.15) for index in range(36)], wick_multiplier=0.01)
    timestamps = [candle.timestamp for candle in candles[-12:]]
    base_prices = [float(candle.close) for candle in candles[-12:]]
    venue_snapshots = {
        "binance": _structure_series(
            venue="binance",
            timestamps=timestamps,
            last_prices=base_prices[:-1] + [base_prices[-1] * 1.022],
            basis_values=[0.0005 for _ in range(11)] + [0.0065],
        ),
        "bybit": _structure_series(
            venue="bybit",
            timestamps=timestamps,
            last_prices=[price * 1.0004 for price in base_prices[:-1]] + [base_prices[-1] * 0.989],
            basis_values=[0.0004 for _ in range(11)] + [-0.0045],
        ),
        "okx": _structure_series(
            venue="okx",
            timestamps=timestamps,
            last_prices=[price * 0.9998 for price in base_prices[:-1]] + [base_prices[-1] * 1.004],
            basis_values=[0.0003 for _ in range(11)] + [0.0012],
        ),
    }

    finding = CrossExchangeDislocationDetector().detect(_context(candles=candles, venue_snapshots=venue_snapshots))

    assert finding is not None
    assert finding.component_scores["liquidity"] > 0.45
    assert finding.metrics["venue_spread_pct"] > 0.02
    assert finding.metrics["venue_spread_zscore"] > 2.0


def test_liquidation_cascade_detector_detects_forced_unwind() -> None:
    closes = [100.0]
    for index in range(38):
        closes.append(closes[-1] * (1.001 if index % 2 == 0 else 0.9995))
    closes.extend([closes[-1] * 0.998, closes[-1] * 0.944])
    candles = _build_candles(closes=closes, wick_multiplier=0.015)
    timestamps = [candle.timestamp for candle in candles[-16:]]
    venue_snapshots = {
        "binance": _structure_series(
            venue="binance",
            timestamps=timestamps,
            last_prices=[float(candle.close) for candle in candles[-16:]],
            open_interests=[22000.0 for _ in range(15)] + [18200.0],
            liquidations_long=[120.0 for _ in range(15)] + [6200.0],
            liquidations_short=[80.0 for _ in range(15)] + [220.0],
        ),
        "bybit": _structure_series(
            venue="bybit",
            timestamps=timestamps,
            last_prices=[float(candle.close) * 1.0003 for candle in candles[-16:]],
            open_interests=[21000.0 for _ in range(15)] + [17150.0],
            liquidations_long=[100.0 for _ in range(15)] + [5400.0],
            liquidations_short=[75.0 for _ in range(15)] + [210.0],
        ),
    }

    finding = LiquidationCascadeDetector().detect(_context(candles=candles, venue_snapshots=venue_snapshots))

    assert finding is not None
    assert finding.component_scores["liquidity"] > 0.5
    assert finding.metrics["liquidation_zscore"] > 3.0
    assert finding.metrics["open_interest_drop_ratio"] > 0.1
    assert finding.confirmation_target == 2


def test_anomaly_scorer_maps_weighted_score_to_severity() -> None:
    finding = DetectorFinding(
        anomaly_type="synthetic",
        summary="Synthetic anomaly",
        component_scores={
            "price": 1.0,
            "volume": 0.98,
            "volatility": 0.95,
            "relative": 0.92,
            "synchronicity": 0.90,
        },
        metrics={},
        confidence=0.95,
    )

    score, severity, confidence = AnomalyScorer().score(finding)

    assert score > 0.8
    assert severity == "critical"
    assert confidence > 0.8
