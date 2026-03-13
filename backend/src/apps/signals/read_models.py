from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


@dataclass(slots=True, frozen=True)
class SignalReadModel:
    id: int
    coin_id: int
    symbol: str
    name: str
    sector: str | None
    timeframe: int
    signal_type: str
    confidence: float
    priority_score: float
    context_score: float
    regime_alignment: float
    candle_timestamp: datetime
    created_at: datetime
    market_regime: str | None
    cycle_phase: str | None
    cycle_confidence: float | None
    cluster_membership: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class InvestmentDecisionReadModel:
    id: int
    coin_id: int
    symbol: str
    name: str
    sector: str | None
    timeframe: int
    decision: str
    confidence: float
    score: float
    reason: str
    created_at: datetime


@dataclass(slots=True, frozen=True)
class CoinDecisionItemReadModel:
    timeframe: int
    decision: str
    confidence: float
    score: float
    reason: str
    created_at: datetime


@dataclass(slots=True, frozen=True)
class CoinDecisionReadModel:
    coin_id: int
    symbol: str
    canonical_decision: str | None
    items: tuple[CoinDecisionItemReadModel, ...]


@dataclass(slots=True, frozen=True)
class MarketDecisionReadModel:
    id: int
    coin_id: int
    symbol: str
    name: str
    sector: str | None
    timeframe: int
    decision: str
    confidence: float
    signal_count: int
    regime: str | None
    created_at: datetime


@dataclass(slots=True, frozen=True)
class CoinMarketDecisionItemReadModel:
    timeframe: int
    decision: str
    confidence: float
    signal_count: int
    regime: str | None
    created_at: datetime | None


@dataclass(slots=True, frozen=True)
class CoinMarketDecisionReadModel:
    coin_id: int
    symbol: str
    canonical_decision: str | None
    items: tuple[CoinMarketDecisionItemReadModel, ...]


@dataclass(slots=True, frozen=True)
class FinalSignalReadModel:
    id: int
    coin_id: int
    symbol: str
    name: str
    sector: str | None
    timeframe: int
    decision: str
    confidence: float
    risk_adjusted_score: float
    liquidity_score: float
    slippage_risk: float
    volatility_risk: float
    reason: str
    created_at: datetime


@dataclass(slots=True, frozen=True)
class CoinFinalSignalItemReadModel:
    timeframe: int
    decision: str
    confidence: float
    risk_adjusted_score: float
    liquidity_score: float
    slippage_risk: float
    volatility_risk: float
    reason: str
    created_at: datetime


@dataclass(slots=True, frozen=True)
class CoinFinalSignalReadModel:
    coin_id: int
    symbol: str
    canonical_decision: str | None
    items: tuple[CoinFinalSignalItemReadModel, ...]


@dataclass(slots=True, frozen=True)
class BacktestSummaryReadModel:
    symbol: str | None
    signal_type: str
    timeframe: int
    sample_size: int
    coin_count: int
    win_rate: float
    roi: float
    avg_return: float
    sharpe_ratio: float
    max_drawdown: float
    avg_confidence: float
    last_evaluated_at: datetime | None


@dataclass(slots=True, frozen=True)
class CoinBacktestsReadModel:
    coin_id: int
    symbol: str
    items: tuple[BacktestSummaryReadModel, ...]


@dataclass(slots=True, frozen=True)
class StrategyRuleReadModel:
    pattern_slug: str
    regime: str
    sector: str
    cycle: str
    min_confidence: float


@dataclass(slots=True, frozen=True)
class StrategyPerformanceReadModel:
    strategy_id: int
    name: str
    enabled: bool
    sample_size: int
    win_rate: float
    avg_return: float
    sharpe_ratio: float
    max_drawdown: float
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class StrategyReadModel:
    id: int
    name: str
    description: str
    enabled: bool
    created_at: datetime
    rules: tuple[StrategyRuleReadModel, ...]
    performance: StrategyPerformanceReadModel | None


