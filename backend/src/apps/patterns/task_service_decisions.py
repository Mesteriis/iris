from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.apps.cross_market.models import SectorMetric
from src.apps.indicators.models import CoinMetrics, IndicatorCache
from src.apps.market_data.domain import utc_now
from src.apps.market_data.models import Candle, Coin
from src.apps.patterns.domain.context import (
    _cycle_alignment as context_cycle_alignment,
)
from src.apps.patterns.domain.decision import (
    MATERIAL_CONFIDENCE_DELTA,
    MATERIAL_SCORE_DELTA,
    RECENT_DECISION_LOOKBACK_DAYS,
    DecisionFactors,
    _decision_confidence,
    _decision_from_score,
    _decision_reason,
    _sector_strength_factor,
    calculate_decision_score,
)
from src.apps.patterns.domain.decision import (
    _clamp as decision_clamp,
)
from src.apps.patterns.domain.decision import (
    _regime_alignment as decision_regime_alignment,
)
from src.apps.patterns.domain.regime import read_regime_details
from src.apps.patterns.domain.risk import (
    MATERIAL_RISK_CONFIDENCE_DELTA,
    MATERIAL_RISK_SCORE_DELTA,
    RECENT_FINAL_SIGNAL_LOOKBACK_DAYS,
    _final_signal_reason,
    _risk_adjusted_decision,
    _risk_confidence,
    calculate_liquidity_score,
    calculate_risk_adjusted_score,
    calculate_slippage_risk,
    calculate_volatility_risk,
)
from src.apps.patterns.domain.semantics import is_pattern_signal, pattern_bias, slug_from_signal_type
from src.apps.patterns.domain.success import GLOBAL_MARKET_REGIME, normalize_market_regime
from src.apps.patterns.models import MarketCycle, PatternStatistic
from src.apps.signals.models import FinalSignal, InvestmentDecision, RiskMetric, Signal, Strategy
from src.runtime.streams.messages import publish_investment_decision_message, publish_investment_signal_message


