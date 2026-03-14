from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class HypothesisGenerationOutput(BaseModel):
    type: str
    confidence: float = Field(ge=0.0, le=1.0)
    horizon_min: int = Field(ge=1)
    direction: Literal["up", "down", "neutral"]
    target_move: float = Field(gt=0.0)
    summary: str
    assets: list[str] = Field(min_length=1)
    explain: str | None = None
    kind: str | None = None

    @field_validator("assets")
    @classmethod
    def normalize_assets(cls, value: list[str]) -> list[str]:
        assets = [str(item).strip() for item in value if str(item).strip()]
        if not assets:
            raise ValueError("At least one asset must be present in the hypothesis output.")
        return assets


__all__ = ["HypothesisGenerationOutput"]