def signal_read_model_from_mapping(mapping: Mapping[str, Any]) -> SignalReadModel:
    return SignalReadModel(
        id=int(mapping["id"]),
        coin_id=int(mapping["coin_id"]),
        symbol=str(mapping["symbol"]),
        name=str(mapping["name"]),
        sector=str(mapping["sector"]) if mapping["sector"] is not None else None,
        timeframe=int(mapping["timeframe"]),
        signal_type=str(mapping["signal_type"]),
        confidence=float(mapping["confidence"]),
        priority_score=float(mapping["priority_score"] or 0.0),
        context_score=float(mapping["context_score"] or 0.0),
        regime_alignment=float(mapping["regime_alignment"] or 0.0),
        candle_timestamp=mapping["candle_timestamp"],
        created_at=mapping["created_at"],
        market_regime=str(mapping["market_regime"]) if mapping["market_regime"] is not None else None,
        cycle_phase=str(mapping["cycle_phase"]) if mapping["cycle_phase"] is not None else None,
        cycle_confidence=float(mapping["cycle_confidence"]) if mapping["cycle_confidence"] is not None else None,
        cluster_membership=tuple(str(item) for item in mapping.get("cluster_membership", ()) or ()),
    )


def investment_decision_read_model_from_mapping(mapping: Mapping[str, Any]) -> InvestmentDecisionReadModel:
    return InvestmentDecisionReadModel(
        id=int(mapping["id"]),
        coin_id=int(mapping["coin_id"]),
        symbol=str(mapping["symbol"]),
        name=str(mapping["name"]),
        sector=str(mapping["sector"]) if mapping["sector"] is not None else None,
        timeframe=int(mapping["timeframe"]),
        decision=str(mapping["decision"]),
        confidence=float(mapping["confidence"]),
        score=float(mapping["score"]),
        reason=str(mapping["reason"]),
        created_at=mapping["created_at"],
    )


def coin_decision_item_read_model_from_mapping(mapping: Mapping[str, Any]) -> CoinDecisionItemReadModel:
    return CoinDecisionItemReadModel(
        timeframe=int(mapping["timeframe"]),
        decision=str(mapping["decision"]),
        confidence=float(mapping["confidence"]),
        score=float(mapping["score"]),
        reason=str(mapping["reason"]),
        created_at=mapping["created_at"],
    )


def coin_decision_read_model_from_mapping(mapping: Mapping[str, Any]) -> CoinDecisionReadModel:
    return CoinDecisionReadModel(
        coin_id=int(mapping["coin_id"]),
        symbol=str(mapping["symbol"]),
        canonical_decision=str(mapping["canonical_decision"]) if mapping["canonical_decision"] is not None else None,
        items=tuple(coin_decision_item_read_model_from_mapping(item) for item in mapping.get("items", ()) or ()),
    )


def market_decision_read_model_from_mapping(mapping: Mapping[str, Any]) -> MarketDecisionReadModel:
    return MarketDecisionReadModel(
        id=int(mapping["id"]),
        coin_id=int(mapping["coin_id"]),
        symbol=str(mapping["symbol"]),
        name=str(mapping["name"]),
        sector=str(mapping["sector"]) if mapping["sector"] is not None else None,
        timeframe=int(mapping["timeframe"]),
        decision=str(mapping["decision"]),
        confidence=float(mapping["confidence"]),
        signal_count=int(mapping["signal_count"]),
        regime=str(mapping["regime"]) if mapping["regime"] is not None else None,
        created_at=mapping["created_at"],
    )


def coin_market_decision_item_read_model_from_mapping(mapping: Mapping[str, Any]) -> CoinMarketDecisionItemReadModel:
    return CoinMarketDecisionItemReadModel(
        timeframe=int(mapping["timeframe"]),
        decision=str(mapping["decision"]),
        confidence=float(mapping["confidence"]),
        signal_count=int(mapping["signal_count"]),
        regime=str(mapping["regime"]) if mapping["regime"] is not None else None,
        created_at=mapping["created_at"],
    )


def coin_market_decision_read_model_from_mapping(mapping: Mapping[str, Any]) -> CoinMarketDecisionReadModel:
    return CoinMarketDecisionReadModel(
        coin_id=int(mapping["coin_id"]),
        symbol=str(mapping["symbol"]),
        canonical_decision=str(mapping["canonical_decision"]) if mapping["canonical_decision"] is not None else None,
        items=tuple(
            coin_market_decision_item_read_model_from_mapping(item) for item in mapping.get("items", ()) or ()
        ),
    )


