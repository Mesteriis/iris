from iris.apps.cross_market.engines.contracts import (
    CrossMarketSectorMomentumAggregateInput,
    CrossMarketSectorMomentumEngineResult,
    CrossMarketSectorMomentumRow,
    CrossMarketTopSectorResult,
)


def build_sector_momentum(
    *,
    aggregates: tuple[CrossMarketSectorMomentumAggregateInput, ...],
    timeframe: int,
) -> CrossMarketSectorMomentumEngineResult:
    if not aggregates:
        return CrossMarketSectorMomentumEngineResult(rows=(), top_sector=None)

    market_average = sum(item.avg_price_change_24h for item in aggregates) / len(aggregates)
    rows: list[CrossMarketSectorMomentumRow] = []
    top_sector: CrossMarketTopSectorResult | None = None
    for item in aggregates:
        trend = "sideways"
        if item.avg_price_change_24h >= 1 and item.avg_volume_change_24h >= 0:
            trend = "bullish"
        elif item.avg_price_change_24h <= -1:
            trend = "bearish"
        relative_strength = item.avg_price_change_24h - market_average
        rows.append(
            CrossMarketSectorMomentumRow(
                sector_id=int(item.sector_id),
                timeframe=int(timeframe),
                sector_strength=float(item.avg_price_change_24h),
                relative_strength=float(relative_strength),
                capital_flow=float(item.capital_flow),
                avg_price_change_24h=float(item.avg_price_change_24h),
                avg_volume_change_24h=float(item.avg_volume_change_24h),
                volatility=float(item.avg_volatility),
                trend=trend,
            )
        )
        candidate = CrossMarketTopSectorResult(
            sector_id=int(item.sector_id),
            sector_name=item.sector_name,
            relative_strength=float(relative_strength),
        )
        if top_sector is None or (
            candidate.relative_strength > top_sector.relative_strength
            or (
                candidate.relative_strength == top_sector.relative_strength
                and candidate.sector_name < top_sector.sector_name
            )
        ):
            top_sector = candidate
    return CrossMarketSectorMomentumEngineResult(rows=tuple(rows), top_sector=top_sector)


__all__ = ["build_sector_momentum"]
