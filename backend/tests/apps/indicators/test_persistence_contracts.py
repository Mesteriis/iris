from dataclasses import FrozenInstanceError

import iris.apps.indicators.query_services as indicator_query_module
import pytest
from iris.apps.indicators.query_services import IndicatorQueryService
from iris.apps.indicators.repositories import IndicatorMetricsRepository
from iris.apps.market_data.models import Coin
from iris.core.db.persistence import PERSISTENCE_LOGGER
from iris.core.db.uow import SessionUnitOfWork
from sqlalchemy import select


class _AsyncRedisClient:
    def __init__(self, messages: list[tuple[str, dict[str, str]]]) -> None:
        self._messages = messages

    async def xrevrange(self, _stream: str, _max: str, _min: str, *, count: int):
        return self._messages[:count]

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_indicator_query_returns_immutable_read_models(async_db_session, seeded_api_state, monkeypatch) -> None:
    btc = seeded_api_state["btc"]
    messages = [
        (
            "1-0",
            {
                "event_type": "market_regime_changed",
                "coin_id": str(btc.id),
                "timeframe": "60",
                "timestamp": seeded_api_state["signal_timestamp"].isoformat(),
                "payload": "{\"regime\": \"bull_trend\", \"confidence\": 0.83}",
            },
        )
    ]
    monkeypatch.setattr(indicator_query_module, "_stream_client", lambda: _AsyncRedisClient(messages))

    metrics = await IndicatorQueryService(async_db_session).list_coin_metrics()
    radar = await IndicatorQueryService(async_db_session).get_market_radar(limit=5)

    btc_metrics = next(item for item in metrics if item.symbol == "BTCUSD_EVT")
    with pytest.raises(FrozenInstanceError):
        btc_metrics.symbol = "changed"
    with pytest.raises(TypeError):
        btc_metrics.market_regime_details["15"] = {}
    with pytest.raises(FrozenInstanceError):
        radar.hot_coins[0].symbol = "changed"


@pytest.mark.asyncio
async def test_indicator_persistence_logs_cover_query_repo_and_uow(async_db_session, seeded_api_state, monkeypatch) -> None:
    btc_id = int((await async_db_session.execute(select(Coin.id).where(Coin.symbol == "BTCUSD_EVT").limit(1))).scalar_one())
    events: list[str] = []

    def _debug(message: str, *args, **kwargs) -> None:
        del args, kwargs
        events.append(message)

    def _log(level: int, message: str, *args, **kwargs) -> None:
        del level, args, kwargs
        events.append(message)

    monkeypatch.setattr(PERSISTENCE_LOGGER, "debug", _debug)
    monkeypatch.setattr(PERSISTENCE_LOGGER, "log", _log)

    async with SessionUnitOfWork(async_db_session) as uow:
        await IndicatorMetricsRepository(uow.session).ensure_row(btc_id)
        items = await IndicatorQueryService(uow.session).list_coin_metrics()
        await uow.commit()

    assert items
    assert "uow.begin" in events
    assert "repo.ensure_indicator_metrics_row" in events
    assert "query.list_indicator_coin_metrics" in events
    assert "uow.commit" in events
