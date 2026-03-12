from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

import src.apps.signals.services as signal_services_module
from src.apps.signals.query_services import SignalQueryService
from src.core.db.persistence import PERSISTENCE_LOGGER
from src.core.db.uow import SessionUnitOfWork


@pytest.mark.asyncio
async def test_signal_query_returns_immutable_read_models(async_db_session, seeded_api_state) -> None:
    del seeded_api_state
    rows = await SignalQueryService(async_db_session).list_signals(symbol="BTCUSD_EVT", limit=10)

    assert rows
    item = rows[0]
    assert item.symbol == "BTCUSD_EVT"
    assert isinstance(item.cluster_membership, tuple)
    with pytest.raises(FrozenInstanceError):
        item.signal_type = "changed"


@pytest.mark.asyncio
async def test_signal_persistence_logs_cover_query_service_and_uow(async_db_session) -> None:
    events: list[str] = []

    def _debug(message: str, *args, **kwargs) -> None:
        del args, kwargs
        events.append(message)

    def _log(level: int, message: str, *args, **kwargs) -> None:
        del level, args, kwargs
        events.append(message)

    original_debug = PERSISTENCE_LOGGER.debug
    original_log = PERSISTENCE_LOGGER.log
    PERSISTENCE_LOGGER.debug = _debug
    PERSISTENCE_LOGGER.log = _log
    try:
        async with SessionUnitOfWork(async_db_session) as uow:
            await SignalQueryService(uow.session).list_signals(limit=5)
    finally:
        PERSISTENCE_LOGGER.debug = original_debug
        PERSISTENCE_LOGGER.log = original_log

    assert "uow.begin" in events
    assert "query.list_signals" in events
    assert "uow.rollback_uncommitted" in events


def test_signal_services_exports_no_public_async_query_wrappers() -> None:
    forbidden_exports = (
        "get_coin_backtests_async",
        "get_coin_decision_async",
        "get_coin_final_signal_async",
        "get_coin_market_decision_async",
        "list_backtests_async",
        "list_decisions_async",
        "list_enriched_signals_async",
        "list_final_signals_async",
        "list_market_decisions_async",
        "list_strategies_async",
        "list_strategy_performance_async",
        "list_top_backtests_async",
        "list_top_decisions_async",
        "list_top_final_signals_async",
        "list_top_market_decisions_async",
        "list_top_signals_async",
    )

    for export_name in forbidden_exports:
        assert not hasattr(signal_services_module, export_name), export_name
