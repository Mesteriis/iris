from __future__ import annotations

from pydantic import BaseModel

from src.apps.system.schemas import SourceStatusRead, SystemStatusRead


class HealthRead(BaseModel):
    status: str


__all__ = ["HealthRead", "SourceStatusRead", "SystemStatusRead"]
