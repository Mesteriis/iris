from typing import TYPE_CHECKING

from iris.apps.cross_market.engines import CrossMarketSectorMomentumAggregateInput, build_sector_momentum
from iris.apps.cross_market.services.results import CrossMarketSectorMomentumResult
from iris.apps.cross_market.services.side_effects import CrossMarketSectorRotationSideEffect
from iris.apps.market_data.domain import utc_now

if TYPE_CHECKING:
    from iris.apps.cross_market.services.cross_market_service import CrossMarketService


async def refresh_sector_momentum(
    *,
    service: CrossMarketService,
    timeframe: int,
    emit_events: bool,
) -> tuple[CrossMarketSectorMomentumResult, CrossMarketSectorRotationSideEffect | None]:
    service._log_debug(
        "service.refresh_sector_momentum",
        mode="write",
        timeframe=timeframe,
        emit_events=emit_events,
    )
    previous_top = await service._queries.get_top_sector(timeframe=timeframe)
    aggregates = await service._queries.list_sector_momentum_aggregates()
    if not aggregates:
        return CrossMarketSectorMomentumResult(status="skipped", reason="sector_rows_not_found"), None

    engine_result = build_sector_momentum(
        aggregates=tuple(
            CrossMarketSectorMomentumAggregateInput(
                sector_id=item.sector_id,
                sector_name=item.sector_name,
                avg_price_change_24h=item.avg_price_change_24h,
                avg_volume_change_24h=item.avg_volume_change_24h,
                avg_volatility=item.avg_volatility,
                capital_flow=item.capital_flow,
            )
            for item in aggregates
        ),
        timeframe=int(timeframe),
    )
    updated_at = utc_now()
    rows = [
        {
            "sector_id": item.sector_id,
            "timeframe": item.timeframe,
            "sector_strength": item.sector_strength,
            "relative_strength": item.relative_strength,
            "capital_flow": item.capital_flow,
            "avg_price_change_24h": item.avg_price_change_24h,
            "avg_volume_change_24h": item.avg_volume_change_24h,
            "volatility": item.volatility,
            "trend": item.trend,
            "updated_at": updated_at,
        }
        for item in engine_result.rows
    ]
    await service._sectors.upsert_many(rows)

    sector_effect: CrossMarketSectorRotationSideEffect | None = None
    if (
        emit_events
        and previous_top is not None
        and engine_result.top_sector is not None
        and previous_top.sector_id != engine_result.top_sector.sector_id
    ):
        sector_effect = CrossMarketSectorRotationSideEffect(
            timeframe=int(timeframe),
            source_sector=previous_top.sector_name,
            target_sector=engine_result.top_sector.sector_name,
            source_strength=previous_top.relative_strength,
            target_strength=engine_result.top_sector.relative_strength,
            timestamp=utc_now(),
        )

    result = CrossMarketSectorMomentumResult(status="ok", updated=len(rows), timeframe=int(timeframe))
    service._log_info("service.refresh_sector_momentum.result", mode="write", timeframe=timeframe, updated=len(rows))
    return result, sector_effect
