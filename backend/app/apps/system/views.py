from fastapi import APIRouter, Request

from app.apps.system.services import get_market_source_carousel, get_rate_limit_manager
from app.core.db.session import ping_database
from app.apps.system.schemas import SourceStatusRead, SystemStatusRead

router = APIRouter(tags=["system"])


async def _source_status_rows() -> list[SourceStatusRead]:
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


@router.get("/status", response_model=SystemStatusRead)
async def status(request: Request) -> SystemStatusRead:
    worker_processes = getattr(request.app.state, "taskiq_worker_processes", [])
    return SystemStatusRead(
        service="iris",
        status="ok",
        taskiq_mode="process_workers",
        taskiq_running=bool(worker_processes) and all(process.is_alive() for process in worker_processes),
        sources=await _source_status_rows(),
    )


@router.get("/health")
async def health() -> dict[str, str]:
    await ping_database()
    return {"status": "healthy"}