class PatternDecisionSignalsMixin:
    async def _evaluate_investment_decision(
        self,
        *,
        coin_id: int,
        timeframe: int,
        narratives_by_timeframe: dict[int, object] | None = None,
        strategies: Sequence[Strategy] | None = None,
        emit_event: bool = True,
    ) -> dict[str, object]:
        latest_timestamp = await self.session.scalar(
            select(func.max(Signal.candle_timestamp)).where(
                Signal.coin_id == coin_id,
                Signal.timeframe == timeframe,
                Signal.signal_type.like("pattern_%"),
            )
        )
        if latest_timestamp is None:
            return {
                "status": "skipped",
                "reason": "pattern_signals_not_found",
                "coin_id": coin_id,
                "timeframe": timeframe,
            }
        signals = (
            (
                await self.session.execute(
                    select(Signal)
                    .where(
                        Signal.coin_id == coin_id,
                        Signal.timeframe == timeframe,
                        Signal.candle_timestamp == latest_timestamp,
                        Signal.signal_type.like("pattern_%"),
                    )
                    .order_by(Signal.created_at.asc(), Signal.id.asc())
                )
            )
            .scalars()
            .all()
        )
        if not signals:
            return {"status": "skipped", "reason": "signal_stack_not_found", "coin_id": coin_id, "timeframe": timeframe}

        coin = await self.session.scalar(
            select(Coin).options(selectinload(Coin.sector)).where(Coin.id == coin_id).limit(1)
        )
        if coin is None:
            return {"status": "skipped", "reason": "coin_not_found", "coin_id": coin_id, "timeframe": timeframe}
        metrics = await self.session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id).limit(1))
        cycle = await self.session.get(MarketCycle, (coin_id, timeframe))
        sector_metric = (
            await self.session.get(SectorMetric, (int(coin.sector_id), timeframe))
            if coin.sector_id is not None
            else None
        )
        narrative = narratives_by_timeframe.get(timeframe) if narratives_by_timeframe is not None else None
        if narrative is None:
            narrative = next(
                (item for item in await self._queries.build_sector_narratives() if item.timeframe == timeframe),
                None,
            )

        relevant_signals = [signal for signal in signals if str(signal.signal_type).startswith("pattern_")]
        weights = [max(float(signal.priority_score or signal.confidence), 0.01) for signal in relevant_signals]
        signal_priority = sum(sorted(weights, reverse=True)[:5]) / max(min(len(weights), 5), 1)

        signed_weight = 0.0
        pattern_slugs: set[str] = set()
        token_confidence: dict[str, float] = {}
        strategy_tokens: set[str] = set()
        for signal in relevant_signals:
            slug = slug_from_signal_type(str(signal.signal_type))
            if slug is not None and is_pattern_signal(str(signal.signal_type)):
                pattern_slugs.add(slug)
                strategy_tokens.add(slug)
                token_confidence[slug] = max(token_confidence.get(slug, 0.0), float(signal.confidence))
            weight = max(float(signal.priority_score or signal.confidence), 0.01)
            signed_weight += weight * pattern_bias(
                slug or str(signal.signal_type),
                fallback_price_delta=float(signal.confidence) - 0.5,
            )

        total_weight = sum(weights)
        bias_ratio = signed_weight / max(total_weight, 1e-9)
        bias = 1 if bias_ratio > 0 else -1 if bias_ratio < 0 else 0
        regime_snapshot = (
            read_regime_details(metrics.market_regime_details, timeframe)
            if metrics is not None and metrics.market_regime_details
            else None
        )
        regime = (
            regime_snapshot.regime
            if regime_snapshot is not None
            else (metrics.market_regime if metrics is not None else None)
        )
        regime_alignment = decision_regime_alignment(relevant_signals)
        sector_strength = _sector_strength_factor(coin, metrics, sector_metric, narrative)
        cycle_alignment = context_cycle_alignment(cycle, bias)

        success_rows = (
            (
                await self.session.execute(
                    select(PatternStatistic).where(
                        PatternStatistic.pattern_slug.in_(sorted(pattern_slugs)) if pattern_slugs else False,
                        PatternStatistic.timeframe == timeframe,
                        PatternStatistic.market_regime.in_([GLOBAL_MARKET_REGIME, normalize_market_regime(regime)]),
                    )
                )
            )
            .scalars()
            .all()
            if pattern_slugs
            else []
        )
        success_values: dict[str, float] = {}
        for row in success_rows:
            current = success_values.get(str(row.pattern_slug))
            candidate = float(row.success_rate or 0.0)
            if current is None or str(row.market_regime) != GLOBAL_MARKET_REGIME:
                success_values[str(row.pattern_slug)] = candidate
        historical_pattern_success = (
            decision_clamp(sum(success_values.values()) / len(success_values), 0.35, 0.95) if success_values else 0.55
        )

        loaded_strategies = list(strategies) if strategies is not None else await self._load_enabled_strategies()
        strategy_alignment_value, matched_strategies = await self._strategy_alignment(
            strategies=loaded_strategies,
            tokens=strategy_tokens,
            token_confidence=token_confidence,
            regime=regime,
            sector=coin.sector.name if coin.sector is not None else None,
            cycle=cycle.cycle_phase if cycle is not None else None,
        )
        factors = DecisionFactors(
            signal_priority=signal_priority,
            regime_alignment=regime_alignment,
            sector_strength=sector_strength,
            cycle_alignment=cycle_alignment,
            historical_pattern_success=historical_pattern_success,
            strategy_alignment=strategy_alignment_value,
        )
        score = calculate_decision_score(
            signal_priority=factors.signal_priority,
            regime_alignment=factors.regime_alignment,
            sector_strength=factors.sector_strength,
            cycle_alignment=factors.cycle_alignment,
            historical_pattern_success=factors.historical_pattern_success,
            strategy_alignment=factors.strategy_alignment,
        )
        decision = _decision_from_score(score, bias_ratio)
        confidence = _decision_confidence(score, bias_ratio, factors)
        reason = _decision_reason(
            decision=decision,
            score=score,
            bias_ratio=bias_ratio,
            signals=relevant_signals,
            regime=regime,
            sector_metric=sector_metric,
            narrative=narrative,
            cycle=cycle,
            historical_pattern_success=historical_pattern_success,
            strategy_alignment_value=strategy_alignment_value,
            matched_strategies=matched_strategies,
        )

        latest_decision = await self.session.scalar(
            select(InvestmentDecision)
            .where(InvestmentDecision.coin_id == coin_id, InvestmentDecision.timeframe == timeframe)
            .order_by(InvestmentDecision.created_at.desc(), InvestmentDecision.id.desc())
            .limit(1)
        )
        if (
            latest_decision is not None
            and latest_decision.decision == decision
            and abs(float(latest_decision.score) - score) < MATERIAL_SCORE_DELTA
            and abs(float(latest_decision.confidence) - confidence) < MATERIAL_CONFIDENCE_DELTA
            and latest_decision.reason == reason
        ):
            return {
                "status": "skipped",
                "reason": "decision_unchanged",
                "coin_id": coin_id,
                "timeframe": timeframe,
                "decision": decision,
                "score": score,
            }

        row = InvestmentDecision(
            coin_id=coin_id,
            timeframe=timeframe,
            decision=decision,
            confidence=confidence,
            score=score,
            reason=reason,
        )
        self.session.add(row)
        await self._uow.flush()
        if emit_event:
            publish_investment_decision_message(
                coin,
                timeframe=timeframe,
                decision=decision,
                confidence=confidence,
                score=score,
                reason=reason,
            )
        return {
            "status": "ok",
            "id": row.id,
            "coin_id": coin_id,
            "timeframe": timeframe,
            "decision": decision,
            "confidence": confidence,
            "score": score,
        }

    async def _refresh_investment_decisions(
        self,
        *,
        lookback_days: int = RECENT_DECISION_LOOKBACK_DAYS,
        emit_events: bool = False,
    ) -> dict[str, object]:
        cutoff = utc_now() - timedelta(days=max(lookback_days, 1))
        rows = (
            await self.session.execute(
                select(Signal.coin_id, Signal.timeframe)
                .where(Signal.signal_type.like("pattern_%"), Signal.candle_timestamp >= cutoff)
                .distinct()
                .order_by(Signal.coin_id.asc(), Signal.timeframe.asc())
            )
        ).all()
        candidates = [(int(row.coin_id), int(row.timeframe)) for row in rows]
        narratives_by_timeframe = {item.timeframe: item for item in await self._queries.build_sector_narratives()}
        strategies = await self._load_enabled_strategies()
        items = [
            await self._evaluate_investment_decision(
                coin_id=coin_id,
                timeframe=timeframe,
                narratives_by_timeframe=narratives_by_timeframe,
                strategies=strategies,
                emit_event=emit_events,
            )
            for coin_id, timeframe in candidates
        ]
        return {
            "status": "ok",
            "items": items,
            "updated": sum(1 for item in items if item.get("status") == "ok"),
            "candidates": len(candidates),
        }

    async def _update_risk_metrics(
        self,
        *,
        coin_id: int,
        timeframe: int,
    ) -> tuple[dict[str, object], RiskMetric | None]:
        coin = await self.session.scalar(select(Coin).where(Coin.id == coin_id).limit(1))
        if coin is None:
            return {"status": "skipped", "reason": "coin_not_found", "coin_id": coin_id, "timeframe": timeframe}, None
        metrics = await self.session.scalar(select(CoinMetrics).where(CoinMetrics.coin_id == coin_id).limit(1))
        volume_24h = float(metrics.volume_24h or 0.0) if metrics is not None else 0.0
        market_cap = float(metrics.market_cap or 0.0) if metrics is not None else 0.0
        atr_14 = (
            await self.session.execute(
                select(IndicatorCache.value)
                .where(
                    IndicatorCache.coin_id == coin_id,
                    IndicatorCache.timeframe == timeframe,
                    IndicatorCache.indicator == "atr_14",
                )
                .order_by(IndicatorCache.timestamp.desc(), IndicatorCache.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if atr_14 is None and metrics is not None:
            atr_14 = float(metrics.atr_14 or 0.0)
        price = (
            await self.session.execute(
                select(Candle.close)
                .where(Candle.coin_id == coin_id, Candle.timeframe == timeframe)
                .order_by(Candle.timestamp.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if price is None and metrics is not None:
            price = float(metrics.price_current or 0.0)

        liquidity_score = calculate_liquidity_score(volume_24h=volume_24h, market_cap=market_cap)
        slippage_risk = calculate_slippage_risk(volume_24h=volume_24h, market_cap=market_cap)
        volatility_risk = calculate_volatility_risk(atr_14=float(atr_14 or 0.0), price=float(price or 0.0))

        row = await self.session.get(RiskMetric, (coin_id, timeframe))
        if row is None:
            row = RiskMetric(coin_id=coin_id, timeframe=timeframe)
            self.session.add(row)
        row.liquidity_score = liquidity_score
        row.slippage_risk = slippage_risk
        row.volatility_risk = volatility_risk
        row.updated_at = utc_now()
        await self._uow.flush()
        return {
            "status": "ok",
            "coin_id": coin_id,
            "timeframe": timeframe,
            "liquidity_score": liquidity_score,
            "slippage_risk": slippage_risk,
            "volatility_risk": volatility_risk,
        }, row

    async def _evaluate_final_signal(
        self,
        *,
        coin_id: int,
        timeframe: int,
        emit_event: bool = True,
    ) -> dict[str, object]:
        coin = await self.session.scalar(select(Coin).where(Coin.id == coin_id).limit(1))
        if coin is None:
            return {"status": "skipped", "reason": "coin_not_found", "coin_id": coin_id, "timeframe": timeframe}
        latest_decision = await self.session.scalar(
            select(InvestmentDecision)
            .where(InvestmentDecision.coin_id == coin_id, InvestmentDecision.timeframe == timeframe)
            .order_by(InvestmentDecision.created_at.desc(), InvestmentDecision.id.desc())
            .limit(1)
        )
        if latest_decision is None:
            return {"status": "skipped", "reason": "decision_not_found", "coin_id": coin_id, "timeframe": timeframe}

        metrics_payload, _ = await self._update_risk_metrics(coin_id=coin_id, timeframe=timeframe)
        risk_adjusted_score = calculate_risk_adjusted_score(
            decision_score=float(latest_decision.score),
            liquidity_score=float(metrics_payload["liquidity_score"]),
            slippage_risk=float(metrics_payload["slippage_risk"]),
            volatility_risk=float(metrics_payload["volatility_risk"]),
        )
        decision = _risk_adjusted_decision(str(latest_decision.decision), risk_adjusted_score)
        confidence = _risk_confidence(
            base_confidence=float(latest_decision.confidence),
            liquidity_score=float(metrics_payload["liquidity_score"]),
            slippage_risk=float(metrics_payload["slippage_risk"]),
            volatility_risk=float(metrics_payload["volatility_risk"]),
        )
        reason = _final_signal_reason(
            decision=decision,
            base_decision=str(latest_decision.decision),
            decision_score=float(latest_decision.score),
            risk_adjusted_score=risk_adjusted_score,
            liquidity_score=float(metrics_payload["liquidity_score"]),
            slippage_risk=float(metrics_payload["slippage_risk"]),
            volatility_risk=float(metrics_payload["volatility_risk"]),
        )

        latest_signal = await self.session.scalar(
            select(FinalSignal)
            .where(FinalSignal.coin_id == coin_id, FinalSignal.timeframe == timeframe)
            .order_by(FinalSignal.created_at.desc(), FinalSignal.id.desc())
            .limit(1)
        )
        if (
            latest_signal is not None
            and latest_signal.decision == decision
            and abs(float(latest_signal.risk_adjusted_score) - risk_adjusted_score) < MATERIAL_RISK_SCORE_DELTA
            and abs(float(latest_signal.confidence) - confidence) < MATERIAL_RISK_CONFIDENCE_DELTA
            and latest_signal.reason == reason
        ):
            return {
                "status": "skipped",
                "reason": "final_signal_unchanged",
                "coin_id": coin_id,
                "timeframe": timeframe,
                "decision": decision,
                "risk_adjusted_score": risk_adjusted_score,
            }

        row = FinalSignal(
            coin_id=coin_id,
            timeframe=timeframe,
            decision=decision,
            confidence=confidence,
            risk_adjusted_score=risk_adjusted_score,
            reason=reason,
        )
        self.session.add(row)
        await self._uow.flush()
        if emit_event:
            publish_investment_signal_message(
                coin,
                timeframe=timeframe,
                decision=decision,
                confidence=confidence,
                risk_score=risk_adjusted_score,
                reason=reason,
            )
        return {
            "status": "ok",
            "id": row.id,
            "coin_id": coin_id,
            "timeframe": timeframe,
            "decision": decision,
            "confidence": confidence,
            "risk_adjusted_score": risk_adjusted_score,
        }

    async def _refresh_final_signals(
        self,
        *,
        lookback_days: int = RECENT_FINAL_SIGNAL_LOOKBACK_DAYS,
        emit_events: bool = False,
    ) -> dict[str, object]:
        cutoff = utc_now() - timedelta(days=max(lookback_days, 1))
        rows = (
            await self.session.execute(
                select(InvestmentDecision.coin_id, InvestmentDecision.timeframe)
                .where(InvestmentDecision.created_at >= cutoff)
                .distinct()
                .order_by(InvestmentDecision.coin_id.asc(), InvestmentDecision.timeframe.asc())
            )
        ).all()
        candidates = [(int(row.coin_id), int(row.timeframe)) for row in rows]
        items = [
            await self._evaluate_final_signal(
                coin_id=coin_id,
                timeframe=timeframe,
                emit_event=emit_events,
            )
            for coin_id, timeframe in candidates
        ]
        return {
            "status": "ok",
            "items": items,
            "updated": sum(1 for item in items if item.get("status") == "ok"),
            "candidates": len(candidates),
        }


__all__ = ["PatternDecisionSignalsMixin"]
