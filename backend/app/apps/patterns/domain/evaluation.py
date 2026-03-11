from __future__ import annotations

from sqlalchemy.orm import Session

from app.apps.patterns.domain.context import refresh_recent_signal_contexts
from app.apps.patterns.domain.decision import refresh_investment_decisions
from app.apps.patterns.domain.risk import refresh_final_signals
from app.apps.patterns.domain.statistics import refresh_pattern_statistics
from app.apps.signals.history import refresh_signal_history


def run_pattern_evaluation_cycle(db: Session) -> dict[str, object]:
    history_result = refresh_signal_history(db, lookback_days=365, commit=True)
    statistics_result = refresh_pattern_statistics(db)
    context_result = refresh_recent_signal_contexts(db, lookback_days=30)
    decision_result = refresh_investment_decisions(db, lookback_days=30, emit_events=False)
    final_signal_result = refresh_final_signals(db, lookback_days=30, emit_events=False)
    return {
        "status": "ok",
        "signal_history": history_result,
        "statistics": statistics_result,
        "context": context_result,
        "decisions": decision_result,
        "final_signals": final_signal_result,
    }
