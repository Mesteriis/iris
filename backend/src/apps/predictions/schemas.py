from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PredictionRead(BaseModel):
    id: int
    prediction_type: str
    leader_coin_id: int
    leader_symbol: str
    target_coin_id: int
    target_symbol: str
    prediction_event: str
    expected_move: str
    lag_hours: int
    confidence: float
    created_at: datetime
    evaluation_time: datetime
    status: str
    actual_move: float | None = None
    success: bool | None = None
    profit: float | None = None
    evaluated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


__all__ = ["PredictionRead"]
