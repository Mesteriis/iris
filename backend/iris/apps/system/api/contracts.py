from pydantic import BaseModel

from iris.apps.system.schemas import SourceStatusRead, SystemStatusRead
from iris.core.http.operations import OperationEventResponse, OperationResultResponse, OperationStatusResponse


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
