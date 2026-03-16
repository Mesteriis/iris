from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from src.apps.frontend.api.stream_adapter import FrontendDashboardStreamAdapter
from src.core.settings import get_settings

router = APIRouter(tags=["frontend:streams"])

_settings = get_settings()
_adapter = FrontendDashboardStreamAdapter(
    redis_url=_settings.redis_url,
    stream_name=_settings.event_stream_name,
)


@router.get("/stream/dashboard", summary="Stream live dashboard updates")
async def stream_dashboard_events(
    request: Request,
    cursor: str | None = Query(default=None),
    once: bool = Query(default=False),
) -> StreamingResponse:
    return _adapter.stream_response(request=request, cursor=cursor, once=once)