def final_signal_read_model_from_mapping(mapping: Mapping[str, Any]) -> FinalSignalReadModel:
    return FinalSignalReadModel(
        id=int(mapping["id"]),
        coin_id=int(mapping["coin_id"]),
        symbol=str(mapping["symbol"]),
        name=str(mapping["name"]),
        sector=str(mapping["sector"]) if mapping["sector"] is not None else None,
        timeframe=int(mapping["timeframe"]),
        decision=str(mapping["decision"]),
        confidence=float(mapping["confidence"]),
        risk_adjusted_score=float(mapping["risk_adjusted_score"]),
        liquidity_score=float(mapping["liquidity_score"] or 0.0),
        slippage_risk=float(mapping["slippage_risk"] or 0.0),
        volatility_risk=float(mapping["volatility_risk"] or 0.0),
        reason=str(mapping["reason"]),
        created_at=mapping["created_at"],
    )


def coin_final_signal_item_read_model_from_mapping(mapping: Mapping[str, Any]) -> CoinFinalSignalItemReadModel:
    return CoinFinalSignalItemReadModel(
        timeframe=int(mapping["timeframe"]),
        decision=str(mapping["decision"]),
        confidence=float(mapping["confidence"]),
        risk_adjusted_score=float(mapping["risk_adjusted_score"]),
        liquidity_score=float(mapping["liquidity_score"] or 0.0),
        slippage_risk=float(mapping["slippage_risk"] or 0.0),
        volatility_risk=float(mapping["volatility_risk"] or 0.0),
        reason=str(mapping["reason"]),
        created_at=mapping["created_at"],
    )


def coin_final_signal_read_model_from_mapping(mapping: Mapping[str, Any]) -> CoinFinalSignalReadModel:
    return CoinFinalSignalReadModel(
        coin_id=int(mapping["coin_id"]),
        symbol=str(mapping["symbol"]),
        canonical_decision=str(mapping["canonical_decision"]) if mapping["canonical_decision"] is not None else None,
        items=tuple(coin_final_signal_item_read_model_from_mapping(item) for item in mapping.get("items", ()) or ()),
    )


def backtest_summary_read_model_from_mapping(mapping: Mapping[str, Any]) -> BacktestSummaryReadModel:
    return BacktestSummaryReadModel(
        symbol=str(mapping["symbol"]) if mapping["symbol"] is not None else None,
        signal_type=str(mapping["signal_type"]),
        timeframe=int(mapping["timeframe"]),
        sample_size=int(mapping["sample_size"]),
        coin_count=int(mapping["coin_count"]),
        win_rate=float(mapping["win_rate"]),
        roi=float(mapping["roi"]),
        avg_return=float(mapping["avg_return"]),
        sharpe_ratio=float(mapping["sharpe_ratio"]),
        max_drawdown=float(mapping["max_drawdown"]),
        avg_confidence=float(mapping["avg_confidence"]),
        last_evaluated_at=mapping["last_evaluated_at"],
    )


def coin_backtests_read_model_from_mapping(mapping: Mapping[str, Any]) -> CoinBacktestsReadModel:
    return CoinBacktestsReadModel(
        coin_id=int(mapping["coin_id"]),
        symbol=str(mapping["symbol"]),
        items=tuple(backtest_summary_read_model_from_mapping(item) for item in mapping.get("items", ()) or ()),
    )


def strategy_rule_read_model_from_mapping(mapping: Mapping[str, Any]) -> StrategyRuleReadModel:
    return StrategyRuleReadModel(
        pattern_slug=str(mapping["pattern_slug"]),
        regime=str(mapping["regime"]),
        sector=str(mapping["sector"]),
        cycle=str(mapping["cycle"]),
        min_confidence=float(mapping["min_confidence"]),
    )


def strategy_performance_read_model_from_mapping(mapping: Mapping[str, Any]) -> StrategyPerformanceReadModel:
    return StrategyPerformanceReadModel(
        strategy_id=int(mapping["strategy_id"]),
        name=str(mapping["name"]),
        enabled=bool(mapping["enabled"]),
        sample_size=int(mapping["sample_size"]),
        win_rate=float(mapping["win_rate"]),
        avg_return=float(mapping["avg_return"]),
        sharpe_ratio=float(mapping["sharpe_ratio"]),
        max_drawdown=float(mapping["max_drawdown"]),
        updated_at=mapping["updated_at"],
    )


