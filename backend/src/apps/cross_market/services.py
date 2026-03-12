from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.apps.cross_market import cache as _cache
from src.apps.cross_market import engine as _legacy_engine
from src.apps.cross_market.query_services import CrossMarketQueryService
from src.apps.cross_market.repositories import CoinRelationRepository, SectorMetricRepository
from src.apps.market_data.domain import utc_now
from src.apps.market_data.repositories import CandleRepository
from src.apps.predictions.services import PredictionCreationBatch, PredictionService, PredictionSideEffectDispatcher
from src.core.db.persistence import PersistenceComponent
from src.core.db.uow import BaseAsyncUnitOfWork
from src.runtime.streams.publisher import publish_event

cache_correlation_snapshot = _cache.cache_correlation_snapshot
cache_correlation_snapshot_async = _cache.cache_correlation_snapshot_async
read_cached_correlation = _cache.read_cached_correlation
read_cached_correlation_async = _cache.read_cached_correlation_async

LEADER_SYMBOLS = _legacy_engine.LEADER_SYMBOLS
MATERIAL_RELATION_DELTA = _legacy_engine.MATERIAL_RELATION_DELTA
RELATION_LOOKBACK = _legacy_engine.RELATION_LOOKBACK
RELATION_MIN_CORRELATION = _legacy_engine.RELATION_MIN_CORRELATION
RELATION_MIN_POINTS = _legacy_engine.RELATION_MIN_POINTS
_best_lagged_correlation = _legacy_engine._best_lagged_correlation
_clamp = _legacy_engine._clamp
_relation_timeframe = _legacy_engine._relation_timeframe
cross_market_alignment_weight = _legacy_engine.cross_market_alignment_weight
detect_market_leader = _legacy_engine.detect_market_leader
process_cross_market_event = _legacy_engine.process_cross_market_event
refresh_sector_momentum = _legacy_engine.refresh_sector_momentum
update_coin_relations = _legacy_engine.update_coin_relations


@dataclass(slots=True, frozen=True)
class _RelationSideEffect:
    leader_coin_id: int
    follower_coin_id: int
    correlation: float
    lag_hours: int
    confidence: float
    updated_at: datetime
    publish_event: bool


@dataclass(slots=True, frozen=True)
class _SectorRotationSideEffect:
    timeframe: int
    source_sector: str
    target_sector: str
    source_strength: float
    target_strength: float
    timestamp: datetime


@dataclass(slots=True, frozen=True)
class _LeaderDetectionSideEffect:
    timeframe: int
    leader_coin_id: int
    leader_symbol: str
    direction: str
    confidence: float
    market_regime: str
    emit_event: bool
    prediction_batch: PredictionCreationBatch


