from datetime import UTC, datetime

import pytest
from iris.apps.anomalies.consumers.sector_anomaly_consumer import SectorAnomalyConsumer
from iris.apps.anomalies.models import MarketAnomaly, MarketStructureSnapshot
from iris.apps.anomalies.tasks.anomaly_enrichment_tasks import market_structure_anomaly_scan
from iris.runtime.streams.publisher import flush_publisher
from iris.runtime.streams.types import IrisEvent
from redis import Redis
from sqlalchemy import select

from tests.market_data_support import fetch_candle_points


def _insert_snapshot_series(db, *, coin_id: int, symbol: str, timeframe: int, venue: str, rows: list[dict[str, float | datetime]]) -> None:
    for row in rows:
        db.add(
            MarketStructureSnapshot(
                coin_id=coin_id,
                symbol=symbol,
                timeframe=timeframe,
                venue=venue,
                timestamp=row["timestamp"],
                last_price=float(row["last_price"]),
                mark_price=float(row["mark_price"]),
                index_price=float(row["index_price"]),
                funding_rate=float(row["funding_rate"]),
                open_interest=float(row["open_interest"]),
                basis=float(row["basis"]),
                liquidations_long=float(row["liquidations_long"]),
                liquidations_short=float(row["liquidations_short"]),
                volume=float(row["volume"]),
                payload_json={},
            )
        )
    db.commit()


def _build_rows(*, timestamps: list[datetime], prices: list[float], funding: list[float], open_interest: list[float], basis: list[float], liq_long: list[float], liq_short: list[float]) -> list[dict[str, float | datetime]]:
    return [
        {
            "timestamp": timestamp,
            "last_price": price,
            "mark_price": price * (1.0 + basis_value),
            "index_price": price,
            "funding_rate": funding_value,
            "open_interest": open_interest_value,
            "basis": basis_value,
            "liquidations_long": liq_long_value,
            "liquidations_short": liq_short_value,
            "volume": 1000.0,
        }
        for timestamp, price, funding_value, open_interest_value, basis_value, liq_long_value, liq_short_value in zip(
            timestamps,
            prices,
            funding,
            open_interest,
            basis,
            liq_long,
            liq_short,
            strict=False,
        )
    ]


@pytest.mark.asyncio
async def test_market_structure_anomaly_scan_persists_and_publishes(db_session, seeded_market, settings) -> None:
    coin_id = int(seeded_market["ETHUSD_EVT"]["coin_id"])
    candles = fetch_candle_points(db_session, coin_id, 15, 18)
    symbol = "ETHUSD_EVT"
    timestamps = [candle.timestamp for candle in candles[-12:]]
    base_prices = [float(candle.close) for candle in candles[-12:]]

    _insert_snapshot_series(
        db_session,
        coin_id=coin_id,
        symbol=symbol,
        timeframe=15,
        venue="binance",
        rows=_build_rows(
            timestamps=timestamps,
            prices=[*base_prices[:-1], base_prices[-1] * 1.026],
            funding=[0.00008 for _ in range(11)] + [0.00110],
            open_interest=[16000.0 + (index * 120.0) for index in range(11)] + [24400.0],
            basis=[0.0004 for _ in range(11)] + [0.0055],
            liq_long=[90.0 for _ in range(11)] + [4100.0],
            liq_short=[70.0 for _ in range(11)] + [180.0],
        ),
    )
    _insert_snapshot_series(
        db_session,
        coin_id=coin_id,
        symbol=symbol,
        timeframe=15,
        venue="bybit",
        rows=_build_rows(
            timestamps=timestamps,
            prices=[price * 1.0004 for price in base_prices[:-1]] + [base_prices[-1] * 0.992],
            funding=[0.00007 for _ in range(11)] + [0.00118],
            open_interest=[15800.0 + (index * 110.0) for index in range(11)] + [23750.0],
            basis=[0.0003 for _ in range(11)] + [-0.0038],
            liq_long=[85.0 for _ in range(11)] + [3850.0],
            liq_short=[65.0 for _ in range(11)] + [170.0],
        ),
    )

    result = await market_structure_anomaly_scan(
        trigger_coin_id=coin_id,
        timeframe=15,
        timestamp=timestamps[-1].isoformat(),
        trigger_anomaly_id=41,
    )
    assert result["status"] == "ok"
    assert int(result["created"]) >= 1
    assert flush_publisher(timeout=5.0)

    db_session.expire_all()
    anomalies = db_session.scalars(
        select(MarketAnomaly)
        .where(MarketAnomaly.coin_id == coin_id, MarketAnomaly.timeframe == 15)
        .order_by(MarketAnomaly.detected_at.desc())
        .limit(20)
    ).all()
    assert anomalies
    assert {item.anomaly_type for item in anomalies} & {
        "funding_open_interest_anomaly",
        "cross_exchange_dislocation",
        "liquidation_cascade",
    }
    assert any(item.payload_json.get("source_pipeline") == "market_structure_scan" for item in anomalies)

    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        messages = redis_client.xrange(settings.event_stream_name, "-", "+")
        anomaly_messages = [fields for _, fields in messages if fields["event_type"] == "anomaly_detected"]
        assert anomaly_messages
        assert any("market_structure_scan" in item["payload"] for item in anomaly_messages)
    finally:
        redis_client.close()


@pytest.mark.asyncio
async def test_sector_consumer_enqueues_market_structure_scan_for_high_severity(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def _fake_enqueue(task, **kwargs):
        calls.append((getattr(task, "kiq_name", getattr(task, "__name__", "task")), kwargs))

    monkeypatch.setattr(
        "iris.apps.anomalies.consumers.sector_anomaly_consumer.enqueue_task",
        _fake_enqueue,
    )

    event = IrisEvent(
        stream_id="1-0",
        event_type="anomaly_detected",
        coin_id=11,
        timeframe=15,
        timestamp=datetime(2026, 3, 12, 12, 0, tzinfo=UTC),
        payload={
            "anomaly_id": 9,
            "type": "price_spike",
            "severity": "critical",
            "source_pipeline": "fast_path",
        },
    )

    await SectorAnomalyConsumer().handle_event(event)

    task_names = [name for name, _ in calls]
    assert task_names[0].endswith("anomaly_enrichment_job") or "anomaly_enrichment_job" in task_names[0]
    assert task_names[1].endswith("sector_anomaly_scan") or "sector_anomaly_scan" in task_names[1]
    assert task_names[2].endswith("market_structure_anomaly_scan") or "market_structure_anomaly_scan" in task_names[2]
