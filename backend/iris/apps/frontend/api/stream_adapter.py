import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis as AsyncRedis

from iris.apps.indicators.api.presenters import coin_metrics_read
from iris.apps.indicators.query_services import IndicatorQueryService
from iris.apps.market_data.api.presenters import coin_read
from iris.apps.market_data.query_services import MarketDataQueryService
from iris.apps.portfolio.api.presenters import (
    portfolio_action_read,
    portfolio_position_read,
    portfolio_state_read,
)
from iris.apps.portfolio.query_services import PortfolioQueryService
from iris.apps.signals.api.presenters import coin_market_decision_read, market_decision_read, signal_read
from iris.apps.signals.query_services import SignalQueryService
from iris.core.db.uow import AsyncUnitOfWork
from iris.runtime.streams.types import IrisEvent, parse_stream_message

_ASSET_EVENT_TYPES = frozenset(
    {
        "indicator_updated",
        "signal_created",
        "market_regime_changed",
        "decision_generated",
        "portfolio_position_changed",
        "portfolio_position_opened",
        "portfolio_position_closed",
        "portfolio_rebalanced",
        "portfolio_balance_updated",
    }
)
_PORTFOLIO_EVENT_TYPES = frozenset(
    {
        "portfolio_position_changed",
        "portfolio_position_opened",
        "portfolio_position_closed",
        "portfolio_rebalanced",
        "portfolio_balance_updated",
    }
)
_FRONTEND_EVENT_TYPES = _ASSET_EVENT_TYPES | _PORTFOLIO_EVENT_TYPES
_SIGNAL_LIMIT = 48
_PORTFOLIO_POSITION_LIMIT = 40
_PORTFOLIO_ACTION_LIMIT = 40


@dataclass(frozen=True, slots=True)
class FrontendStreamEvent:
    event: str
    data: dict[str, object]


class FrontendDashboardStreamAdapter:
    def __init__(self, *, redis_url: str, stream_name: str) -> None:
        self._redis_url = redis_url
        self._stream_name = stream_name

    async def _build_asset_snapshot(
        self,
        *,
        event: IrisEvent,
        market_data: MarketDataQueryService,
        indicators: IndicatorQueryService,
        signals: SignalQueryService,
    ) -> FrontendStreamEvent | None:
        if event.coin_id <= 0:
            return None
        coin_item = await market_data.get_coin_read_by_id(event.coin_id)
        if coin_item is None:
            return None

        metric_item = await indicators.get_coin_metrics(symbol=coin_item.symbol)
        signal_items = await signals.list_signals(symbol=coin_item.symbol, limit=_SIGNAL_LIMIT)
        signal_count = await signals.count_signals(symbol=coin_item.symbol)
        market_decision_items = await signals.list_market_decisions(symbol=coin_item.symbol, limit=8)
        coin_market_decision_item = await signals.get_coin_market_decision(coin_item.symbol)

        return FrontendStreamEvent(
            event="asset_snapshot_updated",
            data={
                "stream_id": event.stream_id,
                "source_event_type": event.event_type,
                "coin_id": int(coin_item.id),
                "symbol": str(coin_item.symbol),
                "timeframe": int(event.timeframe),
                "timestamp": event.timestamp.isoformat(),
                "coin": coin_read(coin_item).model_dump(mode="json", by_alias=True),
                "metrics": (
                    coin_metrics_read(metric_item).model_dump(mode="json")
                    if metric_item is not None
                    else None
                ),
                "signal_count": signal_count,
                "signals": [signal_read(item).model_dump(mode="json") for item in signal_items],
                "market_decisions": [market_decision_read(item).model_dump(mode="json") for item in market_decision_items],
                "coin_market_decision": (
                    coin_market_decision_read(coin_market_decision_item).model_dump(mode="json")
                    if coin_market_decision_item is not None
                    else None
                ),
            },
        )

    async def _build_portfolio_snapshot(
        self,
        *,
        event: IrisEvent,
        portfolio: PortfolioQueryService,
    ) -> FrontendStreamEvent:
        state_item = await portfolio.get_state()
        position_items = await portfolio.list_positions(limit=_PORTFOLIO_POSITION_LIMIT)
        action_items = await portfolio.list_actions(limit=_PORTFOLIO_ACTION_LIMIT)
        return FrontendStreamEvent(
            event="portfolio_snapshot_updated",
            data={
                "stream_id": event.stream_id,
                "source_event_type": event.event_type,
                "coin_id": int(event.coin_id),
                "timeframe": int(event.timeframe),
                "timestamp": event.timestamp.isoformat(),
                "state": portfolio_state_read(state_item).model_dump(mode="json"),
                "positions": [portfolio_position_read(item).model_dump(mode="json") for item in position_items],
                "actions": [portfolio_action_read(item).model_dump(mode="json") for item in action_items],
            },
        )

    async def _build_frontend_events(self, event: IrisEvent) -> tuple[FrontendStreamEvent, ...]:
        if event.event_type not in _FRONTEND_EVENT_TYPES:
            return ()

        items: list[FrontendStreamEvent] = []
        async with AsyncUnitOfWork() as uow:
            market_data = MarketDataQueryService(uow.session)
            indicators = IndicatorQueryService(uow.session)
            signals = SignalQueryService(uow.session)
            portfolio = PortfolioQueryService(uow.session)
            if event.event_type in _ASSET_EVENT_TYPES:
                asset_item = await self._build_asset_snapshot(
                    event=event,
                    market_data=market_data,
                    indicators=indicators,
                    signals=signals,
                )
                if asset_item is not None:
                    items.append(asset_item)
            if event.event_type in _PORTFOLIO_EVENT_TYPES:
                items.append(await self._build_portfolio_snapshot(event=event, portfolio=portfolio))
        return tuple(items)

    @staticmethod
    def _resolve_last_id(*, request: Request, cursor: str | None) -> str:
        if cursor:
            return cursor
        last_event_id = request.headers.get("last-event-id")
        if last_event_id:
            return last_event_id
        return "$"

    @staticmethod
    def _serialize_event(*, stream_id: str, event_name: str, payload: dict[str, object]) -> str:
        return (
            f"id: {stream_id}\n"
            f"event: {event_name}\n"
            f"data: {json.dumps(payload, ensure_ascii=True, sort_keys=True)}\n\n"
        )

    async def iter_events(
        self,
        *,
        request: Request,
        cursor: str | None,
        once: bool,
    ) -> AsyncIterator[str]:
        client = AsyncRedis.from_url(self._redis_url, decode_responses=True)
        last_id = self._resolve_last_id(request=request, cursor=cursor)
        try:
            while not await request.is_disconnected():
                records = await client.xread({self._stream_name: last_id}, count=20, block=1000)
                if not records:
                    yield ": keepalive\n\n"
                    continue
                for _, messages in records:
                    for stream_id, fields in messages:
                        event = parse_stream_message(stream_id, fields)
                        last_id = stream_id
                        frontend_events = await self._build_frontend_events(event)
                        if not frontend_events:
                            continue
                        for frontend_event in frontend_events:
                            yield self._serialize_event(
                                stream_id=stream_id,
                                event_name=frontend_event.event,
                                payload=frontend_event.data,
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
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
