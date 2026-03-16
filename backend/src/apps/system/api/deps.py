from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from src.apps.system.schemas import SourceStatusRead, SystemStatusRead
from src.apps.system.services import get_market_source_carousel, get_rate_limit_manager
from src.core.db.session import ping_database
from src.core.http.deps import get_operation_store
from src.core.http.operation_store import OperationStore
from src.core.http.operations import OperationEventResponse, OperationResultResponse, OperationStatusResponse


@dataclass(slots=True, frozen=True)
class SystemStatusFacade:
    async def list_source_status_rows(self) -> list[SourceStatusRead]:
        carousel = get_market_source_carousel()
        manager = get_rate_limit_manager()
        rows: list[SourceStatusRead] = []

        for name, source in sorted(carousel.sources.items()):
            snapshot = await manager.snapshot(name)
            rows.append(
                SourceStatusRead(
                    name=name,
                    asset_types=sorted(source.asset_types),
                    supported_intervals=sorted(source.supported_intervals),
                    official_limit=snapshot.policy.official_limit,
                    rate_limited=snapshot.cooldown_seconds > 0,
                    cooldown_seconds=round(snapshot.cooldown_seconds, 1),
                    next_available_at=snapshot.next_available_at,
                    requests_per_window=snapshot.policy.requests_per_window,
                    window_seconds=snapshot.policy.window_seconds,
                    min_interval_seconds=snapshot.policy.min_interval_seconds or None,
                    request_cost=snapshot.policy.request_cost,
                    fallback_retry_after_seconds=snapshot.policy.fallback_retry_after_seconds,
                )
            )

        return rows

    async def get_status(self, *, worker_processes: list[object]) -> SystemStatusRead:
        return SystemStatusRead(
            service="iris",
            status="ok",
            taskiq_mode="process_workers",
            taskiq_running=bool(worker_processes) and all(process.is_alive() for process in worker_processes),
            sources=await self.list_source_status_rows(),
        )

    async def ping(self) -> None:
        await ping_database()


@dataclass(slots=True, frozen=True)
class SystemOperationFacade:
    store: OperationStore

    async def get_status(self, operation_id: str) -> OperationStatusResponse | None:
        return await self.store.get_status(operation_id)

    async def get_result(self, operation_id: str) -> OperationResultResponse | None:
        return await self.store.get_result(operation_id)

    async def list_events(self, operation_id: str) -> tuple[OperationEventResponse, ...]:
        return await self.store.list_events(operation_id)


def get_system_status_facade() -> SystemStatusFacade:
    return SystemStatusFacade()


def get_system_operation_facade(
    store: OperationStore = Depends(get_operation_store),
) -> SystemOperationFacade:
    return SystemOperationFacade(store=store)


SystemStatusFacadeDep = Annotated[SystemStatusFacade, Depends(get_system_status_facade)]
SystemOperationFacadeDep = Annotated[SystemOperationFacade, Depends(get_system_operation_facade)]


__all__ = [
    "SystemOperationFacadeDep",
    "SystemOperationFacade",
    "SystemStatusFacadeDep",
    "SystemStatusFacade",
    "get_system_operation_facade",
    "get_system_status_facade",
]
