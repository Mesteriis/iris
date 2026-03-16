import asyncio
import json
from contextlib import asynccontextmanager
from datetime import timedelta

import pytest
from _pytest.fixtures import FixtureLookupError
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from src.apps.cross_market.models import CoinRelation, SectorMetric
from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.models import Coin
from src.apps.patterns.models import DiscoveredPattern, MarketCycle, PatternFeature, PatternRegistry, PatternStatistic
from src.apps.portfolio.models import ExchangeAccount, PortfolioAction, PortfolioPosition, PortfolioState
from src.apps.predictions.models import MarketPrediction, PredictionResult
from src.apps.signals.models import FinalSignal, InvestmentDecision, MarketDecision, RiskMetric, Signal, SignalHistory, Strategy, StrategyPerformance, StrategyRule
from src.apps.system.schemas import SourceStatusRead
from src.core.bootstrap.app import create_app
from src.core.settings import get_settings
from tests.cross_market_support import DEFAULT_START
from tests.factories.base import json_utc
from tests.factories.seeds import DecisionSeedFactory, MetricSeedFactory, NarrativeSeedFactory, SectorSeedFactory, SignalSeedFactory, StrategySeedFactory
from tests.portfolio_support import create_exchange_account, create_sector

API_PREFIX = "/api/v1"


def api_path(path: str) -> str:
    if path == "/status":
        return f"{API_PREFIX}/system/status"
    if path == "/health":
        return f"{API_PREFIX}/system/health"
    if path.startswith(API_PREFIX):
        return path
    if path.startswith("/"):
        return f"{API_PREFIX}{path}"
    return f"{API_PREFIX}/{path}"


class PrefixedAsyncClient:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def get(self, url: str, *args, **kwargs):
        return await self._client.get(api_path(url), *args, **kwargs)

    async def post(self, url: str, *args, **kwargs):
        return await self._client.post(api_path(url), *args, **kwargs)

    async def put(self, url: str, *args, **kwargs):
        return await self._client.put(api_path(url), *args, **kwargs)

    async def patch(self, url: str, *args, **kwargs):
        return await self._client.patch(api_path(url), *args, **kwargs)

    async def delete(self, url: str, *args, **kwargs):
        return await self._client.delete(api_path(url), *args, **kwargs)

    async def request(self, method: str, url: str, *args, **kwargs):
        return await self._client.request(method, api_path(url), *args, **kwargs)

    def stream(self, method: str, url: str, *args, **kwargs):
        return self._client.stream(method, api_path(url), *args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._client, name)


class AliveProcess:
    def __init__(self, *, alive: bool) -> None:
        self._alive = alive

    def is_alive(self) -> bool:
        return self._alive


@pytest.fixture(autouse=True)
def cleanup_app_static_rows(request) -> None:
    try:
        db_session = request.getfixturevalue("db_session")
    except FixtureLookupError:
        return
    db_session.execute(delete(StrategyPerformance))
    db_session.execute(delete(StrategyRule))
    db_session.execute(delete(Strategy))
    db_session.execute(delete(DiscoveredPattern))
    db_session.commit()


@pytest.fixture
async def api_app_client():
    app = create_app()

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    app.router.lifespan_context = _noop_lifespan
    app.state.taskiq_backfill_event = asyncio.Event()
    app.state.taskiq_worker_processes = []

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield app, PrefixedAsyncClient(client)


