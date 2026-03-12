from __future__ import annotations

from datetime import timezone

from app.apps.market_data.schemas import PriceHistoryCreate


def test_market_data_schema_defaults_use_utc_now() -> None:
    payload = PriceHistoryCreate(price=123.0)
    assert payload.timestamp.tzinfo == timezone.utc
