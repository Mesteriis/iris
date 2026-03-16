from src.apps.market_data.domain import ensure_utc, utc_now
from src.apps.signals.engines import evaluate_signal_history_batch
from src.apps.signals.engines.contracts import SignalHistoryCandleInput, SignalHistorySignalInput
from src.apps.signals.history_support import (
    SIGNAL_HISTORY_LOOKBACK_DAYS,
    SIGNAL_HISTORY_RECENT_LIMIT,
    _open_timestamp_from_signal,
)
from src.apps.signals.integrations.market_data import SignalHistoryMarketDataAdapter
from src.apps.signals.models import Signal
from src.apps.signals.repositories import SignalHistoryRepository
from src.apps.signals.services.results import SignalHistoryRefreshResult
from src.core.db.persistence import PersistenceComponent
from src.core.db.uow import BaseAsyncUnitOfWork


class SignalHistoryService(PersistenceComponent):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(
            uow.session,
            component_type="service",
            domain="signals",
            component_name="SignalHistoryService",
        )
        self._history = SignalHistoryRepository(uow.session)
        self._market_data = SignalHistoryMarketDataAdapter(uow)

    async def refresh_history(
        self,
        *,
        lookback_days: int = SIGNAL_HISTORY_LOOKBACK_DAYS,
        coin_id: int | None = None,
        timeframe: int | None = None,
        limit_per_scope: int | None = None,
    ) -> SignalHistoryRefreshResult:
        self._log_debug(
            "service.refresh_signal_history",
            mode="write",
            lookback_days=lookback_days,
            coin_id=coin_id,
            timeframe=timeframe,
            limit_per_scope=limit_per_scope,
        )
        signals = await self._history.list_signals_for_history(
            lookback_days=int(lookback_days),
            coin_id=coin_id,
            timeframe=timeframe,
            limit_per_scope=limit_per_scope,
        )
        if not signals:
            result = SignalHistoryRefreshResult(
                status="ok",
                rows=0,
                evaluated=0,
                coin_id=coin_id,
                timeframe=timeframe,
            )
            self._log_debug(
                "service.refresh_signal_history.result",
                mode="write",
                status=result.status,
                rows=result.rows,
                evaluated=result.evaluated,
                coin_id=coin_id,
                timeframe=timeframe,
            )
            return result

        rows: list[dict[str, object]] = []
        evaluated = 0
        for scoped_signals in _group_signals(signals).values():
            group_coin_id = int(scoped_signals[0].coin_id)
            group_timeframe = int(scoped_signals[0].timeframe)
            candles = await self._market_data.fetch_points_between(
                coin_id=group_coin_id,
                timeframe=group_timeframe,
                window_start=_open_timestamp_from_signal(scoped_signals[0]),
                window_end=ensure_utc(scoped_signals[-1].candle_timestamp) + _evaluation_horizon(group_timeframe),
            )
            if not candles:
                self._log_debug(
                    "service.refresh_signal_history.group_missing_candles",
                    mode="write",
                    coin_id=group_coin_id,
                    timeframe=group_timeframe,
                    signal_count=len(scoped_signals),
                )
            evaluations = evaluate_signal_history_batch(
                signals=tuple(
                    SignalHistorySignalInput(
                        coin_id=int(signal.coin_id),
                        timeframe=int(signal.timeframe),
                        signal_type=str(signal.signal_type),
                        confidence=float(signal.confidence),
                        market_regime=str(signal.market_regime) if signal.market_regime is not None else None,
                        candle_timestamp=ensure_utc(signal.candle_timestamp),
                    )
                    for signal in scoped_signals
                ),
                candles=tuple(
                    SignalHistoryCandleInput(
                        timestamp=ensure_utc(candle.timestamp),
                        open=float(candle.open),
                        high=float(candle.high),
                        low=float(candle.low),
                        close=float(candle.close),
                        volume=float(candle.volume) if candle.volume is not None else None,
                    )
                    for candle in candles
                ),
                evaluated_at=utc_now(),
            )
            for evaluation in evaluations:
                if evaluation.evaluated_at is not None:
                    evaluated += 1
                rows.append(
                    {
                        "coin_id": evaluation.coin_id,
                        "timeframe": evaluation.timeframe,
                        "signal_type": evaluation.signal_type,
                        "confidence": evaluation.confidence,
                        "market_regime": evaluation.market_regime,
                        "candle_timestamp": evaluation.candle_timestamp,
                        "profit_after_24h": evaluation.profit_after_24h,
                        "profit_after_72h": evaluation.profit_after_72h,
                        "maximum_drawdown": evaluation.maximum_drawdown,
                        "result_return": evaluation.result_return,
                        "result_drawdown": evaluation.result_drawdown,
                        "evaluated_at": evaluation.evaluated_at,
                    }
                )
        await self._history.upsert_signal_history(rows=rows)
        result = SignalHistoryRefreshResult(
            status="ok",
            rows=len(rows),
            evaluated=evaluated,
            coin_id=coin_id,
            timeframe=timeframe,
        )
        self._log_info(
            "service.refresh_signal_history.result",
            mode="write",
            rows=result.rows,
            evaluated=result.evaluated,
            coin_id=coin_id,
            timeframe=timeframe,
        )
        return result

    async def refresh_recent_history(
        self,
        *,
        coin_id: int,
        timeframe: int,
    ) -> SignalHistoryRefreshResult:
        self._log_debug(
            "service.refresh_recent_signal_history",
            mode="write",
            coin_id=coin_id,
            timeframe=timeframe,
        )
        return await self.refresh_history(
            lookback_days=SIGNAL_HISTORY_LOOKBACK_DAYS,
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            limit_per_scope=SIGNAL_HISTORY_RECENT_LIMIT,
        )


def _group_signals(signals: list[Signal]) -> dict[tuple[int, int], list[Signal]]:
    grouped: dict[tuple[int, int], list[Signal]] = {}
    for signal in signals:
        grouped.setdefault((int(signal.coin_id), int(signal.timeframe)), []).append(signal)
    return grouped


def _evaluation_horizon(timeframe: int):
    from datetime import timedelta

    return timedelta(hours=72, minutes=timeframe)


__all__ = ["SignalHistoryService"]
