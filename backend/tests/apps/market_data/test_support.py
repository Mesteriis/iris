from datetime import datetime, timezone

from src.apps.market_data.models import Coin
from src.apps.market_data.schemas import CandleConfig
from src.apps.market_data.support import (
    get_base_candle_config,
    get_coin_base_timeframe,
    get_interval_retention_bars,
    publish_candle_events,
    resolve_history_interval,
    serialize_candles,
)


def test_market_data_support_config_and_event_helpers(monkeypatch) -> None:
    published: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr("src.apps.market_data.support.publish_event", lambda event_type, payload: published.append((event_type, payload)))

    default_coin = Coin(
        symbol="DEFAULT_EVT",
        name="Default Asset",
        asset_type="crypto",
        theme="core",
        source="fixture",
        enabled=True,
        sort_order=0,
        sector_code="core",
        candles_config=[],
    )
    configured_coin = Coin(
        symbol="BTCUSD_EVT",
        name="Bitcoin Event Test",
        asset_type="crypto",
        theme="core",
        source="fixture",
        enabled=True,
        sort_order=1,
        sector_code="store_of_value",
        candles_config=[
            {"interval": "1d", "retention_bars": 3650},
            {"interval": "15m", "retention_bars": 20160},
            {"interval": "1h", "retention_bars": 8760},
        ],
    )

    assert get_base_candle_config(default_coin) == {"interval": "15m", "retention_bars": 20160}

    serialized = serialize_candles(
        [
            CandleConfig(interval="1h", retention_bars=10),
            {"interval": "15m", "retention_bars": 20},
        ]
    )
    assert serialized[0]["interval"] == "1h"
    assert get_base_candle_config(configured_coin)["interval"] == "15m"
    assert get_interval_retention_bars(configured_coin, "1d") == 3650
    assert get_interval_retention_bars(configured_coin, "15m") == 20160
    assert get_coin_base_timeframe(configured_coin) == 15
    assert resolve_history_interval(configured_coin) == "15m"
    assert resolve_history_interval(configured_coin, " 1H ") == "1h"

    publish_candle_events(
        coin_id=1,
        timeframe=15,
        timestamp=datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc),
        created_count=3,
        source="manual",
    )
    assert [event_type for event_type, _ in published] == ["candle_inserted", "candle_closed"]
