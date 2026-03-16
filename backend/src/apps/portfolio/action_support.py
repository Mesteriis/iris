from sqlalchemy.ext.asyncio import AsyncSession

from src.apps.market_data.domain import utc_now
from src.apps.market_data.repositories import CoinRepository
from src.apps.portfolio.engines import build_rebalance_plan
from src.apps.portfolio.models import PortfolioAction, PortfolioPosition
from src.apps.portfolio.repositories import PortfolioRepository
from src.apps.portfolio.results import PortfolioActionEvaluationResult, PortfolioPendingEvent
from src.apps.portfolio.support import (
    PORTFOLIO_ACTIONS,
    SIMULATION_EXCHANGE,
    calculate_position_size,
    calculate_stops,
    clamp_portfolio_value,
)
from src.core.settings import get_settings


def apply_portfolio_rebalance(
    *,
    position: PortfolioPosition,
    target_value: float,
    entry_price: float,
    atr_14: float | None,
) -> tuple[str, float]:
    plan = build_rebalance_plan(
        current_value=float(position.position_value),
        target_value=target_value,
        entry_price=entry_price,
        atr_14=atr_14,
    )
    position.position_value = plan.position_value
    position.position_size = plan.position_size
    position.stop_loss = plan.stop_loss
    position.take_profit = plan.take_profit
    if plan.action == "CLOSE_POSITION":
        position.status = "closed"
        position.closed_at = utc_now()
        return plan.action, plan.action_size
    position.entry_price = plan.entry_price
    if plan.status is not None:
        position.status = plan.status
        position.closed_at = None
    elif plan.action == "OPEN_POSITION":
        position.status = "open"
        position.closed_at = None
    return plan.action, plan.action_size


def _portfolio_action_event(
    event_type: str,
    *,
    coin_id: int,
    timeframe: int,
    timestamp,
    action_id: int,
    decision_id: int,
    size: float,
    confidence: float,
) -> PortfolioPendingEvent:
    return PortfolioPendingEvent(
        event_type,
        {
            "coin_id": coin_id,
            "timeframe": timeframe,
            "timestamp": timestamp,
            "action_id": action_id,
            "decision_id": decision_id,
            "size": size,
            "confidence": confidence,
        },
    )


