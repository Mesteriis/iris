from __future__ import annotations

from datetime import datetime, timedelta, timezone
from collections.abc import Sequence

from polyfactory.factories.dataclass_factory import DataclassFactory
from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.fields import Use

from app.apps.market_data.repos import CandlePoint
from app.apps.market_data.schemas import CoinCreate, PriceHistoryCreate
from tests.factories.base import fake


def _event_symbol() -> str:
    return f"{fake.lexify(text='????').upper()}USD_EVT"


class CoinCreateFactory(ModelFactory[CoinCreate]):
    __model__ = CoinCreate
    __check_model__ = False

    symbol = Use(_event_symbol)
    name = Use(lambda: f"{fake.word().title()} {fake.word().title()} Test")
    asset_type = "crypto"
    theme = Use(lambda: fake.random_element(elements=("core", "layer1", "payments", "defi")))
    sector = Use(lambda: fake.random_element(elements=("store_of_value", "smart_contract", "high_beta", "payments")))
    source = "fixture"
    enabled = True
    sort_order = Use(lambda: fake.random_int(min=0, max=20))
    candles = Use(
        lambda: [
            {"interval": "15m", "retention_bars": 20160},
            {"interval": "1h", "retention_bars": 8760},
            {"interval": "4h", "retention_bars": 4380},
            {"interval": "1d", "retention_bars": 3650},
        ]
    )


class PriceHistoryCreateFactory(ModelFactory[PriceHistoryCreate]):
    __model__ = PriceHistoryCreate
    __check_model__ = False

    interval = Use(lambda: fake.random_element(elements=("15m", "1h")))
    timestamp = Use(lambda: datetime.now(timezone.utc))
    price = Use(lambda: round(fake.pyfloat(min_value=10, max_value=200000, positive=True), 2))
    volume = Use(lambda: round(fake.pyfloat(min_value=1, max_value=100000, positive=True), 2))


class CandlePointFactory(DataclassFactory[CandlePoint]):
    __check_model__ = False

    timestamp = Use(lambda: datetime.now(timezone.utc))
    open = Use(lambda: round(fake.pyfloat(min_value=10, max_value=200000, positive=True), 4))
    high = Use(lambda: round(fake.pyfloat(min_value=10, max_value=200000, positive=True), 4))
    low = Use(lambda: round(fake.pyfloat(min_value=10, max_value=200000, positive=True), 4))
    close = Use(lambda: round(fake.pyfloat(min_value=10, max_value=200000, positive=True), 4))
    volume = Use(lambda: round(fake.pyfloat(min_value=10, max_value=500000, positive=True), 4))


def build_candle_points(
    *,
    closes: Sequence[float],
    volumes: Sequence[float] | None = None,
    timeframe_minutes: int = 15,
    start: datetime | None = None,
) -> list[CandlePoint]:
    base = start or datetime(2026, 3, 12, 12, 0, tzinfo=timezone.utc)
    series: list[CandlePoint] = []
    previous_close = float(closes[0]) if closes else 100.0
    for index, close in enumerate(closes):
        volume = float(volumes[index]) if volumes is not None else round(fake.pyfloat(min_value=500, max_value=5000, positive=True), 3)
        open_price = previous_close if index > 0 else float(close) * (1 + fake.pyfloat(min_value=-0.003, max_value=0.003))
        high = max(open_price, float(close)) * (1 + float(fake.pyfloat(min_value=0.001, max_value=0.01, positive=True)))
        low = min(open_price, float(close)) * (1 - float(fake.pyfloat(min_value=0.001, max_value=0.01, positive=True)))
        series.append(
            CandlePointFactory.build(
                timestamp=base.replace(second=0, microsecond=0) + timedelta(minutes=timeframe_minutes * index),
                open=round(open_price, 4),
                high=round(high, 4),
                low=round(low, 4),
                close=round(float(close), 4),
                volume=round(volume, 4),
            )
        )
        previous_close = float(close)
    return series
