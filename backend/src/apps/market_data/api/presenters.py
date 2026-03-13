from __future__ import annotations

from typing import Any

from src.apps.market_data.api.contracts import CoinJobAcceptedRead, CoinRead, PriceHistoryRead
from src.core.http.operation_store import OperationDispatchResult


def coin_read(item: Any) -> CoinRead:
    if isinstance(item, dict):
        return CoinRead.model_validate(item)
    candles = getattr(item, "candles", getattr(item, "candles_config", ()))
    sector = getattr(item, "sector", None)
    if sector is None:
        sector = getattr(item, "sector_code", None)
    return CoinRead.model_validate(
        {
            "id": int(item.id),
            "symbol": item.symbol,
            "name": item.name,
            "asset_type": item.asset_type,
            "theme": item.theme,
            "sector": sector,
            "source": item.source,
            "enabled": bool(item.enabled),
            "sort_order": int(item.sort_order),
            "auto_watch_enabled": bool(getattr(item, "auto_watch_enabled", False)),
            "auto_watch_source": getattr(item, "auto_watch_source", None),
            "created_at": item.created_at,
            "history_backfill_completed_at": getattr(item, "history_backfill_completed_at", None),
            "last_history_sync_at": getattr(item, "last_history_sync_at", None),
            "next_history_sync_at": getattr(item, "next_history_sync_at", None),
            "last_history_sync_error": getattr(item, "last_history_sync_error", None),
            "candles": [
                {
                    "interval": candle.interval,
                    "retention_bars": int(candle.retention_bars),
                }
                for candle in candles
            ],
        }
    )


def price_history_read(item: Any) -> PriceHistoryRead:
    if isinstance(item, dict):
        return PriceHistoryRead.model_validate(item)
    return PriceHistoryRead.model_validate(
        {
            "coin_id": int(item.coin_id),
            "interval": item.interval,
            "timestamp": item.timestamp,
            "price": float(item.price),
            "volume": float(item.volume) if item.volume is not None else None,
        }
    )


def coin_job_accepted_read(
    *,
    dispatch_result: OperationDispatchResult,
    symbol: str,
    mode: str,
    force: bool,
) -> CoinJobAcceptedRead:
    operation = dispatch_result.operation
    return CoinJobAcceptedRead.model_validate(
        {
            "operation_id": operation.operation_id,
            "accepted_at": operation.accepted_at,
            "correlation_id": operation.correlation_id,
            "deduplicated": dispatch_result.deduplicated,
            "message": dispatch_result.message,
            "symbol": symbol,
            "mode": mode,
            "force": force,
        }
    )


__all__ = ["coin_job_accepted_read", "coin_read", "price_history_read"]
