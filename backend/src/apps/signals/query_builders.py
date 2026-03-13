from __future__ import annotations

from sqlalchemy import func, select

from src.apps.signals.models import FinalSignal, InvestmentDecision, MarketDecision


def latest_decisions_subquery():
    return (
        select(
            InvestmentDecision.id.label("id"),
            InvestmentDecision.coin_id.label("coin_id"),
            InvestmentDecision.timeframe.label("timeframe"),
            InvestmentDecision.decision.label("decision"),
            InvestmentDecision.confidence.label("confidence"),
            InvestmentDecision.score.label("score"),
            InvestmentDecision.reason.label("reason"),
            InvestmentDecision.created_at.label("created_at"),
            func.row_number()
            .over(
                partition_by=(InvestmentDecision.coin_id, InvestmentDecision.timeframe),
                order_by=(InvestmentDecision.created_at.desc(), InvestmentDecision.id.desc()),
            )
            .label("decision_rank"),
        )
        .subquery()
    )


def latest_market_decisions_subquery():
    return (
        select(
            MarketDecision.id.label("id"),
            MarketDecision.coin_id.label("coin_id"),
            MarketDecision.timeframe.label("timeframe"),
            MarketDecision.decision.label("decision"),
            MarketDecision.confidence.label("confidence"),
            MarketDecision.signal_count.label("signal_count"),
            MarketDecision.created_at.label("created_at"),
            func.row_number()
            .over(
                partition_by=(MarketDecision.coin_id, MarketDecision.timeframe),
                order_by=(MarketDecision.created_at.desc(), MarketDecision.id.desc()),
            )
            .label("market_decision_rank"),
        )
        .subquery()
    )


def latest_final_signals_subquery():
    return (
        select(
            FinalSignal.id.label("id"),
            FinalSignal.coin_id.label("coin_id"),
            FinalSignal.timeframe.label("timeframe"),
            FinalSignal.decision.label("decision"),
            FinalSignal.confidence.label("confidence"),
            FinalSignal.risk_adjusted_score.label("risk_adjusted_score"),
            FinalSignal.reason.label("reason"),
            FinalSignal.created_at.label("created_at"),
            func.row_number()
            .over(
                partition_by=(FinalSignal.coin_id, FinalSignal.timeframe),
                order_by=(FinalSignal.created_at.desc(), FinalSignal.id.desc()),
            )
            .label("final_signal_rank"),
        )
        .subquery()
    )


__all__ = [
    "latest_decisions_subquery",
    "latest_final_signals_subquery",
    "latest_market_decisions_subquery",
]
