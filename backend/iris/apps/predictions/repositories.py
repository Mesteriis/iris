from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from iris.apps.cross_market.models import CoinRelation
from iris.apps.market_data.models import Coin
from iris.apps.predictions.models import MarketPrediction
from iris.core.db.persistence import AsyncRepository


@dataclass(slots=True, frozen=True)
class PredictionCreationCandidate:
    target_coin_id: int
    lag_hours: int
    relation_confidence: float
    correlation: float


class PredictionRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="predictions", repository_name="PredictionRepository")

    async def list_creation_candidates(
        self,
        *,
        leader_coin_id: int,
        minimum_confidence: float,
        limit: int,
    ) -> tuple[PredictionCreationCandidate, ...]:
        self._log_debug(
            "repo.list_prediction_creation_candidates",
            mode="write",
            leader_coin_id=leader_coin_id,
            minimum_confidence=minimum_confidence,
            limit=limit,
            bulk=True,
        )
        rows = (
            await self.session.execute(
                select(
                    CoinRelation.follower_coin_id,
                    CoinRelation.lag_hours,
                    CoinRelation.confidence,
                    CoinRelation.correlation,
                )
                .join(Coin, Coin.id == CoinRelation.follower_coin_id)
                .where(
                    CoinRelation.leader_coin_id == leader_coin_id,
                    CoinRelation.confidence >= minimum_confidence,
                    Coin.deleted_at.is_(None),
                    Coin.enabled.is_(True),
                )
                .order_by(CoinRelation.confidence.desc(), CoinRelation.correlation.desc())
                .limit(max(limit, 1))
            )
        ).all()
        items = tuple(
            PredictionCreationCandidate(
                target_coin_id=int(row.follower_coin_id),
                lag_hours=max(int(row.lag_hours or 1), 1),
                relation_confidence=float(row.confidence or 0.0),
                correlation=float(row.correlation or 0.0),
            )
            for row in rows
        )
        self._log_debug("repo.list_prediction_creation_candidates.result", mode="write", count=len(items))
        return items

    async def list_active_pending_evaluation_times(
        self,
        *,
        leader_coin_id: int,
        target_coin_ids: list[int],
        prediction_event: str,
        expected_move: str,
    ) -> dict[int, datetime]:
        normalized_ids = list(dict.fromkeys(int(value) for value in target_coin_ids))
        self._log_debug(
            "repo.list_prediction_pending_windows",
            mode="write",
            leader_coin_id=leader_coin_id,
            target_count=len(normalized_ids),
            prediction_event=prediction_event,
            expected_move=expected_move,
            bulk=True,
        )
        if not normalized_ids:
            return {}
        rows = (
            await self.session.execute(
                select(
                    MarketPrediction.target_coin_id,
                    func.max(MarketPrediction.evaluation_time).label("evaluation_time"),
                )
                .where(
                    MarketPrediction.leader_coin_id == leader_coin_id,
                    MarketPrediction.target_coin_id.in_(normalized_ids),
                    MarketPrediction.prediction_event == prediction_event,
                    MarketPrediction.expected_move == expected_move,
                    MarketPrediction.status == "pending",
                )
                .group_by(MarketPrediction.target_coin_id)
            )
        ).all()
        items = {
            int(row.target_coin_id): row.evaluation_time
            for row in rows
            if row.evaluation_time is not None
        }
        self._log_debug("repo.list_prediction_pending_windows.result", mode="write", count=len(items))
        return items

    async def add(self, prediction: MarketPrediction) -> MarketPrediction:
        self._log_info(
            "repo.add_prediction",
            mode="write",
            leader_coin_id=int(prediction.leader_coin_id),
            target_coin_id=int(prediction.target_coin_id),
        )
        self.session.add(prediction)
        await self.session.flush()
        return prediction

    async def list_pending_for_update(self, *, limit: int) -> list[MarketPrediction]:
        self._log_debug(
            "repo.list_pending_predictions_for_update",
            mode="write",
            limit=limit,
            loading_profile="with_result",
            lock=True,
            bulk=True,
        )
        rows = (
            await self.session.execute(
                select(MarketPrediction)
                .options(selectinload(MarketPrediction.result))
                .where(MarketPrediction.status == "pending")
                .order_by(MarketPrediction.created_at.asc(), MarketPrediction.id.asc())
                .limit(max(limit, 1))
            )
        ).scalars().all()
        items = list(rows)
        self._log_debug("repo.list_pending_predictions_for_update.result", mode="write", count=len(items))
        return items


class PredictionRelationRepository(AsyncRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="predictions", repository_name="PredictionRelationRepository")

    async def get_for_update(
        self,
        *,
        leader_coin_id: int,
        target_coin_id: int,
    ) -> CoinRelation | None:
        self._log_debug(
            "repo.get_prediction_relation_for_update",
            mode="write",
            leader_coin_id=leader_coin_id,
            target_coin_id=target_coin_id,
            lock=True,
        )
        relation = await self.session.scalar(
            select(CoinRelation)
            .where(
                CoinRelation.leader_coin_id == leader_coin_id,
                CoinRelation.follower_coin_id == target_coin_id,
            )
            .with_for_update()
            .limit(1)
        )
        self._log_debug("repo.get_prediction_relation_for_update.result", mode="write", found=relation is not None)
        return relation


__all__ = [
    "PredictionCreationCandidate",
    "PredictionRelationRepository",
    "PredictionRepository",
]
