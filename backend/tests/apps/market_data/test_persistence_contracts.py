from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import timedelta

import pytest
from src.apps.market_data.query_services import MarketDataQueryService
from src.apps.market_data.schemas import CoinCreate, PriceHistoryCreate
from src.apps.market_data.services import MarketDataService
from src.core.db.persistence import PERSISTENCE_LOGGER
from src.core.db.uow import SessionUnitOfWork


@pytest.mark.asyncio
async def test_market_data_query_returns_immutable_read_models(async_db_session, seeded_market) -> None:
    latest_timestamp = seeded_market["BTCUSD_EVT"]["latest_timestamp"]
    assert latest_timestamp is not None

    async with SessionUnitOfWork(async_db_session) as uow:
        created = await MarketDataService(uow).create_coin(
            CoinCreate(
                symbol="ATOMUSD_EVT",
                name="Cosmos Event Test",
                asset_type="crypto",
                theme="layer1",
                sector="infrastructure",
                source="fixture",
                sort_order=7,
                candles=[{"interval": "15m", "retention_bars": 120}],
            )
        )
        created_history = await MarketDataService(uow).create_price_history(
            symbol=created.symbol,
            payload=PriceHistoryCreate(
                interval="15m",
                timestamp=latest_timestamp + timedelta(minutes=15),
                price=14.25,
                volume=55.0,
            ),
        )
        coins = await MarketDataQueryService(uow.session).list_coins()
        history = await MarketDataQueryService(uow.session).list_price_history(created.symbol, "15m")

    coin = next(item for item in coins if item.symbol == created.symbol)
    assert created_history is not None
    assert len(history) == 1
    assert history[0].price == 14.25
    assert coin.symbol == "ATOMUSD_EVT"
    assert coin.candles[0].interval == "15m"
    with pytest.raises(FrozenInstanceError):
        coin.symbol = "changed"
    with pytest.raises(FrozenInstanceError):
        coin.candles[0].retention_bars = 1
    with pytest.raises(FrozenInstanceError):
        history[0].price = 0.0


@pytest.mark.asyncio
async def test_market_data_persistence_logs_cover_query_repo_and_uow(async_db_session, monkeypatch) -> None:
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
        await MarketDataService(uow).create_coin(
            CoinCreate(
                symbol="NEARUSD_EVT",
                name="Near Event Test",
                asset_type="crypto",
                theme="layer1",
                sector="infrastructure",
                source="fixture",
                sort_order=8,
                candles=[{"interval": "15m", "retention_bars": 240}],
            )
        )
        items = await MarketDataQueryService(uow.session).list_coins()

    assert items
    assert "uow.begin" in events
    assert "repo.add_market_data_coin" in events
    assert "query.list_market_data_coins" in events
    assert "uow.commit" in events