def strategy_read_model_from_mapping(mapping: Mapping[str, Any]) -> StrategyReadModel:
    performance = mapping.get("performance")
    return StrategyReadModel(
        id=int(mapping["id"]),
        name=str(mapping["name"]),
        description=str(mapping["description"]),
        enabled=bool(mapping["enabled"]),
        created_at=mapping["created_at"],
        rules=tuple(strategy_rule_read_model_from_mapping(item) for item in mapping.get("rules", ()) or ()),
        performance=strategy_performance_read_model_from_mapping(performance) if performance is not None else None,
    )


def backtest_summary_payload(item: BacktestSummaryReadModel) -> dict[str, Any]:
    return {
        "symbol": item.symbol,
        "signal_type": item.signal_type,
        "timeframe": int(item.timeframe),
        "sample_size": int(item.sample_size),
        "coin_count": int(item.coin_count),
        "win_rate": float(item.win_rate),
        "roi": float(item.roi),
        "avg_return": float(item.avg_return),
        "sharpe_ratio": float(item.sharpe_ratio),
        "max_drawdown": float(item.max_drawdown),
        "avg_confidence": float(item.avg_confidence),
        "last_evaluated_at": item.last_evaluated_at,
    }


def coin_backtests_payload(item: CoinBacktestsReadModel) -> dict[str, Any]:
    return {
        "coin_id": int(item.coin_id),
        "symbol": item.symbol,
        "items": [backtest_summary_payload(row) for row in item.items],
    }


def strategy_rule_payload(item: StrategyRuleReadModel) -> dict[str, Any]:
    return {
        "pattern_slug": item.pattern_slug,
        "regime": item.regime,
        "sector": item.sector,
        "cycle": item.cycle,
        "min_confidence": float(item.min_confidence),
    }


def strategy_performance_payload(item: StrategyPerformanceReadModel) -> dict[str, Any]:
    return {
        "strategy_id": int(item.strategy_id),
        "name": item.name,
        "enabled": bool(item.enabled),
        "sample_size": int(item.sample_size),
        "win_rate": float(item.win_rate),
        "avg_return": float(item.avg_return),
        "sharpe_ratio": float(item.sharpe_ratio),
        "max_drawdown": float(item.max_drawdown),
        "updated_at": item.updated_at,
    }


def strategy_payload(item: StrategyReadModel) -> dict[str, Any]:
    return {
        "id": int(item.id),
        "name": item.name,
        "description": item.description,
        "enabled": bool(item.enabled),
        "created_at": item.created_at,
        "rules": [strategy_rule_payload(rule) for rule in item.rules],
        "performance": strategy_performance_payload(item.performance) if item.performance is not None else None,
    }


__all__ = [
    "BacktestSummaryReadModel",
    "CoinBacktestsReadModel",
    "CoinDecisionItemReadModel",
    "CoinDecisionReadModel",
    "CoinFinalSignalItemReadModel",
    "CoinFinalSignalReadModel",
    "CoinMarketDecisionItemReadModel",
    "CoinMarketDecisionReadModel",
    "FinalSignalReadModel",
    "InvestmentDecisionReadModel",
    "MarketDecisionReadModel",
    "SignalReadModel",
    "StrategyPerformanceReadModel",
    "StrategyReadModel",
    "StrategyRuleReadModel",
    "backtest_summary_payload",
    "backtest_summary_read_model_from_mapping",
    "coin_backtests_payload",
    "coin_backtests_read_model_from_mapping",
    "coin_decision_item_read_model_from_mapping",
    "coin_decision_read_model_from_mapping",
    "coin_final_signal_item_read_model_from_mapping",
    "coin_final_signal_read_model_from_mapping",
    "coin_market_decision_item_read_model_from_mapping",
    "coin_market_decision_read_model_from_mapping",
    "final_signal_read_model_from_mapping",
    "investment_decision_read_model_from_mapping",
    "market_decision_read_model_from_mapping",
    "signal_read_model_from_mapping",
    "strategy_payload",
    "strategy_performance_payload",
    "strategy_performance_read_model_from_mapping",
    "strategy_rule_payload",
    "strategy_read_model_from_mapping",
    "strategy_rule_read_model_from_mapping",
]
