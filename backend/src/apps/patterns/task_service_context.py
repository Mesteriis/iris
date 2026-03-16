from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.cross_market.models import SectorMetric
from src.apps.indicators.models import CoinMetrics
from src.apps.market_data.domain import ensure_utc, utc_now
from src.apps.market_data.models import Coin
from src.apps.patterns.domain.context import (
    _cycle_alignment as context_cycle_alignment,
)
from src.apps.patterns.domain.context import (
    _liquidity_score,
    _sector_alignment,
    _volatility_alignment,
    calculate_priority_score,
)
from src.apps.patterns.domain.context import (
    _regime_alignment as context_regime_alignment,
)
from src.apps.patterns.domain.semantics import is_cluster_signal, is_pattern_signal, pattern_bias, slug_from_signal_type
from src.apps.patterns.domain.success import PatternSuccessSnapshot
from src.apps.patterns.models import MarketCycle
from src.apps.signals.models import Signal
from src.core.db.uow import BaseAsyncUnitOfWork


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    return 0


class _PatternContextSupport(Protocol):
    @property
    def session(self) -> AsyncSession: ...

    _uow: BaseAsyncUnitOfWork

    async def _enrich_signal_context(
        self,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: object | None = None,
    ) -> dict[str, object]: ...

    async def _signal_regime(self, *, metrics: CoinMetrics | None, timeframe: int) -> str | None: ...

    async def _pattern_success_cache(
        self,
        *,
        timeframe: int,
        slugs: set[str],
        regimes: set[str] | None = None,
    ) -> dict[tuple[str, str], PatternSuccessSnapshot]: ...

    async def _pattern_success_snapshot(
        self,
        *,
        slug: str,
        timeframe: int,
        market_regime: str | None,
        snapshot_cache: dict[tuple[str, str], PatternSuccessSnapshot] | None = None,
    ) -> PatternSuccessSnapshot | None: ...


class PatternContextMixin:
    async def _enrich_signal_context(
        self: _PatternContextSupport,
        *,
        coin_id: int,
        timeframe: int,
        candle_timestamp: object | None = None,
    ) -> dict[str, object]:
        stmt = select(Signal).where(Signal.coin_id == coin_id, Signal.timeframe == timeframe)
        if candle_timestamp is not None:
            normalized_timestamp = (
                ensure_utc(datetime.fromisoformat(candle_timestamp))
                if isinstance(candle_timestamp, str)
                else candle_timestamp
            )
            stmt = stmt.where(Signal.candle_timestamp == normalized_timestamp)
        signals = (await self.session.execute(stmt)).scalars().all()
        if not signals:
            return {"status": "skipped", "reason": "signals_not_found", "coin_id": coin_id, "timeframe": timeframe}

        metrics = await self.session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id).limit(1))
        coin = await self.session.scalar(select(Coin).where(Coin.id == coin_id).limit(1))
        sector_metric = (
            await self.session.get(SectorMetric, (int(coin.sector_id), timeframe))
            if coin is not None and coin.sector_id is not None
            else None
        )
        cycle = await self.session.get(MarketCycle, (coin_id, timeframe))
        cluster_timestamps = {
            signal.candle_timestamp for signal in signals if is_cluster_signal(str(signal.signal_type))
        }
        signal_regimes: dict[int, str | None] = {}
        unique_slugs = {
            slug for signal in signals if (slug := slug_from_signal_type(str(signal.signal_type))) is not None
        }
        regime_values: set[str] = set()
        for signal in signals:
            resolved_regime = signal.market_regime or await self._signal_regime(
                metrics=metrics, timeframe=int(signal.timeframe)
            )
            signal_regimes[int(signal.id)] = resolved_regime
            if resolved_regime is not None:
                regime_values.add(resolved_regime)
        snapshot_cache = await self._pattern_success_cache(
            timeframe=timeframe,
            slugs=unique_slugs,
            regimes=regime_values,
        )
        for signal in signals:
            slug = slug_from_signal_type(str(signal.signal_type))
            bias = pattern_bias(slug or str(signal.signal_type), fallback_price_delta=float(signal.confidence) - 0.5)
            signal_regime = signal_regimes.get(int(signal.id))
            regime_alignment = context_regime_alignment(signal_regime, bias)
            volatility_alignment = _volatility_alignment(str(signal.signal_type), metrics)
            liquidity_score = _liquidity_score(metrics)
            sector_alignment = _sector_alignment(sector_metric, bias)
            cycle_alignment = context_cycle_alignment(cycle, bias)
            snapshot = (
                await self._pattern_success_snapshot(
                    slug=slug,
                    timeframe=int(signal.timeframe),
                    market_regime=signal_regime,
                    snapshot_cache=snapshot_cache,
                )
                if slug is not None
                else None
            )
            temperature = float(snapshot.temperature) if snapshot is not None and snapshot.temperature != 0 else 1.0
            cluster_bonus = (
                1.15
                if signal.candle_timestamp in cluster_timestamps and is_pattern_signal(str(signal.signal_type))
                else 1.0
            )
            context_score = max(
                temperature
                * volatility_alignment
                * liquidity_score
                * cluster_bonus
                * sector_alignment
                * cycle_alignment,
                0.0,
            )
            signal.regime_alignment = regime_alignment
            signal.context_score = context_score
            signal.priority_score = calculate_priority_score(
                confidence=float(signal.confidence),
                pattern_temperature=temperature,
                regime_alignment=regime_alignment,
                volatility_alignment=volatility_alignment * cluster_bonus * sector_alignment * cycle_alignment,
                liquidity_score=liquidity_score,
            )
        await self._uow.flush()
        return {"status": "ok", "coin_id": coin_id, "timeframe": timeframe, "signals": len(signals)}

    async def _refresh_recent_signal_contexts(
        self: _PatternContextSupport,
        *,
        lookback_days: int = 30,
    ) -> dict[str, object]:
        recent_cutoff = utc_now() - timedelta(days=max(lookback_days, 1))
        rows = (
            await self.session.execute(
                select(Signal.coin_id, Signal.timeframe, Signal.candle_timestamp)
                .where(Signal.candle_timestamp >= recent_cutoff)
                .distinct()
                .order_by(Signal.coin_id.asc(), Signal.timeframe.asc(), Signal.candle_timestamp.asc())
            )
        ).all()
        updated = 0
        for row in rows:
            result = await self._enrich_signal_context(
                coin_id=int(row.coin_id),
                timeframe=int(row.timeframe),
                candle_timestamp=row.candle_timestamp,
            )
            updated += _int_value(result.get("signals", 0))
        return {"status": "ok", "signals": updated, "groups": len(rows)}


__all__ = ["PatternContextMixin"]