class CrossMarketService(PersistenceComponent):
    def __init__(
        self,
        uow: BaseAsyncUnitOfWork,
        *,
        queries: CrossMarketQueryService | None = None,
        relation_repo: CoinRelationRepository | None = None,
        sector_repo: SectorMetricRepository | None = None,
        candle_repo: CandleRepository | None = None,
    ) -> None:
        super().__init__(
            uow.session,
            component_type="service",
            domain="cross_market",
            component_name="CrossMarketService",
        )
        self._uow = uow
        self._queries = queries or CrossMarketQueryService(uow.session)
        self._relations = relation_repo or CoinRelationRepository(uow.session)
        self._sectors = sector_repo or SectorMetricRepository(uow.session)
        self._candles = candle_repo or CandleRepository(uow.session)

    async def process_event(
        self,
        *,
        coin_id: int,
        timeframe: int,
        event_type: str,
        payload: dict[str, object],
        emit_events: bool = True,
    ) -> dict[str, object]:
        self._log_debug(
            "service.process_cross_market_event",
            mode="write",
            coin_id=coin_id,
            timeframe=timeframe,
            event_type=event_type,
            emit_events=emit_events,
        )
        try:
            relation_result, relation_effects = await self._update_coin_relations(
                follower_coin_id=coin_id,
                timeframe=timeframe,
                emit_events=emit_events and event_type == "candle_closed",
            )
            sector_result, sector_effect = await self._refresh_sector_momentum(
                timeframe=timeframe,
                emit_events=emit_events and event_type == "indicator_updated",
            )
            if event_type == "indicator_updated":
                leader_result, leader_effect, leader_requires_commit = await self._detect_market_leader(
                    coin_id=coin_id,
                    timeframe=timeframe,
                    payload=payload,
                    emit_events=emit_events,
                )
            else:
                leader_result = {"status": "skipped", "reason": "leader_detection_not_requested"}
                leader_effect = None
                leader_requires_commit = False

            requires_commit = bool(relation_effects) or sector_result["status"] == "ok" or leader_requires_commit
            if requires_commit:
                await self._uow.commit()

            for effect in relation_effects:
                await cache_correlation_snapshot_async(
                    leader_coin_id=effect.leader_coin_id,
                    follower_coin_id=effect.follower_coin_id,
                    correlation=effect.correlation,
                    lag_hours=effect.lag_hours,
                    confidence=effect.confidence,
                    updated_at=effect.updated_at,
                )
                if effect.publish_event:
                    publish_event(
                        "correlation_updated",
                        {
                            "coin_id": effect.follower_coin_id,
                            "timeframe": _relation_timeframe(timeframe),
                            "timestamp": effect.updated_at,
                            "leader_coin_id": effect.leader_coin_id,
                            "follower_coin_id": effect.follower_coin_id,
                            "correlation": effect.correlation,
                            "lag_hours": effect.lag_hours,
                            "confidence": effect.confidence,
                        },
                    )

            if sector_effect is not None:
                publish_event(
                    "sector_rotation_detected",
                    {
                        "coin_id": 0,
                        "timeframe": sector_effect.timeframe,
                        "timestamp": sector_effect.timestamp,
                        "source_sector": sector_effect.source_sector,
                        "target_sector": sector_effect.target_sector,
                        "source_strength": sector_effect.source_strength,
                        "target_strength": sector_effect.target_strength,
                    },
                )

            if leader_effect is not None:
                await PredictionSideEffectDispatcher().apply_creation(leader_effect.prediction_batch)
                if leader_effect.emit_event:
                    publish_event(
                        "market_leader_detected",
                        {
                            "coin_id": leader_effect.leader_coin_id,
                            "timeframe": leader_effect.timeframe,
                            "timestamp": utc_now(),
                            "leader_coin_id": leader_effect.leader_coin_id,
                            "leader_symbol": leader_effect.leader_symbol,
                            "direction": leader_effect.direction,
                            "confidence": leader_effect.confidence,
                            "market_regime": leader_effect.market_regime,
                        },
                    )

            result = {
                "status": "ok",
                "relations": relation_result,
                "sectors": sector_result,
                "leader": leader_result,
            }
            self._log_debug(
                "service.process_cross_market_event.result",
                mode="write",
                coin_id=coin_id,
                timeframe=timeframe,
                relation_status=relation_result["status"],
                sector_status=sector_result["status"],
                leader_status=leader_result["status"],
                committed=requires_commit,
            )
            return result
        except Exception:
            self._log_exception(
                "service.process_cross_market_event.error",
                mode="write",
                coin_id=coin_id,
                timeframe=timeframe,
                event_type=event_type,
            )
            raise

    async def _update_coin_relations(
        self,
        *,
        follower_coin_id: int,
        timeframe: int,
        emit_events: bool,
    ) -> tuple[dict[str, object], tuple[_RelationSideEffect, ...]]:
        relation_timeframe = _relation_timeframe(timeframe)
        self._log_debug(
            "service.update_coin_relations",
            mode="write",
            follower_coin_id=follower_coin_id,
            timeframe=relation_timeframe,
            emit_events=emit_events,
        )
        context = await self._queries.get_relation_computation_context(
            follower_coin_id=follower_coin_id,
            preferred_symbols=LEADER_SYMBOLS,
            limit=8,
        )
        if context is None:
            return (
                {"status": "skipped", "reason": "follower_not_found", "follower_coin_id": follower_coin_id},
                (),
            )

        follower_points = await self._candles.fetch_points(
            coin_id=context.follower_coin_id,
            timeframe=relation_timeframe,
            limit=RELATION_LOOKBACK,
        )
        if len(follower_points) < RELATION_MIN_POINTS:
            return (
                {
                    "status": "skipped",
                    "reason": "insufficient_follower_candles",
                    "follower_coin_id": follower_coin_id,
                },
                (),
            )

        candidate_ids = [candidate.coin_id for candidate in context.candidates]
        leader_points_by_id = await self._candles.fetch_points_for_coin_ids(
            coin_ids=candidate_ids,
            timeframe=relation_timeframe,
            limit=RELATION_LOOKBACK,
        )
        existing_rows = await self._queries.list_existing_relation_snapshots(
            follower_coin_id=follower_coin_id,
            leader_coin_ids=candidate_ids,
        )
        existing_by_leader_id = {item.leader_coin_id: item for item in existing_rows}
        updated_at = utc_now()
        rows: list[dict[str, object]] = []
        side_effects: list[_RelationSideEffect] = []
        for candidate in context.candidates:
            leader_points = leader_points_by_id.get(candidate.coin_id, [])
            if len(leader_points) < RELATION_MIN_POINTS:
                continue
            correlation, lag_hours, sample_size = _best_lagged_correlation(
                leader_points,
                follower_points,
                timeframe=relation_timeframe,
            )
            if correlation < RELATION_MIN_CORRELATION:
                continue
            confidence = _clamp(correlation * min(sample_size / RELATION_LOOKBACK, 1.0), 0.2, 0.99)
            rows.append(
                {
                    "leader_coin_id": candidate.coin_id,
                    "follower_coin_id": follower_coin_id,
                    "correlation": float(correlation),
                    "lag_hours": int(lag_hours),
                    "confidence": float(confidence),
                    "updated_at": updated_at,
                }
            )
            previous = existing_by_leader_id.get(candidate.coin_id)
            should_publish = bool(
                emit_events
                and (
                    previous is None
                    or abs(previous.confidence - float(confidence)) >= MATERIAL_RELATION_DELTA
                    or abs(previous.correlation - float(correlation)) >= MATERIAL_RELATION_DELTA
                )
            )
            side_effects.append(
                _RelationSideEffect(
                    leader_coin_id=candidate.coin_id,
                    follower_coin_id=follower_coin_id,
                    correlation=float(correlation),
                    lag_hours=int(lag_hours),
                    confidence=float(confidence),
                    updated_at=updated_at,
                    publish_event=should_publish,
                )
            )

        if not rows:
            return (
                {"status": "skipped", "reason": "relations_not_found", "follower_coin_id": follower_coin_id},
                (),
            )

        await self._relations.upsert_many(rows)
        best = max(rows, key=lambda item: float(item["confidence"]))
        result = {
            "status": "ok",
            "updated": len(rows),
            "published": sum(1 for effect in side_effects if effect.publish_event),
            "follower_coin_id": follower_coin_id,
            "leader_coin_id": int(best["leader_coin_id"]),
            "confidence": float(best["confidence"]),
        }
        self._log_info(
            "service.update_coin_relations.result",
            mode="write",
            follower_coin_id=follower_coin_id,
            updated=len(rows),
            published=result["published"],
        )
        return result, tuple(side_effects)

    async def _refresh_sector_momentum(
        self,
        *,
        timeframe: int,
        emit_events: bool,
    ) -> tuple[dict[str, object], _SectorRotationSideEffect | None]:
        self._log_debug(
            "service.refresh_sector_momentum",
            mode="write",
            timeframe=timeframe,
            emit_events=emit_events,
        )
        previous_top = await self._queries.get_top_sector(timeframe=timeframe)
        aggregates = await self._queries.list_sector_momentum_aggregates()
        if not aggregates:
            return {"status": "skipped", "reason": "sector_rows_not_found"}, None

        market_average = sum(item.sector_strength for item in aggregates) / len(aggregates)
        updated_at = utc_now()
        rows: list[dict[str, object]] = []
        ranked_rows: list[tuple[int, str, float]] = []
        for item in aggregates:
            trend = "sideways"
            if item.avg_price_change_24h >= 1 and item.avg_volume_change_24h >= 0:
                trend = "bullish"
            elif item.avg_price_change_24h <= -1:
                trend = "bearish"
            relative_strength = item.avg_price_change_24h - market_average
            rows.append(
                {
                    "sector_id": item.sector_id,
                    "timeframe": int(timeframe),
                    "sector_strength": item.avg_price_change_24h,
                    "relative_strength": relative_strength,
                    "capital_flow": item.capital_flow,
                    "avg_price_change_24h": item.avg_price_change_24h,
                    "avg_volume_change_24h": item.avg_volume_change_24h,
                    "volatility": item.avg_volatility,
                    "trend": trend,
                    "updated_at": updated_at,
                }
            )
            ranked_rows.append((item.sector_id, item.sector_name, relative_strength))

        await self._sectors.upsert_many(rows)

        sector_effect: _SectorRotationSideEffect | None = None
        if emit_events and previous_top is not None and ranked_rows:
            current_sector_id, current_sector_name, current_strength = sorted(
                ranked_rows,
                key=lambda item: (-item[2], item[1]),
            )[0]
            if previous_top.sector_id != current_sector_id:
                sector_effect = _SectorRotationSideEffect(
                    timeframe=int(timeframe),
                    source_sector=previous_top.sector_name,
                    target_sector=current_sector_name,
                    source_strength=previous_top.relative_strength,
                    target_strength=float(current_strength),
                    timestamp=utc_now(),
                )

        result = {"status": "ok", "updated": len(rows), "timeframe": timeframe}
        self._log_info("service.refresh_sector_momentum.result", mode="write", timeframe=timeframe, updated=len(rows))
        return result, sector_effect

    async def _detect_market_leader(
        self,
        *,
        coin_id: int,
        timeframe: int,
        payload: dict[str, object],
        emit_events: bool,
    ) -> tuple[dict[str, object], _LeaderDetectionSideEffect | None, bool]:
        self._log_debug("service.detect_market_leader", mode="write", coin_id=coin_id, timeframe=timeframe)
        context = await self._queries.get_leader_detection_context(coin_id=coin_id)
        if context is None:
            return (
                {"status": "skipped", "reason": "coin_metrics_not_found", "coin_id": coin_id},
                None,
                False,
            )

        activity_bucket = str(payload.get("activity_bucket") or context.activity_bucket or "")
        price_change_24h = float(payload.get("price_change_24h") or context.price_change_24h or 0.0)
        volume_change_24h = float(context.volume_change_24h or 0.0)
        regime = str(payload.get("market_regime") or context.market_regime or "")
        bullish = price_change_24h > 0
        directional_ok = (bullish and regime in {"bull_trend", "high_volatility"}) or (
            (not bullish) and regime == "bear_trend"
        )
        if activity_bucket != "HOT" or abs(price_change_24h) < 2 or volume_change_24h < 12 or not directional_ok:
            return (
                {"status": "skipped", "reason": "leader_threshold_not_met", "coin_id": coin_id},
                None,
                False,
            )

        confidence = _clamp(
            0.45
            + min(abs(price_change_24h) / 12, 0.2)
            + min(volume_change_24h / 100, 0.2)
            + (0.1 if activity_bucket == "HOT" else 0.0),
            0.45,
            0.95,
        )
        direction = "up" if bullish else "down"
        predictions = await PredictionService(self._uow).create_market_predictions(
            leader_coin_id=coin_id,
            prediction_event="leader_breakout" if bullish else "leader_breakdown",
            expected_move=direction,
            base_confidence=confidence,
        )
        effect = _LeaderDetectionSideEffect(
            timeframe=int(timeframe),
            leader_coin_id=coin_id,
            leader_symbol=context.symbol,
            direction=direction,
            confidence=float(confidence),
            market_regime=regime,
            emit_event=emit_events,
            prediction_batch=predictions,
        )
        prediction_result = predictions.to_summary()
        result = {
            "status": "ok",
            "leader_coin_id": coin_id,
            "direction": direction,
            "confidence": confidence,
            "predictions": prediction_result,
        }
        self._log_info(
            "service.detect_market_leader.result",
            mode="write",
            coin_id=coin_id,
            direction=direction,
            created_predictions=int(prediction_result.get("created") or 0),
        )
        return result, effect, bool(prediction_result.get("created") or 0)


__all__ = [
    "CrossMarketService",
    "cache_correlation_snapshot",
    "cache_correlation_snapshot_async",
    "cross_market_alignment_weight",
    "detect_market_leader",
    "process_cross_market_event",
    "read_cached_correlation_async",
    "read_cached_correlation",
    "refresh_sector_momentum",
    "update_coin_relations",
]
