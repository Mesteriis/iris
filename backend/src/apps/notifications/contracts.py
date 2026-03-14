from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class NotificationHumanizationOutput(BaseModel):
    title: str
    message: str
    severity: Literal["info", "warning", "critical"]
    urgency: Literal["low", "medium", "high"]

    model_config = ConfigDict(extra="forbid")


__all__ = ["NotificationHumanizationOutput"]
