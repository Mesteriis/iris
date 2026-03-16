from dataclasses import dataclass
from datetime import datetime, timedelta

from src.apps.cross_market.cache import read_cached_correlation_async
from src.apps.market_data.domain import ensure_utc
from src.apps.patterns.domain.semantics import slug_from_signal_type
from src.apps.signals.engines.contracts import (
    SignalFusionInput,
    SignalFusionNewsImpactInput,
    SignalFusionSignalInput,
    SignalSuccessRate,
)
from src.apps.signals.fusion_support import (
    FUSION_CANDLE_GROUPS,
    FUSION_SIGNAL_LIMIT,
    NEWS_FUSION_MAX_ITEMS,
    NEWS_FUSION_SCORE_CAP,
    _clamp,
    _signal_regime,
)
from src.apps.signals.models import Signal
from src.apps.signals.repositories import SignalFusionRepository
from src.core.db.uow import BaseAsyncUnitOfWork


@dataclass(slots=True, frozen=True)
class SignalFusionPreparation:
    fusion_input: SignalFusionInput
    regime: str | None


class SignalFusionInputBuilder:
    def __init__(self, *, uow: BaseAsyncUnitOfWork, signals: SignalFusionRepository) -> None:
        self._uow = uow
        self._signals = signals

    async def build(
        self,
        *,
        coin_id: int,
        timeframe: int,
        trigger_timestamp: object | None,
        news_reference_timestamp: object | None,
    ) -> SignalFusionPreparation | None:
        recent_signals = await self._recent_signals(coin_id=coin_id, timeframe=timeframe)
        if not recent_signals:
            return None
        metrics = await self._signals.get_coin_metrics(coin_id=coin_id)
        regime = _signal_regime(metrics, timeframe)
        reference_timestamp = ensure_utc(
            news_reference_timestamp or trigger_timestamp or max(signal.candle_timestamp for signal in recent_signals)
        )
        success_rates = await self._pattern_success_rates(
            signals=recent_signals,
            timeframe=timeframe,
            regime=regime,
        )
        bullish_alignment = await self._cross_market_alignment_weight(
            coin_id=coin_id,
            timeframe=timeframe,
            directional_bias=1.0,
        )
        bearish_alignment = await self._cross_market_alignment_weight(
            coin_id=coin_id,
            timeframe=timeframe,
            directional_bias=-1.0,
        )
        news_impact = await self._recent_news_impact(
            coin_id=coin_id,
            timeframe=timeframe,
            reference_timestamp=reference_timestamp,
        )
        return SignalFusionPreparation(
            fusion_input=SignalFusionInput(
                signals=tuple(
                    SignalFusionSignalInput(
                        signal_type=str(signal.signal_type),
                        confidence=float(signal.confidence),
                        priority_score=float(signal.priority_score) if signal.priority_score is not None else None,
                        context_score=float(signal.context_score) if signal.context_score is not None else None,
                        regime_alignment=(
                            float(signal.regime_alignment) if signal.regime_alignment is not None else None
                        ),
                        candle_timestamp=ensure_utc(signal.candle_timestamp),
                    )
                    for signal in recent_signals
                ),
                regime=regime,
                success_rates=tuple(
                    SignalSuccessRate(
                        pattern_slug=pattern_slug,
                        market_regime=market_regime,
                        success_rate=float(success_rate),
                    )
                    for (pattern_slug, market_regime), success_rate in sorted(success_rates.items())
                ),
                bullish_alignment=bullish_alignment,
                bearish_alignment=bearish_alignment,
                news_impact=news_impact,
            ),
            regime=regime,
        )

    async def _recent_signals(self, *, coin_id: int, timeframe: int) -> list[Signal]:
        rows = await self._signals.list_recent_signals(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            limit=FUSION_SIGNAL_LIMIT,
        )
        if not rows:
            return []
        timestamps: list[datetime] = []
        selected: list[Signal] = []
        for row in rows:
            normalized = ensure_utc(row.candle_timestamp)
            if normalized not in timestamps:
                if len(timestamps) >= FUSION_CANDLE_GROUPS:
                    break
                timestamps.append(normalized)
            selected.append(row)
        return selected

    async def _pattern_success_rates(
        self,
        *,
        signals: list[Signal],
        timeframe: int,
        regime: str | None,
    ) -> dict[tuple[str, str], float]:
        slugs = sorted(
            {slug for signal in signals if (slug := slug_from_signal_type(str(signal.signal_type))) is not None}
        )
        regimes = ["all"]
        if regime is not None:
            regimes.insert(0, str(regime))
        return await self._signals.list_pattern_success_rates(
            timeframe=int(timeframe),
            pattern_slugs=slugs,
            market_regimes=regimes,
        )

    async def _cross_market_alignment_weight(
        self,
        *,
        coin_id: int,
        timeframe: int,
        directional_bias: float,
    ) -> float:
        if directional_bias == 0:
            return 1.0
        relations = await self._signals.list_alignment_relations(follower_coin_id=int(coin_id), limit=3)
        if not relations:
            return 1.0
        leader_decisions = await self._signals.list_latest_leader_decisions(
            leader_coin_ids=[int(item.leader_coin_id) for item in relations],
            timeframe=int(timeframe),
        )
        weight = 1.0
        for relation in relations:
            cached = await read_cached_correlation_async(
                leader_coin_id=int(relation.leader_coin_id),
                follower_coin_id=int(relation.follower_coin_id),
            )
            decision, decision_confidence = leader_decisions.get(int(relation.leader_coin_id), (None, 0.0))
            if decision is None:
                continue
            relation_strength = float(cached.confidence if cached is not None else relation.confidence) * float(
                cached.correlation if cached is not None else relation.correlation
            )
            delta = min(relation_strength * max(float(decision_confidence), 0.3), 0.22)
            if (directional_bias > 0 and decision == "BUY") or (directional_bias < 0 and decision == "SELL"):
                weight += delta
            elif decision in {"BUY", "SELL"}:
                weight -= delta * 0.8
        sector_trend = await self._signals.get_sector_trend(coin_id=int(coin_id), timeframe=int(timeframe))
        if sector_trend is not None:
            if (directional_bias > 0 and sector_trend == "bullish") or (
                directional_bias < 0 and sector_trend == "bearish"
            ):
                weight += 0.05
            elif sector_trend in {"bullish", "bearish"}:
                weight -= 0.04
        return _clamp(weight, 0.75, 1.35)

    async def _recent_news_impact(
        self,
        *,
        coin_id: int,
        timeframe: int,
        reference_timestamp: datetime,
    ) -> SignalFusionNewsImpactInput | None:
        lookback = self._news_lookback(int(timeframe))
        since = reference_timestamp - lookback
        rows = await self._signals.list_recent_news_rows(
            coin_id=int(coin_id),
            reference_timestamp=reference_timestamp,
            since=since,
            limit=NEWS_FUSION_MAX_ITEMS,
        )
        if not rows:
            return None
        bullish_score = 0.0
        bearish_score = 0.0
        latest_timestamp = max(ensure_utc(row.published_at) for row in rows)
        lookback_seconds = max(lookback.total_seconds(), 1.0)
        for row in rows:
            published_at = ensure_utc(row.published_at)
            age_seconds = max((reference_timestamp - published_at).total_seconds(), 0.0)
            recency_weight = _clamp(1.0 - (age_seconds / lookback_seconds), 0.12, 1.0)
            base_weight = (
                _clamp(float(row.confidence or 0.0), 0.0, 1.0)
                * _clamp(float(row.relevance_score or 0.0), 0.0, 1.0)
                * recency_weight
            )
            sentiment = float(row.sentiment_score or 0.0)
            if sentiment >= 0.08:
                bullish_score += base_weight * max(abs(sentiment), 0.2)
            elif sentiment <= -0.08:
                bearish_score += base_weight * max(abs(sentiment), 0.2)
            else:
                bullish_score += base_weight * 0.05
                bearish_score += base_weight * 0.05
        return SignalFusionNewsImpactInput(
            item_count=len(rows),
            bullish_score=round(_clamp(bullish_score, 0.0, NEWS_FUSION_SCORE_CAP), 4),
            bearish_score=round(_clamp(bearish_score, 0.0, NEWS_FUSION_SCORE_CAP), 4),
            latest_timestamp=latest_timestamp,
        )

    @staticmethod
    def _news_lookback(timeframe: int) -> timedelta:
        if timeframe <= 15:
            return timedelta(hours=12)
        if timeframe <= 60:
            return timedelta(hours=24)
        if timeframe <= 240:
            return timedelta(hours=48)
        return timedelta(days=7)


__all__ = ["SignalFusionInputBuilder", "SignalFusionPreparation"]
