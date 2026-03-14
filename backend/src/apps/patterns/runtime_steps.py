from __future__ import annotations

from src.apps.market_data.domain import utc_now
from src.apps.patterns.engines import PatternCycleEngineInput, compute_pattern_market_cycle
from src.apps.patterns.query_services import PatternQueryService
from src.apps.patterns.repositories import PatternMarketCycleRepository
from src.apps.patterns.runtime_results import PatternMarketCycleUpdateResult
from src.core.db.uow import BaseAsyncUnitOfWork


async def update_market_cycle_step(
    *,
    queries: PatternQueryService,
    cycles: PatternMarketCycleRepository,
    uow: BaseAsyncUnitOfWork,
    coin_id: int,
    timeframe: int,
) -> PatternMarketCycleUpdateResult:
    metrics = await queries.get_coin_metrics_snapshot(coin_id=int(coin_id), timeframe=int(timeframe))
    if metrics is None:
        return PatternMarketCycleUpdateResult(
            status="skipped",
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            reason="coin_metrics_not_found",
        )
    pattern_density = await queries.count_pattern_signals(
        coin_id=int(coin_id),
        timeframe=int(timeframe),
    )
    cluster_frequency = await queries.count_cluster_signals(
        coin_id=int(coin_id),
        timeframe=int(timeframe),
    )
    sector_metric = await queries.get_sector_metric_snapshot(
        coin_id=int(coin_id),
        timeframe=int(timeframe),
    )
    cycle = compute_pattern_market_cycle(
        PatternCycleEngineInput(
            trend_score=metrics.trend_score,
            regime=metrics.resolved_regime,
            volatility=metrics.volatility,
            price_current=metrics.price_current,
            pattern_density=pattern_density,
            cluster_frequency=cluster_frequency,
            sector_strength=sector_metric.sector_strength if sector_metric is not None else None,
            capital_flow=sector_metric.capital_flow if sector_metric is not None else None,
        )
    )
    await cycles.upsert(
        coin_id=int(coin_id),
        timeframe=int(timeframe),
        cycle_phase=cycle.cycle_phase,
        confidence=cycle.confidence,
        detected_at=utc_now(),
    )
    await uow.flush()
    return PatternMarketCycleUpdateResult(
        status="ok",
        coin_id=int(coin_id),
        timeframe=int(timeframe),
        cycle_phase=cycle.cycle_phase,
        confidence=cycle.confidence,
    )


__all__ = ["update_market_cycle_step"]
