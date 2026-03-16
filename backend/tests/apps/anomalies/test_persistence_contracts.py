import importlib.util
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest
from iris.apps.anomalies.query_services import AnomalyQueryService
from iris.apps.anomalies.read_models import AnomalyReadModel
from iris.apps.anomalies.repos import AnomalyRepo
from iris.apps.anomalies.schemas import AnomalyDraft
from iris.apps.anomalies.services import AnomalyService
from iris.apps.cross_market.models import CoinRelation, Sector
from iris.apps.market_data.models import Coin
from iris.apps.portfolio.models import PortfolioPosition
from iris.core.db.persistence import PERSISTENCE_LOGGER
from iris.core.db.uow import SessionUnitOfWork


@pytest.fixture(autouse=True)
def isolated_event_stream() -> None:
    yield


def _make_draft(
    *,
    coin_id: int,
    symbol: str,
    anomaly_type: str = "price_spike",
    status: str = "new",
    sector: str | None = "smart_contract",
) -> AnomalyDraft:
    detected_at = datetime(2026, 3, 12, 12, 0, tzinfo=UTC)
    return AnomalyDraft(
        coin_id=coin_id,
        symbol=symbol,
        timeframe=15,
        anomaly_type=anomaly_type,
        severity="high",
        confidence=0.82,
        score=0.88,
        status=status,
        detected_at=detected_at,
        window_start=detected_at - timedelta(hours=1),
        window_end=detected_at,
        market_regime="bull_trend",
        sector=sector,
        summary=f"{anomaly_type} detected",
        payload_json={"context": {"scope": "asset"}, "explainability": {"what_happened": "test"}},
        cooldown_until=detected_at + timedelta(minutes=45),
    )


def _open_position(*, coin_id: int, timeframe: int = 15) -> PortfolioPosition:
    return PortfolioPosition(
        coin_id=coin_id,
        timeframe=timeframe,
        entry_price=100.0,
        position_size=1.0,
        position_value=100.0,
        status="open",
    )


@pytest.mark.asyncio
async def test_anomaly_query_returns_immutable_read_models(async_db_session, seeded_market) -> None:
    eth_coin_id = int(seeded_market["ETHUSD_EVT"]["coin_id"])
    btc_coin_id = int(seeded_market["BTCUSD_EVT"]["coin_id"])

    async with SessionUnitOfWork(async_db_session) as uow:
        repo = AnomalyRepo(uow.session)
        await repo.create_anomaly(_make_draft(coin_id=eth_coin_id, symbol="ETHUSD_EVT"))
        await repo.create_anomaly(
            _make_draft(
                coin_id=btc_coin_id,
                symbol="BTCUSD_EVT",
                anomaly_type="volume_spike",
                sector="store_of_value",
            )
        )
        uow.session.add(_open_position(coin_id=eth_coin_id))
        await uow.commit()

        query_service = AnomalyQueryService(uow.session)
        items = await query_service.list_active_anomalies(limit=10)
        portfolio_items = await query_service.list_portfolio_relevant_anomalies(limit=10)

    assert len(items) == 2
    assert len(portfolio_items) == 1
    assert isinstance(items[0], AnomalyReadModel)
    assert portfolio_items[0].coin_id == eth_coin_id
    with pytest.raises(FrozenInstanceError):
        items[0].summary = "changed"
    with pytest.raises(TypeError):
        items[0].payload_json["context"]["scope"] = "sector"


@pytest.mark.asyncio
async def test_anomaly_service_commits_enrichment_updates(async_db_session, seeded_market) -> None:
    eth_coin_id = int(seeded_market["ETHUSD_EVT"]["coin_id"])

    async with SessionUnitOfWork(async_db_session) as uow:
        repo = AnomalyRepo(uow.session)
        anomaly = await repo.create_anomaly(_make_draft(coin_id=eth_coin_id, symbol="ETHUSD_EVT"))
        uow.session.add(_open_position(coin_id=eth_coin_id))
        await uow.commit()

        result = await AnomalyService(uow).enrich_anomaly(int(anomaly.id))
        enriched = await AnomalyQueryService(uow.session).get_read_by_id(int(anomaly.id))

    assert result.status == "ok"
    assert enriched is not None
    assert enriched.status == "active"
    assert enriched.payload_json["context"]["portfolio_relevant"] is True
    assert enriched.payload_json["explainability"]["enriched_by"] == "enrichment"


@pytest.mark.asyncio
async def test_anomaly_repo_batches_peer_candle_reads(async_db_session, seeded_market, monkeypatch) -> None:
    eth_coin_id = int(seeded_market["ETHUSD_EVT"]["coin_id"])
    btc_coin_id = int(seeded_market["BTCUSD_EVT"]["coin_id"])
    sol_coin_id = int(seeded_market["SOLUSD_EVT"]["coin_id"])
    timestamp = seeded_market["ETHUSD_EVT"]["latest_timestamp"]

    async with SessionUnitOfWork(async_db_session) as uow:
        sector = Sector(name="smart_contract_batching", description="test")
        uow.session.add(sector)
        await uow.flush()

        eth_coin = await uow.session.get(Coin, eth_coin_id)
        sol_coin = await uow.session.get(Coin, sol_coin_id)
        assert eth_coin is not None
        assert sol_coin is not None
        eth_coin.sector_id = int(sector.id)
        eth_coin.sector_code = sector.name
        sol_coin.sector_id = int(sector.id)
        sol_coin.sector_code = sector.name
        uow.session.add(
            CoinRelation(
                leader_coin_id=eth_coin_id,
                follower_coin_id=btc_coin_id,
                correlation=0.88,
                lag_hours=0,
                confidence=0.93,
            )
        )
        await uow.flush()

        repo = AnomalyRepo(uow.session)
        candle_load_calls = 0
        original_load_candles = repo._load_candles

        async def _counted_load_candles(coin_id: int, timeframe: int, limit: int):
            nonlocal candle_load_calls
            candle_load_calls += 1
            return await original_load_candles(coin_id, timeframe, limit)

        monkeypatch.setattr(repo, "_load_candles", _counted_load_candles)
        context = await repo.load_sector_detection_context(
            coin_id=eth_coin_id,
            timeframe=15,
            timestamp=timestamp,
            lookback=24,
        )

    assert context is not None
    assert candle_load_calls == 2
    assert "SOLUSD_EVT" in context.sector_peer_candles
    assert "BTCUSD_EVT" in context.related_peer_candles


@pytest.mark.asyncio
async def test_anomaly_persistence_logs_cover_query_repo_and_uow(async_db_session, seeded_market, monkeypatch) -> None:
    eth_coin_id = int(seeded_market["ETHUSD_EVT"]["coin_id"])
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
        repo = AnomalyRepo(uow.session)
        anomaly = await repo.create_anomaly(_make_draft(coin_id=eth_coin_id, symbol="ETHUSD_EVT"))
        uow.session.add(_open_position(coin_id=eth_coin_id))
        await uow.commit()

        result = await AnomalyService(uow).enrich_anomaly(int(anomaly.id))
        items = await AnomalyQueryService(uow.session).list_active_anomalies(limit=5)

    assert result.status == "ok"
    assert items
    assert "uow.begin" in events
    assert "repo.create_anomaly" in events
    assert "repo.get_anomaly_for_update" in events
    assert "repo.touch_anomaly" in events
    assert "query.list_active_anomalies" in events
    assert "uow.commit" in events


def test_anomaly_selectors_module_is_removed() -> None:
    assert importlib.util.find_spec("iris.apps.anomalies.selectors") is None
