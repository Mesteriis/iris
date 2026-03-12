from __future__ import annotations

from typing import Any, cast

from sqlalchemy import func, select

from src.apps.market_data.domain import utc_now
from src.apps.market_data.models import Coin
from src.apps.patterns.domain.base import PatternDetection
from src.apps.patterns.domain.pattern_context import apply_pattern_context, dependencies_satisfied
from src.apps.patterns.domain.success import apply_pattern_success_validation
from src.apps.patterns.domain.utils import current_indicator_map
from src.apps.patterns.task_service_base import PatternTaskBase
from src.apps.signals.models import Signal
from src.core.db.uow import BaseAsyncUnitOfWork


class PatternBootstrapService(PatternTaskBase):
    def __init__(self, uow: BaseAsyncUnitOfWork) -> None:
        super().__init__(uow, service_name="PatternBootstrapService")

    async def bootstrap_scan(self, *, symbol: str | None = None, force: bool = False) -> dict[str, object]:
        from src.apps.market_data.services import (
            get_coin_by_symbol_async,
            list_coin_symbols_ready_for_latest_sync_async,
        )

        if symbol is not None:
            coin = await get_coin_by_symbol_async(self.session, symbol)
            if coin is None:
                return {"status": "error", "reason": "coin_not_found", "symbol": symbol.upper()}
            result = await self._bootstrap_coin(coin=coin, force=force)
            await self._uow.commit()
            return {"status": "ok", "coins": 1, "items": [result]}

        coin_symbols = await list_coin_symbols_ready_for_latest_sync_async(self.session)
        items = []
        for coin_symbol in coin_symbols:
            coin = await get_coin_by_symbol_async(self.session, coin_symbol)
            if coin is None:
                continue
            items.append(await self._bootstrap_coin(coin=coin, force=force))
            await self._uow.commit()
        return {
            "status": "ok",
            "coins": len(coin_symbols),
            "created": sum(int(item.get("created", 0)) for item in items),
            "items": items,
        }

    async def _bootstrap_coin(self, *, coin: Coin, force: bool) -> dict[str, object]:
        if not await self._feature_enabled("pattern_detection"):
            return {"status": "skipped", "reason": "pattern_detection_disabled", "coin_id": int(coin.id)}
        history_count = int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(Signal)
                    .where(
                        Signal.coin_id == int(coin.id),
                        Signal.signal_type.like("pattern_%"),
                    )
                )
            ).scalar_one()
            or 0
        )
        if not force and history_count > 0:
            return {
                "status": "skipped",
                "reason": "pattern_history_exists",
                "coin_id": int(coin.id),
                "symbol": coin.symbol,
            }

        total_created = 0
        total_detections = 0
        interval_to_timeframe = {"15m": 15, "1h": 60, "4h": 240, "1d": 1440}
        for candle_config in coin.candles_config or []:
            timeframe = interval_to_timeframe.get(str(candle_config["interval"]))
            if timeframe is None:
                continue
            detectors = await self._load_active_detectors(timeframe=timeframe)
            if not detectors:
                continue
            candles = await self._fetch_candle_points(
                coin_id=int(coin.id),
                timeframe=timeframe,
                limit=int(candle_config.get("retention_bars", 200)),
            )
            if len(candles) < 30:
                continue
            success_cache = await self._pattern_success_cache(
                timeframe=timeframe,
                slugs={detector.slug for detector in detectors},
                regimes=set(),
            )
            detections: list[PatternDetection] = []
            for index in range(29, len(candles)):
                window = candles[max(0, index - 199) : index + 1]
                indicators = current_indicator_map(window)
                for detector in detectors:
                    if not detector.enabled or timeframe not in detector.supported_timeframes:
                        continue
                    if not dependencies_satisfied(detector, indicators):
                        continue
                    for detection in detector.detect(window, indicators):
                        adjusted = apply_pattern_context(
                            detection=detection,
                            detector=detector,
                            indicators=indicators,
                            regime=None,
                        )
                        if adjusted is None:
                            continue
                        validated = apply_pattern_success_validation(
                            cast(Any, None),
                            detection=adjusted,
                            timeframe=timeframe,
                            market_regime=None,
                            coin_id=int(coin.id),
                            emit_events=True,
                            snapshot_cache=success_cache,
                        )
                        if validated is not None:
                            detections.append(validated)
            rows = [
                {
                    "coin_id": int(coin.id),
                    "timeframe": timeframe,
                    "signal_type": detection.signal_type,
                    "confidence": detection.confidence,
                    "priority_score": 0.0,
                    "context_score": 1.0,
                    "regime_alignment": 1.0,
                    "market_regime": str(detection.attributes.get("regime"))
                    if detection.attributes.get("regime") is not None
                    else None,
                    "candle_timestamp": detection.candle_timestamp,
                }
                for detection in detections
            ]
            total_detections += len(detections)
            total_created += await self._upsert_signals(rows=rows)
        coin.history_backfill_completed_at = utc_now()
        await self._uow.flush()
        return {
            "status": "ok",
            "coin_id": int(coin.id),
            "symbol": coin.symbol,
            "detections": total_detections,
            "created": total_created,
        }


__all__ = ["PatternBootstrapService"]
