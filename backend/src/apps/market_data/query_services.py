from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.market_data.domain import utc_now
from src.apps.market_data.models import Coin
from src.apps.market_data.read_models import (
    CoinReadModel,
    PriceHistoryReadModel,
    coin_read_model_from_orm,
    price_history_read_model,
)
from src.apps.market_data.candles import interval_to_timeframe
from src.apps.market_data.repositories import CandleRepository, latest_candle_pair_map
from src.apps.market_data.support import (
    get_base_candle_config,
    get_interval_retention_bars,
    resolve_history_interval,
)
from src.core.db.persistence import AsyncQueryService


class MarketDataQueryService(AsyncQueryService):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, domain="market_data", service_name="MarketDataQueryService")
        self._candles = CandleRepository(session)

    async def get_coin_read_by_symbol(
        self,
        symbol: str,
        *,
        include_deleted: bool = False,
    ) -> CoinReadModel | None:
        normalized_symbol = symbol.strip().upper()
        self._log_debug(
            "query.get_market_data_coin_read_by_symbol",
            mode="read",
            symbol=normalized_symbol,
            include_deleted=include_deleted,
        )
        stmt = select(Coin).where(Coin.symbol == normalized_symbol)
        if not include_deleted:
            stmt = stmt.where(Coin.deleted_at.is_(None))
        coin = await self.session.scalar(stmt.limit(1))
        if coin is None:
            self._log_debug("query.get_market_data_coin_read_by_symbol.result", mode="read", found=False)
            return None
        item = coin_read_model_from_orm(coin)
        self._log_debug("query.get_market_data_coin_read_by_symbol.result", mode="read", found=True)
        return item

    async def list_coins(
        self,
        *,
        enabled_only: bool = False,
        include_deleted: bool = False,
    ) -> tuple[CoinReadModel, ...]:
        self._log_debug(
            "query.list_market_data_coins",
            mode="read",
            enabled_only=enabled_only,
            include_deleted=include_deleted,
        )
        stmt = select(Coin)
        if not include_deleted:
            stmt = stmt.where(Coin.deleted_at.is_(None))
        if enabled_only:
            stmt = stmt.where(Coin.enabled.is_(True))
        stmt = stmt.order_by(Coin.sort_order.asc(), Coin.symbol.asc())
        rows = (await self.session.execute(stmt)).scalars().all()
        items = tuple(coin_read_model_from_orm(item) for item in rows)
        self._log_debug("query.list_market_data_coins.result", mode="read", count=len(items))
        return items

    async def list_price_history(
        self,
        symbol: str,
        interval: str | None = None,
    ) -> tuple[PriceHistoryReadModel, ...]:
        normalized_symbol = symbol.strip().upper()
        self._log_debug(
            "query.list_market_data_price_history",
            mode="read",
            symbol=normalized_symbol,
            interval=interval,
            loading_profile="base",
        )
        coin = await self.session.scalar(
            select(Coin).where(Coin.symbol == normalized_symbol, Coin.deleted_at.is_(None)).limit(1)
        )
        if coin is None:
            self._log_debug("query.list_market_data_price_history.result", mode="read", count=0, found=False)
            return ()
        resolved_interval = resolve_history_interval(coin, interval)
        timeframe = interval_to_timeframe(resolved_interval)
        retention_bars = get_interval_retention_bars(coin, resolved_interval)
        rows = await self._candles.list_recent_rows(
            coin_id=int(coin.id),
            timeframe=timeframe,
            limit=max(retention_bars, 1),
        )
        items = tuple(
            price_history_read_model(
                coin_id=int(coin.id),
                interval=resolved_interval,
                timestamp=row.timestamp,
                price=float(row.close),
                volume=float(row.volume) if row.volume is not None else None,
            )
            for row in reversed(rows)
        )
        self._log_debug("query.list_market_data_price_history.result", mode="read", count=len(items), found=True)
        return items

    async def list_coin_symbols_pending_backfill(
        self,
        *,
        symbol: str | None = None,
    ) -> list[str]:
        self._log_debug("query.list_market_data_pending_backfill_symbols", mode="read", symbol=symbol)
        coins = await self._list_enabled_sync_coins(symbol=symbol)
        if not coins:
            return []
        latest_map = await self._candles.list_latest_timestamps_for_pairs(latest_candle_pair_map(coins=coins))
        items = [
            coin.symbol
            for coin in coins
            if coin.history_backfill_completed_at is None or not self._has_base_candle(coin, latest_map=latest_map)
        ]
        self._log_debug("query.list_market_data_pending_backfill_symbols.result", mode="read", count=len(items))
        return items

    async def list_coin_symbols_ready_for_latest_sync(self) -> list[str]:
        self._log_debug("query.list_market_data_ready_for_latest_sync_symbols", mode="read")
        coins = (
            (
                await self.session.execute(
                    select(Coin)
                    .where(
                        Coin.deleted_at.is_(None),
                        Coin.enabled.is_(True),
                        Coin.history_backfill_completed_at.is_not(None),
                    )
                    .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
                )
            )
            .scalars()
            .all()
        )
        if not coins:
            return []
        latest_map = await self._candles.list_latest_timestamps_for_pairs(latest_candle_pair_map(coins=coins))
        items = [coin.symbol for coin in coins if self._has_base_candle(coin, latest_map=latest_map)]
        self._log_debug("query.list_market_data_ready_for_latest_sync_symbols.result", mode="read", count=len(items))
        return items

    async def get_next_pending_backfill_due_at(self) -> datetime | None:
        self._log_debug("query.get_next_market_data_pending_backfill_due_at", mode="read")
        now = utc_now()
        coins = await self._list_enabled_sync_coins()
        if not coins:
            self._log_debug("query.get_next_market_data_pending_backfill_due_at.result", mode="read", found=False)
            return None
        latest_map = await self._candles.list_latest_timestamps_for_pairs(latest_candle_pair_map(coins=coins))
        pending_due_at: list[datetime] = []
        for coin in coins:
            if coin.history_backfill_completed_at is None or not self._has_base_candle(coin, latest_map=latest_map):
                if coin.next_history_sync_at is None or coin.next_history_sync_at <= now:
                    self._log_debug(
                        "query.get_next_market_data_pending_backfill_due_at.result",
                        mode="read",
                        found=True,
                        due_at=now.isoformat(),
                    )
                    return now
                pending_due_at.append(coin.next_history_sync_at)
        due_at = min(pending_due_at) if pending_due_at else None
        self._log_debug(
            "query.get_next_market_data_pending_backfill_due_at.result",
            mode="read",
            found=due_at is not None,
            due_at=due_at.isoformat() if due_at is not None else None,
        )
        return due_at

    async def _list_enabled_sync_coins(self, *, symbol: str | None = None) -> list[Coin]:
        stmt = (
            select(Coin)
            .where(Coin.deleted_at.is_(None), Coin.enabled.is_(True))
            .order_by(Coin.sort_order.asc(), Coin.symbol.asc())
        )
        if symbol is not None:
            stmt = stmt.where(Coin.symbol == symbol.strip().upper())
        return list((await self.session.execute(stmt)).scalars().all())

    @staticmethod
    def _has_base_candle(
        coin: Coin,
        *,
        latest_map: dict[tuple[int, int], datetime],
    ) -> bool:
        timeframe = interval_to_timeframe(str(get_base_candle_config(coin)["interval"]))
        return latest_map.get((int(coin.id), timeframe)) is not None


__all__ = ["MarketDataQueryService"]
