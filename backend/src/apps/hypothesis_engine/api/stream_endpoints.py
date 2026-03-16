from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from src.apps.hypothesis_engine.api.deps import HypothesisEventStreamAdapterDep

router = APIRouter(tags=["hypothesis:streams"])


@router.get("/sse/ai", summary="Stream AI insight events")
async def stream_ai_events(
    request: Request,
    stream_adapter: HypothesisEventStreamAdapterDep,
    cursor: str | None = Query(default=None),
    once: bool = Query(default=False),
) -> StreamingResponse:
    return stream_adapter.stream_response(request=request, cursor=cursor, once=once)
