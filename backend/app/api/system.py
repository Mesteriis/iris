from fastapi import APIRouter, Request

from app.db.session import ping_database
from app.schemas.system import SourceStatusRead, SystemStatusRead
from app.services.market_sources import get_market_source_carousel
from app.services.market_sources.rate_limits import get_rate_limit_manager

router = APIRouter(tags=["system"])


def _source_status_rows() -> list[SourceStatusRead]:
    carousel = get_market_source_carousel()
    manager = get_rate_limit_manager()
    rows: list[SourceStatusRead] = []

    for name, source in sorted(carousel.sources.items()):
        snapshot = manager.snapshot(name)
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
def status(request: Request) -> SystemStatusRead:
    listener_task = getattr(request.app.state, "taskiq_listener_task", None)
    return SystemStatusRead(
        service="iris",
        status="ok",
        taskiq_mode="embedded",
        taskiq_running=bool(listener_task and not listener_task.done()),
        sources=_source_status_rows(),
    )


@router.get("/health")
def health() -> dict[str, str]:
    ping_database()
    return {"status": "healthy"}