@pytest.fixture
def seeded_api_state(db_session, seeded_market, redis_client, settings):
    btc = db_session.scalar(select(Coin).where(Coin.symbol == "BTCUSD_EVT").limit(1))
    eth = db_session.scalar(select(Coin).where(Coin.symbol == "ETHUSD_EVT").limit(1))
    sol = db_session.scalar(select(Coin).where(Coin.symbol == "SOLUSD_EVT").limit(1))
    assert btc is not None and eth is not None and sol is not None

    btc_sector_seed = SectorSeedFactory.build(name="store_of_value")
    eth_sector_seed = SectorSeedFactory.build(name="smart_contract")
    sol_sector_seed = SectorSeedFactory.build(name="high_beta")
    btc_sector = create_sector(db_session, name=btc_sector_seed.name, description=btc_sector_seed.description)
    eth_sector = create_sector(db_session, name=eth_sector_seed.name, description=eth_sector_seed.description)
    sol_sector = create_sector(db_session, name=sol_sector_seed.name, description=sol_sector_seed.description)
    btc.sector_id = int(btc_sector.id)
    btc.sector_code = btc_sector.name
    eth.sector_id = int(eth_sector.id)
    eth.sector_code = eth_sector.name
    sol.sector_id = int(sol_sector.id)
    sol.sector_code = sol_sector.name

    signal_timestamp = DEFAULT_START + timedelta(days=2, hours=4)
    later_signal_timestamp = signal_timestamp + timedelta(hours=1)

    metric_specs = {
        int(btc.id): MetricSeedFactory.build(
            regime="bull_trend",
            activity_bucket="HOT",
            activity_score=95.0,
            analysis_priority=1,
            price_current=112_000.0,
            price_change_24h=6.2,
            price_change_7d=12.4,
            volume_change_24h=21.0,
            volatility=0.055,
            market_cap=900_000_000_000.0,
            last_analysis_at=signal_timestamp,
        ),
        int(eth.id): MetricSeedFactory.build(
            regime="sideways_range",
            activity_bucket="WARM",
            activity_score=82.0,
            analysis_priority=2,
            price_current=4_500.0,
            price_change_24h=3.1,
            price_change_7d=7.4,
            volume_change_24h=14.0,
            volatility=0.048,
            market_cap=350_000_000_000.0,
            last_analysis_at=signal_timestamp,
        ),
        int(sol.id): MetricSeedFactory.build(
            regime="high_volatility",
            activity_bucket="COLD",
            activity_score=68.0,
            analysis_priority=3,
            price_current=220.0,
            price_change_24h=-1.4,
            price_change_7d=2.2,
            volume_change_24h=6.0,
            volatility=0.083,
            market_cap=95_000_000_000.0,
            last_analysis_at=signal_timestamp,
        ),
    }

    for coin in (btc, eth, sol):
        metrics = db_session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == int(coin.id)).limit(1))
        assert metrics is not None
        spec = metric_specs[int(coin.id)]
        details = {
            "15": {"regime": spec.regime, "confidence": 0.81},
            "60": {"regime": spec.regime, "confidence": 0.79},
        }
        metrics.price_current = spec.price_current
        metrics.price_change_1h = 1.2
        metrics.price_change_24h = spec.price_change_24h
        metrics.price_change_7d = spec.price_change_7d
        metrics.ema_20 = spec.price_current * 0.98
        metrics.ema_50 = spec.price_current * 0.96
        metrics.sma_50 = spec.price_current * 0.95
        metrics.sma_200 = spec.price_current * 0.9
        metrics.rsi_14 = 62.0
        metrics.macd = 1.4
        metrics.macd_signal = 1.1
        metrics.macd_histogram = 0.3
        metrics.atr_14 = 2.4
        metrics.bb_upper = spec.price_current * 1.05
        metrics.bb_middle = spec.price_current
        metrics.bb_lower = spec.price_current * 0.95
        metrics.bb_width = 0.06
        metrics.adx_14 = 29.0
        metrics.volume_24h = 5_000_000.0
        metrics.volume_change_24h = spec.volume_change_24h
        metrics.volatility = spec.volatility
        metrics.market_cap = spec.market_cap
        metrics.trend = spec.trend
        metrics.trend_score = spec.trend_score
        metrics.activity_score = spec.activity_score
        metrics.activity_bucket = spec.activity_bucket
        metrics.analysis_priority = spec.analysis_priority
        metrics.last_analysis_at = spec.last_analysis_at
        metrics.market_regime = spec.regime
        metrics.market_regime_details = details
        metrics.indicator_version = 1

    bullish_signal = SignalSeedFactory.build(
        signal_type="pattern_bull_flag",
        confidence=0.84,
        priority_score=999.0,
        context_score=1.08,
        regime_alignment=0.97,
        candle_timestamp=signal_timestamp,
        created_at=signal_timestamp,
    )
    cluster_signal = SignalSeedFactory.build(
        signal_type="pattern_cluster_breakout",
        confidence=0.74,
        priority_score=998.0,
        context_score=1.02,
        regime_alignment=0.9,
        candle_timestamp=signal_timestamp,
        created_at=signal_timestamp,
    )
    cross_signal = SignalSeedFactory.build(
        signal_type="golden_cross",
        confidence=0.79,
        priority_score=997.0,
        context_score=1.01,
        regime_alignment=0.92,
        candle_timestamp=later_signal_timestamp,
        created_at=later_signal_timestamp,
    )
    investment_decision_seed = DecisionSeedFactory.build(decision="BUY", confidence=0.82, created_at=signal_timestamp)
    market_decision_seed = DecisionSeedFactory.build(decision="BUY", confidence=0.998, created_at=signal_timestamp)
    hold_decision_seed = DecisionSeedFactory.build(decision="HOLD", confidence=0.61, created_at=later_signal_timestamp)
    final_signal_reason = NarrativeSeedFactory.build(
        reason="Aligned trend and acceptable risk",
        created_at=signal_timestamp,
    )
    decision_reason = NarrativeSeedFactory.build(
        reason="Bullish pattern stack",
        created_at=signal_timestamp,
    )
    strategy_seed = StrategySeedFactory.build(
        name="Momentum Breakout",
        description="Pattern-led continuation entries",
        created_at=signal_timestamp,
    )

    db_session.add_all(
        [
            PatternFeature(feature_slug="market_regime_engine", enabled=True),
            PatternFeature(feature_slug="pattern_context_engine", enabled=True),
            PatternRegistry(slug="bull_flag", category="continuation", enabled=True, cpu_cost=2, lifecycle_state="ACTIVE"),
            PatternRegistry(slug="breakout_retest", category="structural", enabled=True, cpu_cost=3, lifecycle_state="ACTIVE"),
            PatternStatistic(
                pattern_slug="bull_flag",
                timeframe=15,
                market_regime="all",
                sample_size=40,
                total_signals=40,
                successful_signals=28,
                success_rate=0.7,
                avg_return=0.042,
                avg_drawdown=-0.018,
                temperature=0.76,
                enabled=True,
            ),
            PatternStatistic(
                pattern_slug="breakout_retest",
                timeframe=15,
                market_regime="bull_trend",
                sample_size=22,
                total_signals=22,
                successful_signals=15,
                success_rate=0.68,
                avg_return=0.036,
                avg_drawdown=-0.021,
                temperature=0.61,
                enabled=True,
            ),
            DiscoveredPattern(
                structure_hash="cluster:bull_flag:15",
                timeframe=15,
                sample_size=18,
                avg_return=0.031,
                avg_drawdown=-0.017,
                confidence=0.83,
            ),
            MarketCycle(
                coin_id=int(btc.id),
                timeframe=15,
                cycle_phase="markup",
                confidence=0.84,
                detected_at=signal_timestamp,
            ),
            MarketCycle(
                coin_id=int(eth.id),
                timeframe=60,
                cycle_phase="accumulation",
                confidence=0.72,
                detected_at=signal_timestamp,
            ),
            Signal(coin_id=int(btc.id), timeframe=15, **bullish_signal.__dict__),
            Signal(coin_id=int(btc.id), timeframe=15, **cluster_signal.__dict__),
            Signal(coin_id=int(eth.id), timeframe=60, **cross_signal.__dict__),
            InvestmentDecision(
                coin_id=int(btc.id),
                timeframe=15,
                decision=investment_decision_seed.decision,
                confidence=investment_decision_seed.confidence,
                score=99.1,
                reason=decision_reason.reason,
                created_at=investment_decision_seed.created_at,
            ),
            MarketDecision(
                coin_id=int(btc.id),
                timeframe=15,
                decision=market_decision_seed.decision,
                confidence=market_decision_seed.confidence,
                signal_count=3,
                created_at=market_decision_seed.created_at,
            ),
            MarketDecision(
                coin_id=int(eth.id),
                timeframe=60,
                decision=hold_decision_seed.decision,
                confidence=hold_decision_seed.confidence,
                signal_count=2,
                created_at=hold_decision_seed.created_at,
            ),
            RiskMetric(
                coin_id=int(btc.id),
                timeframe=15,
                liquidity_score=0.87,
                slippage_risk=0.09,
                volatility_risk=0.18,
            ),
            FinalSignal(
                coin_id=int(btc.id),
                timeframe=15,
                decision="BUY",
                confidence=0.77,
                risk_adjusted_score=99.69,
                reason=final_signal_reason.reason,
                created_at=signal_timestamp,
            ),
            SignalHistory(
                coin_id=int(btc.id),
                timeframe=15,
                signal_type="pattern_bull_flag",
                confidence=0.83,
                market_regime="bull_trend",
                candle_timestamp=signal_timestamp - timedelta(hours=8),
                result_return=0.041,
                result_drawdown=-0.013,
                profit_after_24h=0.019,
                profit_after_72h=0.041,
                maximum_drawdown=-0.013,
                evaluated_at=signal_timestamp - timedelta(hours=5),
            ),
            SignalHistory(
                coin_id=int(btc.id),
                timeframe=15,
                signal_type="pattern_bull_flag",
                confidence=0.81,
                market_regime="bull_trend",
                candle_timestamp=signal_timestamp - timedelta(hours=32),
                result_return=-0.012,
                result_drawdown=-0.021,
                profit_after_24h=-0.006,
                profit_after_72h=-0.012,
                maximum_drawdown=-0.021,
                evaluated_at=signal_timestamp - timedelta(hours=28),
            ),
            CoinRelation(
                leader_coin_id=int(btc.id),
                follower_coin_id=int(eth.id),
                correlation=0.86,
                lag_hours=4,
                confidence=0.79,
                updated_at=signal_timestamp,
            ),
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
            ),
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
            ),
            PortfolioState(
                id=1,
                total_capital=100_000.0,
                allocated_capital=3_200.0,
                available_capital=96_800.0,
                updated_at=signal_timestamp,
            ),
            MarketPrediction(
                prediction_type="cross_market_follow_through",
                leader_coin_id=int(btc.id),
                target_coin_id=int(eth.id),
                prediction_event="leader_breakout",
                expected_move="up",
                lag_hours=4,
                confidence=0.74,
                created_at=signal_timestamp,
                evaluation_time=signal_timestamp + timedelta(hours=4),
                status="confirmed",
            ),
            Strategy(
                id=101,
                name=strategy_seed.name,
                description=strategy_seed.description,
                enabled=True,
                created_at=strategy_seed.created_at,
            ),
        ]
    )
    db_session.commit()

    account = create_exchange_account(db_session, exchange_name="binance", account_name="swing")
    market_decision = db_session.scalar(
        select(MarketDecision)
        .where(MarketDecision.coin_id == int(btc.id), MarketDecision.timeframe == 15)
        .limit(1)
    )
    prediction = db_session.scalar(select(MarketPrediction).order_by(MarketPrediction.id.desc()).limit(1))
    assert market_decision is not None and prediction is not None

    db_session.add_all(
        [
            PortfolioPosition(
                coin_id=int(btc.id),
                exchange_account_id=int(account.id),
                source_exchange=account.exchange_name,
                position_type="spot",
                timeframe=15,
                entry_price=100_000.0,
                position_size=0.032,
                position_value=3_200.0,
                stop_loss=95_000.0,
                take_profit=110_000.0,
                status="open",
                opened_at=signal_timestamp - timedelta(hours=6),
            ),
            PortfolioAction(
                coin_id=int(btc.id),
                action="OPEN_POSITION",
                size=0.032,
                confidence=0.78,
                decision_id=int(market_decision.id),
                created_at=signal_timestamp,
            ),
            PredictionResult(
                prediction_id=int(prediction.id),
                actual_move=0.046,
                success=True,
                profit=0.046,
                evaluated_at=signal_timestamp + timedelta(hours=4),
            ),
            StrategyRule(
                strategy_id=101,
                pattern_slug="bull_flag",
                regime="bull_trend",
                sector="store_of_value",
                cycle="markup",
                min_confidence=0.7,
            ),
            StrategyPerformance(
                strategy_id=101,
                sample_size=18,
                win_rate=0.67,
                avg_return=0.031,
                sharpe_ratio=1.48,
                max_drawdown=-0.09,
                updated_at=signal_timestamp,
            ),
        ]
    )
    db_session.commit()

    redis_client.xadd(
        settings.event_stream_name,
        {
            "event_type": "market_regime_changed",
            "coin_id": str(btc.id),
            "timeframe": "60",
            "timestamp": signal_timestamp.isoformat(),
            "payload": json.dumps({"regime": "bull_trend", "confidence": 0.83}),
        },
    )
    redis_client.xadd(
        settings.event_stream_name,
        {
            "event_type": "market_leader_detected",
            "coin_id": str(btc.id),
            "timeframe": "60",
            "timestamp": signal_timestamp.isoformat(),
            "payload": json.dumps({"confidence": 0.88}),
        },
    )
    redis_client.xadd(
        settings.event_stream_name,
        {
            "event_type": "sector_rotation_detected",
            "coin_id": str(btc.id),
            "timeframe": "60",
            "timestamp": signal_timestamp.isoformat(),
            "payload": json.dumps({"source_sector": "store_of_value", "target_sector": "smart_contract"}),
        },
    )

    return {
        "btc": btc,
        "eth": eth,
        "sol": sol,
        "signal_timestamp": signal_timestamp,
    }


__all__ = ["AliveProcess", "SourceStatusRead", "api_app_client", "json_utc", "seeded_api_state", "get_settings"]