class PortfolioActionCoordinator:
    def __init__(
        self,
        *,
        session: AsyncSession,
        portfolio: PortfolioRepository,
        state_support,
    ) -> None:
        self._session = session
        self._portfolio = portfolio
        self._state = state_support
        self._coins = CoinRepository(session)

    async def evaluate_portfolio_action(
        self,
        *,
        coin_id: int,
        timeframe: int,
        decision: object | None,
        emit_events: bool,
    ) -> PortfolioActionEvaluationResult:
        settings = get_settings()
        state = await self._state.refresh_portfolio_state()
        decision_row = decision or await self._portfolio.get_latest_market_decision(
            coin_id=int(coin_id),
            timeframe=int(timeframe),
        )
        if decision_row is None:
            return PortfolioActionEvaluationResult(
                status="skipped",
                reason="decision_not_found",
                coin_id=int(coin_id),
                timeframe=int(timeframe),
            )

        coin = await self._coins.get_by_id(int(coin_id))
        metrics = await self._portfolio.get_coin_metrics(coin_id=int(coin_id))
        if coin is None or metrics is None or metrics.price_current is None:
            return PortfolioActionEvaluationResult(
                status="skipped",
                reason="coin_metrics_not_found",
                coin_id=int(coin_id),
                timeframe=int(timeframe),
            )

        existing = await self._portfolio.get_open_position(coin_id=int(coin_id), timeframe=int(timeframe))
        open_count = await self._portfolio.count_open_positions()
        sector_ratio = 0.0
        if coin.sector_id is not None:
            sector_ratio = await self._portfolio.sum_sector_position_value(sector_id=int(coin.sector_id)) / max(
                float(state.total_capital),
                1e-9,
            )

        decision_confidence = float(decision_row.confidence)
        current_price = float(metrics.price_current)
        atr_14 = float(metrics.atr_14) if metrics.atr_14 is not None else None
        size_context = calculate_position_size(
            total_capital=float(state.total_capital),
            available_capital=float(state.available_capital)
            + (float(existing.position_value) if existing is not None else 0.0),
            decision_confidence=decision_confidence,
            regime=metrics.market_regime,
            price_current=current_price,
            atr_14=atr_14,
        )
        target_value = float(size_context["position_value"])
        if existing is None and open_count >= settings.portfolio_max_positions:
            target_value = 0.0
        if existing is None and sector_ratio >= settings.portfolio_max_sector_exposure:
            target_value = 0.0

        action = "HOLD_POSITION"
        action_size = 0.0
        if decision_row.decision == "BUY":
            if existing is None:
                if target_value > 0:
                    stops = calculate_stops(entry_price=current_price, atr=atr_14)
                    await self._portfolio.add_position(
                        PortfolioPosition(
                            coin_id=int(coin_id),
                            exchange_account_id=None,
                            source_exchange=SIMULATION_EXCHANGE,
                            position_type="long",
                            timeframe=int(timeframe),
                            entry_price=current_price,
                            position_size=target_value / max(current_price, 1e-9),
                            position_value=target_value,
                            stop_loss=stops.stop_loss,
                            take_profit=stops.take_profit,
                            status="open",
                            closed_at=None,
                        )
                    )
                    action = "OPEN_POSITION"
                    action_size = target_value
            else:
                action, action_size = apply_portfolio_rebalance(
                    position=existing,
                    target_value=target_value if target_value > 0 else float(existing.position_value),
                    entry_price=current_price,
                    atr_14=atr_14,
                )
        elif decision_row.decision == "SELL" and existing is not None:
            sell_target = 0.0 if decision_confidence >= 0.55 else float(existing.position_value) * 0.5
            action, action_size = apply_portfolio_rebalance(
                position=existing,
                target_value=sell_target,
                entry_price=current_price,
                atr_14=atr_14,
            )

        await self._session.flush()
        action_row = await self._portfolio.add_action(
            PortfolioAction(
                coin_id=int(coin_id),
                action=action if action in PORTFOLIO_ACTIONS else "HOLD_POSITION",
                size=max(float(action_size), 0.0),
                confidence=clamp_portfolio_value(decision_confidence, 0.0, 1.0),
                decision_id=int(decision_row.id),
            )
        )
        refreshed_state = await self._state.refresh_portfolio_state()

        pending_events: list[PortfolioPendingEvent] = []
        if emit_events:
            if action == "OPEN_POSITION":
                pending_events.append(
                    _portfolio_action_event(
                        "portfolio_position_opened",
                        coin_id=int(coin_id),
                        timeframe=int(timeframe),
                        timestamp=action_row.created_at,
                        action_id=int(action_row.id),
                        decision_id=int(decision_row.id),
                        size=float(action_size),
                        confidence=decision_confidence,
                    )
                )
            elif action == "CLOSE_POSITION":
                pending_events.append(
                    _portfolio_action_event(
                        "portfolio_position_closed",
                        coin_id=int(coin_id),
                        timeframe=int(timeframe),
                        timestamp=action_row.created_at,
                        action_id=int(action_row.id),
                        decision_id=int(decision_row.id),
                        size=float(action_size),
                        confidence=decision_confidence,
                    )
                )
            elif action in {"INCREASE_POSITION", "REDUCE_POSITION"}:
                pending_events.append(
                    _portfolio_action_event(
                        "portfolio_rebalanced",
                        coin_id=int(coin_id),
                        timeframe=int(timeframe),
                        timestamp=action_row.created_at,
                        action_id=int(action_row.id),
                        decision_id=int(decision_row.id),
                        size=float(action_size),
                        confidence=decision_confidence,
                    )
                )

        return PortfolioActionEvaluationResult(
            status="ok",
            coin_id=int(coin_id),
            timeframe=int(timeframe),
            decision=str(decision_row.decision),
            action=action,
            size=float(action_size),
            portfolio_state=refreshed_state,
            pending_events=tuple(pending_events),
        )


__all__ = ["PortfolioActionCoordinator", "apply_portfolio_rebalance"]
