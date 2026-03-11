from __future__ import annotations

from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.coin import Coin
from app.models.signal import Signal
from app.patterns.base import PatternDetection, PatternDetector
from app.patterns.registry import feature_enabled, load_active_detectors
from app.patterns.utils import current_indicator_map
from app.services.candles_service import CandlePoint
from app.services.candles_service import fetch_candle_points
from app.services.market_data import utc_now


class PatternEngine:
    interval_to_timeframe = {
        "15m": 15,
        "1h": 60,
        "4h": 240,
        "1d": 1440,
    }

    def detect(
        self,
        *,
        candles: Sequence[CandlePoint],
        indicators: dict[str, float | None],
        detectors: Sequence[PatternDetector],
        timeframe: int,
    ) -> list[PatternDetection]:
        detected: list[PatternDetection] = []
        for detector in detectors:
            if not detector.enabled or timeframe not in detector.supported_timeframes:
                continue
            detected.extend(detector.detect(candles, indicators))
        return detected

    def _insert_detections(
        self,
        db: Session,
        *,
        coin_id: int,
        timeframe: int,
        detections: Sequence[PatternDetection],
    ) -> int:
        if not detections:
            return 0
        rows = [
            {
                "coin_id": coin_id,
                "timeframe": timeframe,
                "signal_type": detection.signal_type,
                "confidence": detection.confidence,
                "priority_score": 0.0,
                "context_score": 1.0,
                "regime_alignment": 1.0,
                "candle_timestamp": detection.candle_timestamp,
            }
            for detection in detections
        ]
        stmt = insert(Signal).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["coin_id", "timeframe", "candle_timestamp", "signal_type"],
            set_={
                "confidence": stmt.excluded.confidence,
            },
        )
        result = db.execute(stmt)
        db.commit()
        return int(result.rowcount or 0)

    def detect_incremental(
        self,
        db: Session,
        *,
        coin_id: int,
        timeframe: int,
        lookback: int = 200,
    ) -> dict[str, object]:
        if not feature_enabled(db, "pattern_detection"):
            return {"status": "skipped", "reason": "pattern_detection_disabled", "coin_id": coin_id, "timeframe": timeframe}

        candles = fetch_candle_points(db, coin_id, timeframe, lookback)
        if len(candles) < 30:
            return {"status": "skipped", "reason": "insufficient_candles", "coin_id": coin_id, "timeframe": timeframe}

        detectors = load_active_detectors(db, timeframe=timeframe)
        indicators = current_indicator_map(candles)
        detections = self.detect(
            candles=candles,
            indicators=indicators,
            detectors=detectors,
            timeframe=timeframe,
        )
        created = self._insert_detections(db, coin_id=coin_id, timeframe=timeframe, detections=detections)
        return {
            "status": "ok",
            "coin_id": coin_id,
            "timeframe": timeframe,
            "detections": len(detections),
            "created": created,
        }

    def _coin_has_pattern_history(self, db: Session, coin_id: int) -> bool:
        count = db.scalar(
            select(func.count())
            .select_from(Signal)
            .where(Signal.coin_id == coin_id, Signal.signal_type.like("pattern_%"))
        )
        return bool(count)

    def bootstrap_coin(
        self,
        db: Session,
        *,
        coin: Coin,
        force: bool = False,
    ) -> dict[str, object]:
        if not feature_enabled(db, "pattern_detection"):
            return {"status": "skipped", "reason": "pattern_detection_disabled", "coin_id": coin.id}
        if not force and self._coin_has_pattern_history(db, coin.id):
            return {"status": "skipped", "reason": "pattern_history_exists", "coin_id": coin.id, "symbol": coin.symbol}

        total_created = 0
        total_detections = 0
        for candle_config in coin.candles_config or []:
            interval = str(candle_config["interval"])
            timeframe = self.interval_to_timeframe.get(interval)
            if timeframe is None:
                continue
            detectors = load_active_detectors(db, timeframe=timeframe)
            if not detectors:
                continue
            retention = int(candle_config.get("retention_bars", 200))
            candles = fetch_candle_points(db, coin.id, timeframe, retention)
            if len(candles) < 30:
                continue

            detections: list[PatternDetection] = []
            for index in range(29, len(candles)):
                window = candles[max(0, index - 199) : index + 1]
                indicators = current_indicator_map(window)
                window_detections = self.detect(
                    candles=window,
                    indicators=indicators,
                    detectors=detectors,
                    timeframe=timeframe,
                )
                detections.extend(window_detections)

            total_detections += len(detections)
            total_created += self._insert_detections(db, coin_id=coin.id, timeframe=timeframe, detections=detections)

        coin.history_backfill_completed_at = utc_now()
        db.commit()
        return {
            "status": "ok",
            "coin_id": coin.id,
            "symbol": coin.symbol,
            "detections": total_detections,
            "created": total_created,
        }
