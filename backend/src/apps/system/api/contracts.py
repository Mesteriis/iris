from pydantic import BaseModel

from src.apps.system.schemas import SourceStatusRead, SystemStatusRead
from src.core.http.operations import OperationEventResponse, OperationResultResponse, OperationStatusResponse


class HealthRead(BaseModel):
    status: str


__all__ = [
    "HealthRead",
    "OperationEventResponse",
    "OperationResultResponse",
    "OperationStatusResponse",
    "SourceStatusRead",
    "SystemStatusRead",
]
