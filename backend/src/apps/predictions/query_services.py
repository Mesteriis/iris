from collections.abc import Mapping
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.market_data.models import Coin
from src.apps.predictions.models import MarketPrediction
from src.apps.predictions.query_builders import prediction_select as _prediction_select
from src.apps.predictions.read_models import PredictionReadModel, prediction_read_model_from_mapping
from src.core.db.persistence import AsyncQueryService


class PredictionQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="predictions", service_name="PredictionQueryService")

    @staticmethod
    def _base_stmt() -> Any:
        return _prediction_select()

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
        items = tuple(prediction_read_model_from_mapping(cast(Mapping[str, Any], row._mapping)) for row in rows)
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
        item = prediction_read_model_from_mapping(cast(Mapping[str, Any], row._mapping))
        self._log_debug("query.get_prediction_read_by_id.result", mode="read", found=True)
        return item


__all__ = ["PredictionQueryService"]
