from iris.apps.patterns.runtime_results import PatternDiscoveryRefreshResult
from iris.apps.patterns.task_service_support import (
    PatternTaskServiceSupport,
    payload_int,
    payload_optional_string,
    payload_string,
)
from iris.core.db.uow import BaseAsyncUnitOfWork


class PatternDiscoveryService(PatternTaskServiceSupport):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternDiscoveryService")

    async def refresh(self) -> PatternDiscoveryRefreshResult:
        payload = await self._refresh_discovered_patterns()
        return PatternDiscoveryRefreshResult(
            status=payload_string(payload.get("status"), default="ok"),
            patterns=payload_int(payload.get("patterns")),
            reason=payload_optional_string(payload.get("reason")),
        )


__all__ = ["PatternDiscoveryService"]
