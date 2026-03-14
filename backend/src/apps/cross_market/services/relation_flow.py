from __future__ import annotations

from typing import TYPE_CHECKING

from src.apps.cross_market.engines import evaluate_relation_candidate
from src.apps.cross_market.services.results import CrossMarketRelationUpdateResult
from src.apps.cross_market.services.side_effects import CrossMarketRelationSideEffect
from src.apps.cross_market.support import (
    LEADER_SYMBOLS,
    MATERIAL_RELATION_DELTA,
    RELATION_LOOKBACK,
    RELATION_MAX_LAG_HOURS,
    RELATION_MIN_CORRELATION,
    RELATION_MIN_POINTS,
    relation_timeframe,
)
from src.apps.market_data.domain import utc_now

if TYPE_CHECKING:
    from src.apps.cross_market.services.cross_market_service import CrossMarketService


async def update_coin_relations(
    *,
    service: CrossMarketService,
    follower_coin_id: int,
    timeframe: int,
    emit_events: bool,
) -> tuple[CrossMarketRelationUpdateResult, tuple[CrossMarketRelationSideEffect, ...]]:
    effective_timeframe = relation_timeframe(timeframe)
    service._log_debug(
        "service.update_coin_relations",
        mode="write",
        follower_coin_id=follower_coin_id,
        timeframe=effective_timeframe,
        emit_events=emit_events,
    )
    context = await service._queries.get_relation_computation_context(
        follower_coin_id=follower_coin_id,
        preferred_symbols=LEADER_SYMBOLS,
        limit=8,
    )
    if context is None:
        return (
            CrossMarketRelationUpdateResult(
                status="skipped",
                reason="follower_not_found",
                follower_coin_id=int(follower_coin_id),
            ),
            (),
        )

    follower_points = await service._candles.fetch_points(
        coin_id=context.follower_coin_id,
        timeframe=effective_timeframe,
        limit=RELATION_LOOKBACK,
    )
    if len(follower_points) < RELATION_MIN_POINTS:
        return (
            CrossMarketRelationUpdateResult(
                status="skipped",
                reason="insufficient_follower_candles",
                follower_coin_id=int(follower_coin_id),
            ),
            (),
        )

    candidate_ids = [candidate.coin_id for candidate in context.candidates]
    leader_points_by_id = await service._candles.fetch_points_for_coin_ids(
        coin_ids=candidate_ids,
        timeframe=effective_timeframe,
        limit=RELATION_LOOKBACK,
    )
    existing_rows = await service._queries.list_existing_relation_snapshots(
        follower_coin_id=follower_coin_id,
        leader_coin_ids=candidate_ids,
    )
    existing_by_leader_id = {item.leader_coin_id: item for item in existing_rows}
    updated_at = utc_now()
    follower_closes = tuple(float(item.close) for item in follower_points)
    rows: list[dict[str, object]] = []
    side_effects: list[CrossMarketRelationSideEffect] = []
    for candidate in context.candidates:
        leader_points = leader_points_by_id.get(candidate.coin_id, [])
        analysis = evaluate_relation_candidate(
            leader_closes=tuple(float(item.close) for item in leader_points),
            follower_closes=follower_closes,
            timeframe=effective_timeframe,
            lookback=RELATION_LOOKBACK,
            min_points=RELATION_MIN_POINTS,
            min_correlation=RELATION_MIN_CORRELATION,
            max_lag_hours=RELATION_MAX_LAG_HOURS,
        )
        if analysis is None:
            continue
        rows.append(
            {
                "leader_coin_id": candidate.coin_id,
                "follower_coin_id": follower_coin_id,
                "correlation": analysis.correlation,
                "lag_hours": analysis.lag_hours,
                "confidence": analysis.confidence,
                "updated_at": updated_at,
            }
        )
        previous = existing_by_leader_id.get(candidate.coin_id)
        should_publish = bool(
            emit_events
            and (
                previous is None
                or abs(previous.confidence - analysis.confidence) >= MATERIAL_RELATION_DELTA
                or abs(previous.correlation - analysis.correlation) >= MATERIAL_RELATION_DELTA
            )
        )
        side_effects.append(
            CrossMarketRelationSideEffect(
                leader_coin_id=candidate.coin_id,
                follower_coin_id=follower_coin_id,
                correlation=analysis.correlation,
                lag_hours=analysis.lag_hours,
                confidence=analysis.confidence,
                updated_at=updated_at,
                publish_event=should_publish,
            )
        )

    if not rows:
        return (
            CrossMarketRelationUpdateResult(
                status="skipped",
                reason="relations_not_found",
                follower_coin_id=int(follower_coin_id),
            ),
            (),
        )

    await service._relations.upsert_many(rows)
    best = max(rows, key=lambda item: float(item["confidence"]))
    result = CrossMarketRelationUpdateResult(
        status="ok",
        updated=len(rows),
        published=sum(1 for effect in side_effects if effect.publish_event),
        follower_coin_id=int(follower_coin_id),
        leader_coin_id=int(best["leader_coin_id"]),
        confidence=float(best["confidence"]),
    )
    service._log_info(
        "service.update_coin_relations.result",
        mode="write",
        follower_coin_id=follower_coin_id,
        updated=len(rows),
        published=result.published,
    )
    return result, tuple(side_effects)
