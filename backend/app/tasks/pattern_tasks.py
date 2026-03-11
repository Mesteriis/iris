from __future__ import annotations

from app.db.session import SessionLocal
from app.patterns.context import enrich_signal_context
from app.patterns.cycle import refresh_market_cycles
from app.patterns.decision import evaluate_investment_decision, refresh_investment_decisions
from app.patterns.discovery import refresh_discovered_patterns
from app.patterns.engine import PatternEngine
from app.patterns.evaluation import run_pattern_evaluation_cycle
from app.patterns.narrative import refresh_sector_metrics
from app.patterns.risk import evaluate_final_signal, refresh_final_signals
from app.patterns.strategy import refresh_strategies
from app.services.history_loader import get_coin_by_symbol, list_coins_ready_for_latest_sync
from app.taskiq.broker import broker
from app.taskiq.locks import redis_task_lock

PATTERN_BOOTSTRAP_LOCK_TIMEOUT_SECONDS = 7200
PATTERN_STATISTICS_LOCK_TIMEOUT_SECONDS = 7200
MARKET_STRUCTURE_LOCK_TIMEOUT_SECONDS = 7200
PATTERN_DISCOVERY_LOCK_TIMEOUT_SECONDS = 14400
STRATEGY_DISCOVERY_LOCK_TIMEOUT_SECONDS = 14400
_ENGINE = PatternEngine()


@broker.task
def patterns_bootstrap_scan(symbol: str | None = None, force: bool = False) -> dict[str, object]:
    lock_suffix = symbol.upper() if symbol is not None else "all"
    with redis_task_lock(
        f"iris:tasklock:patterns_bootstrap:{lock_suffix}",
        timeout=PATTERN_BOOTSTRAP_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "patterns_bootstrap_in_progress", "symbol": lock_suffix}

        db = SessionLocal()
        try:
            if symbol is not None:
                coin = get_coin_by_symbol(db, symbol)
                if coin is None:
                    return {"status": "error", "reason": "coin_not_found", "symbol": symbol.upper()}
                result = _ENGINE.bootstrap_coin(db, coin=coin, force=force)
                return {"status": "ok", "coins": 1, "items": [result]}

            coins = list_coins_ready_for_latest_sync(db)
            items = [_ENGINE.bootstrap_coin(db, coin=coin, force=force) for coin in coins]
            return {
                "status": "ok",
                "coins": len(coins),
                "created": sum(int(item.get("created", 0)) for item in items),
                "items": items,
            }
        finally:
            db.close()


def _run_pattern_evaluation() -> dict[str, object]:
    with redis_task_lock(
        "iris:tasklock:pattern_statistics_refresh",
        timeout=PATTERN_STATISTICS_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "pattern_statistics_refresh_in_progress"}

        db = SessionLocal()
        try:
            return run_pattern_evaluation_cycle(db)
        finally:
            db.close()


@broker.task
def pattern_evaluation_job() -> dict[str, object]:
    return _run_pattern_evaluation()


@broker.task
def update_pattern_statistics() -> dict[str, object]:
    return _run_pattern_evaluation()


@broker.task
def signal_context_enrichment(
    coin_id: int,
    timeframe: int,
    candle_timestamp: str | None = None,
) -> dict[str, object]:
    db = SessionLocal()
    try:
        context_result = enrich_signal_context(
            db,
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            candle_timestamp=candle_timestamp,
        )
        decision_result = evaluate_investment_decision(
            db,
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            emit_event=False,
        )
        final_signal_result = evaluate_final_signal(
            db,
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            emit_event=False,
        )
        return {
            "status": "ok",
            "context": context_result,
            "decision": decision_result,
            "final_signal": final_signal_result,
        }
    finally:
        db.close()


@broker.task
def refresh_market_structure() -> dict[str, object]:
    with redis_task_lock(
        "iris:tasklock:market_structure_refresh",
        timeout=MARKET_STRUCTURE_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "market_structure_refresh_in_progress"}

        db = SessionLocal()
        try:
            sector_result = refresh_sector_metrics(db)
            cycle_result = refresh_market_cycles(db)
            context_result = refresh_recent_signal_contexts(db, lookback_days=30)
            decision_result = refresh_investment_decisions(db, lookback_days=30, emit_events=False)
            final_signal_result = refresh_final_signals(db, lookback_days=30, emit_events=False)
            return {
                "status": "ok",
                "sectors": sector_result,
                "cycles": cycle_result,
                "context": context_result,
                "decisions": decision_result,
                "final_signals": final_signal_result,
            }
        finally:
            db.close()


@broker.task
def run_pattern_discovery() -> dict[str, object]:
    with redis_task_lock(
        "iris:tasklock:pattern_discovery_refresh",
        timeout=PATTERN_DISCOVERY_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "pattern_discovery_refresh_in_progress"}

        db = SessionLocal()
        try:
            return refresh_discovered_patterns(db)
        finally:
            db.close()


@broker.task
def strategy_discovery_job() -> dict[str, object]:
    with redis_task_lock(
        "iris:tasklock:strategy_discovery_refresh",
        timeout=STRATEGY_DISCOVERY_LOCK_TIMEOUT_SECONDS,
    ) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "strategy_discovery_refresh_in_progress"}

        db = SessionLocal()
        try:
            strategy_result = refresh_strategies(db)
            decision_result = refresh_investment_decisions(db, lookback_days=30, emit_events=False)
            final_signal_result = refresh_final_signals(db, lookback_days=30, emit_events=False)
            return {
                "status": "ok",
                "strategies": strategy_result,
                "decisions": decision_result,
                "final_signals": final_signal_result,
            }
        finally:
            db.close()
