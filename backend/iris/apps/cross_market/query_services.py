from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from iris.apps.cross_market.models import CoinRelation, Sector, SectorMetric
from iris.apps.cross_market.read_models import (
    ExistingRelationSnapshotReadModel,
    LeaderDecisionReadModel,
    LeaderDetectionContextReadModel,
    RelationCandidateReadModel,
    RelationComputationContextReadModel,
    SectorLeaderReadModel,
    SectorMomentumAggregateReadModel,
)
from iris.apps.cross_market.support import clamp_relation_value
from iris.apps.indicators.models import CoinMetrics
from iris.apps.market_data.models import Coin
from iris.apps.signals.models import MarketDecision
from iris.core.db.persistence import AsyncQueryService


class CrossMarketQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="cross_market", service_name="CrossMarketQueryService")

    async def get_relation_computation_context(
        self,
        *,
        follower_coin_id: int,
        preferred_symbols: tuple[str, ...],
        limit: int,
    ) -> RelationComputationContextReadModel | None:
        self._log_debug(
            "query.get_cross_market_relation_context",
            mode="read",
            follower_coin_id=follower_coin_id,
            limit=limit,
        )
        follower = (
            await self.session.execute(
                select(Coin.id, Coin.symbol, Coin.sector_id)
                .where(Coin.id == follower_coin_id, Coin.deleted_at.is_(None), Coin.enabled.is_(True))
                .limit(1)
            )
        ).first()
        if follower is None:
            self._log_debug("query.get_cross_market_relation_context.result", mode="read", found=False)
            return None

        preferred_ids = (
            await self.session.execute(
                select(Coin.id)
                .where(Coin.symbol.in_(preferred_symbols), Coin.deleted_at.is_(None), Coin.enabled.is_(True))
            )
        ).scalars().all()
        ranked = (
            await self.session.execute(
                select(Coin.id, Coin.symbol)
                .join(CoinMetrics, CoinMetrics.coin_id == Coin.id)
                .where(
                    Coin.id != follower_coin_id,
                    Coin.deleted_at.is_(None),
                    Coin.enabled.is_(True),
                )
                .order_by(CoinMetrics.market_cap.desc().nullslast(), CoinMetrics.activity_score.desc().nullslast(), Coin.symbol.asc())
                .limit(max(limit * 2, 12))
            )
        ).all()
        by_id: dict[int, RelationCandidateReadModel] = {
            int(row.id): RelationCandidateReadModel(coin_id=int(row.id), symbol=str(row.symbol))
            for row in ranked
        }
        sector_id = int(follower.sector_id) if follower.sector_id is not None else None
        if sector_id is not None:
            same_sector = (
                await self.session.execute(
                    select(Coin.id, Coin.symbol)
                    .where(
                        Coin.id != follower_coin_id,
                        Coin.deleted_at.is_(None),
                        Coin.enabled.is_(True),
                        Coin.sector_id == sector_id,
                    )
                    .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
                    .limit(limit)
                )
            ).all()
            for row in same_sector:
                by_id[int(row.id)] = RelationCandidateReadModel(coin_id=int(row.id), symbol=str(row.symbol))
        ordered: list[RelationCandidateReadModel] = []
        for coin_id in preferred_ids:
            candidate = by_id.get(int(coin_id))
            if candidate is not None and candidate not in ordered:
                ordered.append(candidate)
        for candidate in by_id.values():
            if candidate not in ordered:
                ordered.append(candidate)
        item = RelationComputationContextReadModel(
            follower_coin_id=int(follower.id),
            follower_symbol=str(follower.symbol),
            sector_id=sector_id,
            candidates=tuple(ordered[:limit]),
        )
        self._log_debug(
            "query.get_cross_market_relation_context.result",
            mode="read",
            found=True,
            candidate_count=len(item.candidates),
        )
        return item

    async def list_existing_relation_snapshots(
        self,
        *,
        follower_coin_id: int,
        leader_coin_ids: list[int],
    ) -> tuple[ExistingRelationSnapshotReadModel, ...]:
        self._log_debug(
            "query.list_cross_market_relation_snapshots",
            mode="read",
            follower_coin_id=follower_coin_id,
            leader_coin_count=len(leader_coin_ids),
        )
        if not leader_coin_ids:
            return ()
        rows = (
            await self.session.execute(
                select(
                    CoinRelation.leader_coin_id,
                    CoinRelation.follower_coin_id,
                    CoinRelation.correlation,
                    CoinRelation.lag_hours,
                    CoinRelation.confidence,
                    CoinRelation.updated_at,
                )
                .where(
                    CoinRelation.follower_coin_id == follower_coin_id,
                    CoinRelation.leader_coin_id.in_(leader_coin_ids),
                )
            )
        ).all()
        items = tuple(
            ExistingRelationSnapshotReadModel(
                leader_coin_id=int(row.leader_coin_id),
                follower_coin_id=int(row.follower_coin_id),
                correlation=float(row.correlation),
                lag_hours=int(row.lag_hours),
                confidence=float(row.confidence),
                updated_at=row.updated_at,
            )
            for row in rows
        )
        self._log_debug("query.list_cross_market_relation_snapshots.result", mode="read", count=len(items))
        return items

    async def get_top_sector(self, *, timeframe: int) -> SectorLeaderReadModel | None:
        self._log_debug("query.get_cross_market_top_sector", mode="read", timeframe=timeframe)
        row = (
            await self.session.execute(
                select(SectorMetric.sector_id, Sector.name, SectorMetric.relative_strength)
                .join(Sector, Sector.id == SectorMetric.sector_id)
                .where(SectorMetric.timeframe == timeframe)
                .order_by(SectorMetric.relative_strength.desc(), Sector.name.asc())
                .limit(1)
            )
        ).first()
        if row is None:
            self._log_debug("query.get_cross_market_top_sector.result", mode="read", found=False)
            return None
        item = SectorLeaderReadModel(
            sector_id=int(row.sector_id),
            sector_name=str(row.name),
            relative_strength=float(row.relative_strength or 0.0),
        )
        self._log_debug("query.get_cross_market_top_sector.result", mode="read", found=True)
        return item

    async def list_sector_momentum_aggregates(self) -> tuple[SectorMomentumAggregateReadModel, ...]:
        self._log_debug("query.list_cross_market_sector_momentum_aggregates", mode="read")
        rows = (
            await self.session.execute(
                select(
                    Sector.id.label("sector_id"),
                    Sector.name.label("sector_name"),
                    func.avg(CoinMetrics.price_change_24h).label("avg_price_change_24h"),
                    func.avg(CoinMetrics.volume_change_24h).label("avg_volume_change_24h"),
                    func.avg(CoinMetrics.volatility).label("avg_volatility"),
                    func.avg(CoinMetrics.price_change_24h).label("sector_strength"),
                    func.avg((CoinMetrics.volume_change_24h / 100.0) + (CoinMetrics.price_change_24h / 10.0)).label(
                        "capital_flow"
                    ),
                )
                .join(Coin, Coin.sector_id == Sector.id)
                .join(CoinMetrics, CoinMetrics.coin_id == Coin.id)
                .where(Coin.deleted_at.is_(None), Coin.enabled.is_(True))
                .group_by(Sector.id, Sector.name)
                .order_by(Sector.id.asc())
            )
        ).all()
        items = tuple(
            SectorMomentumAggregateReadModel(
                sector_id=int(row.sector_id),
                sector_name=str(row.sector_name),
                avg_price_change_24h=float(row.avg_price_change_24h or 0.0),
                avg_volume_change_24h=float(row.avg_volume_change_24h or 0.0),
                avg_volatility=float(row.avg_volatility or 0.0),
                sector_strength=float(row.sector_strength or 0.0),
                capital_flow=float(row.capital_flow or 0.0),
            )
            for row in rows
        )
        self._log_debug("query.list_cross_market_sector_momentum_aggregates.result", mode="read", count=len(items))
        return items

    async def get_leader_detection_context(self, *, coin_id: int) -> LeaderDetectionContextReadModel | None:
        self._log_debug("query.get_cross_market_leader_detection_context", mode="read", coin_id=coin_id)
        row = (
            await self.session.execute(
                select(
                    Coin.id,
                    Coin.symbol,
                    Coin.sector_id,
                    CoinMetrics.activity_bucket,
                    CoinMetrics.price_change_24h,
                    CoinMetrics.volume_change_24h,
                    CoinMetrics.market_regime,
                )
                .join(CoinMetrics, CoinMetrics.coin_id == Coin.id)
                .where(Coin.id == coin_id)
                .limit(1)
            )
        ).first()
        if row is None:
            self._log_debug("query.get_cross_market_leader_detection_context.result", mode="read", found=False)
            return None
        item = LeaderDetectionContextReadModel(
            coin_id=int(row.id),
            symbol=str(row.symbol),
            activity_bucket=str(row.activity_bucket) if row.activity_bucket is not None else None,
            price_change_24h=float(row.price_change_24h or 0.0),
            volume_change_24h=float(row.volume_change_24h or 0.0),
            market_regime=str(row.market_regime) if row.market_regime is not None else None,
            sector_id=int(row.sector_id) if row.sector_id is not None else None,
        )
        self._log_debug("query.get_cross_market_leader_detection_context.result", mode="read", found=True)
        return item

    async def get_latest_leader_decision(self, *, leader_coin_id: int, timeframe: int) -> LeaderDecisionReadModel | None:
        self._log_debug("query.get_cross_market_leader_decision", mode="read", leader_coin_id=leader_coin_id, timeframe=timeframe)
        supported_timeframes = tuple(dict.fromkeys((int(timeframe), 60, 240, 1440)))
        row = (
            await self.session.execute(
                select(MarketDecision.decision, MarketDecision.confidence)
                .where(
                    MarketDecision.coin_id == int(leader_coin_id),
                    MarketDecision.timeframe.in_(supported_timeframes),
                )
                .order_by(MarketDecision.created_at.desc(), MarketDecision.id.desc())
                .limit(1)
            )
        ).first()
        if row is not None:
            item = LeaderDecisionReadModel(
                leader_coin_id=int(leader_coin_id),
                decision=str(row.decision),
                confidence=float(row.confidence),
            )
            self._log_debug("query.get_cross_market_leader_decision.result", mode="read", found=True, source="market_decision")
            return item

        price_change = await self.session.scalar(
            select(CoinMetrics.price_change_24h).where(CoinMetrics.coin_id == int(leader_coin_id)).limit(1)
        )
        if price_change is None:
            self._log_debug("query.get_cross_market_leader_decision.result", mode="read", found=False)
            return None

        price_change_value = float(price_change or 0.0)
        decision = "HOLD"
        confidence = 0.3
        if price_change_value > 0:
            decision = "BUY"
            confidence = clamp_relation_value(abs(price_change_value) / 10, 0.25, 0.75)
        elif price_change_value < 0:
            decision = "SELL"
            confidence = clamp_relation_value(abs(price_change_value) / 10, 0.25, 0.75)
        item = LeaderDecisionReadModel(
            leader_coin_id=int(leader_coin_id),
            decision=decision,
            confidence=float(confidence),
        )
        self._log_debug("query.get_cross_market_leader_decision.result", mode="read", found=True, source="coin_metrics")
        return item


__all__ = ["CrossMarketQueryService"]
