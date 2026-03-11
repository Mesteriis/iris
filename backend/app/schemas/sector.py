from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SectorRead(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_at: datetime
    coin_count: int

    model_config = ConfigDict(from_attributes=True)


class SectorMetricRead(BaseModel):
    sector_id: int
    name: str
    description: str | None = None
    timeframe: int
    sector_strength: float
    relative_strength: float
    capital_flow: float
    volatility: float
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SectorNarrativeRead(BaseModel):
    timeframe: int
    top_sector: str | None = None
    rotation_state: str | None = None
    btc_dominance: float | None = None

    model_config = ConfigDict(from_attributes=True)


class SectorMetricsResponse(BaseModel):
    items: list[SectorMetricRead]
    narratives: list[SectorNarrativeRead]

    model_config = ConfigDict(from_attributes=True)
