from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.apps.market_data.models import Coin
from src.apps.predictions.models import MarketPrediction, PredictionResult
from src.apps.predictions.read_models import PredictionReadModel, prediction_read_model_from_mapping
from src.core.db.persistence import AsyncQueryService


class PredictionQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="predictions", service_name="PredictionQueryService")

    @staticmethod
    def _base_stmt():
        leader_coin = aliased(Coin)
        target_coin = aliased(Coin)
        return (
            select(
                MarketPrediction.id,
                MarketPrediction.prediction_type,
                MarketPrediction.leader_coin_id,
                leader_coin.symbol.label("leader_symbol"),
                MarketPrediction.target_coin_id,
                target_coin.symbol.label("target_symbol"),
                MarketPrediction.prediction_event,
                MarketPrediction.expected_move,
                MarketPrediction.lag_hours,
                MarketPrediction.confidence,
                MarketPrediction.created_at,
                MarketPrediction.evaluation_time,
                MarketPrediction.status,
                PredictionResult.actual_move,
                PredictionResult.success,
                PredictionResult.profit,
                PredictionResult.evaluated_at,
            )
            .join(leader_coin, leader_coin.id == MarketPrediction.leader_coin_id)
            .join(target_coin, target_coin.id == MarketPrediction.target_coin_id)
            .outerjoin(PredictionResult, PredictionResult.prediction_id == MarketPrediction.id)
        )

    async def list_predictions(
        self,
        *,
        limit: int,
        status: str | None = None,
    ) -> tuple[PredictionReadModel, ...]:
        self._log_debug(
            "query.list_predictions",
            mode="read",
            limit=limit,
            status=status,
            loading_profile="full",
        )
        stmt = (
            self._base_stmt()
            .order_by(MarketPrediction.created_at.desc(), MarketPrediction.id.desc())
            .limit(max(limit, 1))
        )
        if status is not None:
            stmt = stmt.where(MarketPrediction.status == status)
        rows = (await self.session.execute(stmt)).all()
        items = tuple(prediction_read_model_from_mapping(row._mapping) for row in rows)
        self._log_debug("query.list_predictions.result", mode="read", count=len(items))
        return items

    async def get_read_by_id(self, prediction_id: int) -> PredictionReadModel | None:
        self._log_debug("query.get_prediction_read_by_id", mode="read", prediction_id=prediction_id)
        row = (
            await self.session.execute(
                self._base_stmt()
                .where(MarketPrediction.id == prediction_id)
                .order_by(MarketPrediction.id.desc())
                .limit(1)
            )
        ).first()
        if row is None:
            self._log_debug("query.get_prediction_read_by_id.result", mode="read", found=False)
            return None
        item = prediction_read_model_from_mapping(row._mapping)
        self._log_debug("query.get_prediction_read_by_id.result", mode="read", found=True)
        return item


__all__ = ["PredictionQueryService"]
