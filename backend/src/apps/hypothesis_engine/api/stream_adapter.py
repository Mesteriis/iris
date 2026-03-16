import json
from uuid import uuid4

from fastapi import Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import ResponseError

from src.apps.hypothesis_engine.constants import AI_STREAM_PREFIXES, FRONTEND_AI_SSE_GROUP
from src.runtime.streams.types import parse_stream_message


class HypothesisEventStreamAdapter:
    def __init__(self, *, redis_url: str, stream_name: str) -> None:
        self._redis_url = redis_url
        self._stream_name = stream_name

    async def _ensure_group(self, client: AsyncRedis) -> None:
        try:
            await client.xgroup_create(self._stream_name, FRONTEND_AI_SSE_GROUP, id="$", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    @staticmethod
    def _event_payload(message) -> dict[str, object]:
        return {
            "coin_id": int(message.coin_id),
            "timeframe": int(message.timeframe),
            "timestamp": message.timestamp.isoformat(),
            **dict(message.payload),
        }

    async def iter_events(self, *, request: Request, cursor: str | None, once: bool):
        client = AsyncRedis.from_url(self._redis_url, decode_responses=True)
        consumer_name = f"frontend-ai-{uuid4().hex[:8]}"
        try:
            if cursor is None:
                await self._ensure_group(client)
            last_id = cursor or ">"
            while not await request.is_disconnected():
                if cursor is None:
                    records = await client.xreadgroup(
                        FRONTEND_AI_SSE_GROUP,
                        consumer_name,
                        {self._stream_name: ">"},
                        count=20,
                        block=1000,
                    )
                else:
                    records = await client.xread({self._stream_name: last_id}, count=20, block=1000)
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
                        payload = {
                            "event": message.event_type,
                            "payload": self._event_payload(message),
                        }
                        if cursor is None:
                            await client.xack(stream_name, FRONTEND_AI_SSE_GROUP, stream_id)
                        last_id = stream_id
                        yield (
                            f"event: {message.event_type}\n"
                            f"data: {json.dumps(payload, ensure_ascii=True, sort_keys=True)}\n\n"
                        )
                        if once:
                            return
        finally:
            await client.aclose()

    def stream_response(
        self,
        *,
        request: Request,
        cursor: str | None,
        once: bool,
    ) -> StreamingResponse:
        return StreamingResponse(
            self.iter_events(request=request, cursor=cursor, once=once),
            media_type="text/event-stream",
        )
