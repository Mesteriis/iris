from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import ResponseError

from src.apps.hypothesis_engine.constants import AI_STREAM_PREFIXES, FRONTEND_AI_SSE_GROUP
from src.apps.hypothesis_engine.exceptions import InvalidPromptPayloadError, PromptNotFoundError
from src.apps.hypothesis_engine.query_services import HypothesisQueryService
from src.apps.hypothesis_engine.schemas import (
    AIHypothesisEvalRead,
    AIHypothesisRead,
    AIPromptCreate,
    AIPromptRead,
    AIPromptUpdate,
)
from src.apps.hypothesis_engine.services import PromptService
from src.core.db.uow import BaseAsyncUnitOfWork, get_uow
from src.core.settings import get_settings
from src.runtime.streams.types import parse_stream_message

router = APIRouter(tags=["hypothesis"])
DB_UOW = Depends(get_uow)


def _event_payload(message) -> dict[str, object]:
    return {
        "coin_id": int(message.coin_id),
        "timeframe": int(message.timeframe),
        "timestamp": message.timestamp.isoformat(),
        **dict(message.payload),
    }


async def _ensure_sse_group(client: AsyncRedis, *, stream_name: str) -> None:
    try:
        await client.xgroup_create(stream_name, FRONTEND_AI_SSE_GROUP, id="$", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def _iter_ai_stream(request: Request, *, cursor: str | None, once: bool):
    settings = get_settings()
    client = AsyncRedis.from_url(settings.redis_url, decode_responses=True)
    consumer_name = f"frontend-ai-{uuid4().hex[:8]}"
    try:
        if cursor is None:
            await _ensure_sse_group(client, stream_name=settings.event_stream_name)
        last_id = cursor or ">"
        while not await request.is_disconnected():
            if cursor is None:
                records = await client.xreadgroup(
                    FRONTEND_AI_SSE_GROUP,
                    consumer_name,
                    {settings.event_stream_name: ">"},
                    count=20,
                    block=1000,
                )
            else:
                records = await client.xread({settings.event_stream_name: last_id}, count=20, block=1000)
            if not records:
                continue
            for stream_name, items in records:
                for stream_id, fields in items:
                    message = parse_stream_message(stream_id, fields)
                    if not message.event_type.startswith(AI_STREAM_PREFIXES):
                        if cursor is None:
                            await client.xack(stream_name, FRONTEND_AI_SSE_GROUP, stream_id)
                        last_id = stream_id
                        continue
                    payload = {"event": message.event_type, "payload": _event_payload(message)}
                    if cursor is None:
                        await client.xack(stream_name, FRONTEND_AI_SSE_GROUP, stream_id)
                    last_id = stream_id
                    yield f"event: {message.event_type}\ndata: {json.dumps(payload, ensure_ascii=True, sort_keys=True)}\n\n"
                    if once:
                        return
    finally:
        await client.aclose()


@router.get("/hypothesis/prompts", response_model=list[AIPromptRead])
async def read_ai_prompts(
    name: str | None = Query(default=None),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[AIPromptRead]:
    return await PromptService(uow).list_prompts(name=name)


@router.post("/hypothesis/prompts", response_model=AIPromptRead, status_code=status.HTTP_201_CREATED)
async def create_ai_prompt(
    payload: AIPromptCreate,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> AIPromptRead:
    try:
        return await PromptService(uow).create_prompt(payload)
    except InvalidPromptPayloadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/hypothesis/prompts/{prompt_id}", response_model=AIPromptRead)
async def patch_ai_prompt(
    prompt_id: int,
    payload: AIPromptUpdate,
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> AIPromptRead:
    try:
        return await PromptService(uow).update_prompt(prompt_id, payload)
    except PromptNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/hypothesis/prompts/{prompt_id}/activate", response_model=AIPromptRead)
async def activate_ai_prompt(prompt_id: int, uow: BaseAsyncUnitOfWork = DB_UOW) -> AIPromptRead:
    try:
        return await PromptService(uow).activate_prompt(prompt_id)
    except PromptNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/hypothesis/hypotheses", response_model=list[AIHypothesisRead])
async def read_hypotheses(
    limit: int = Query(default=50, ge=1, le=500),
    status: str | None = Query(default=None),
    coin_id: int | None = Query(default=None, ge=1),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[AIHypothesisRead]:
    items = await HypothesisQueryService(uow.session).list_hypotheses(limit=limit, status=status, coin_id=coin_id)
    return [AIHypothesisRead.model_validate(item) for item in items]


@router.get("/hypothesis/evals", response_model=list[AIHypothesisEvalRead])
async def read_hypothesis_evals(
    limit: int = Query(default=50, ge=1, le=500),
    hypothesis_id: int | None = Query(default=None, ge=1),
    uow: BaseAsyncUnitOfWork = DB_UOW,
) -> list[AIHypothesisEvalRead]:
    items = await HypothesisQueryService(uow.session).list_evals(limit=limit, hypothesis_id=hypothesis_id)
    return [AIHypothesisEvalRead.model_validate(item) for item in items]


@router.post("/hypothesis/jobs/evaluate", status_code=status.HTTP_202_ACCEPTED)
async def run_hypothesis_evaluation_job() -> dict[str, object]:
    from src.apps.hypothesis_engine.tasks.hypothesis_tasks import evaluate_hypotheses_job

    await evaluate_hypotheses_job.kiq()
    return {"status": "queued"}


@router.get("/hypothesis/sse/ai")
async def stream_ai_events(
    request: Request,
    cursor: str | None = Query(default=None),
    once: bool = Query(default=False),
) -> StreamingResponse:
    return StreamingResponse(
        _iter_ai_stream(request, cursor=cursor, once=once),
        media_type="text/event-stream",
    )
