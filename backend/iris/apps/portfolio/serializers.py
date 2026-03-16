from iris.apps.portfolio.read_models import PortfolioStateReadModel, portfolio_state_payload
from iris.apps.portfolio.results import (
    PortfolioActionEvaluationResult,
    PortfolioCachedBalanceRow,
    PortfolioSyncItem,
    PortfolioSyncResult,
)


def portfolio_sync_item_payload(item: PortfolioSyncItem) -> dict[str, object]:
    return {
        "exchange_account_id": item.exchange_account_id,
        "symbol": item.symbol,
        "balance": item.balance,
        "value_usd": item.value_usd,
    }


def portfolio_cached_balance_row_payload(row: PortfolioCachedBalanceRow) -> dict[str, object]:
    return {
        "exchange_account_id": row.exchange_account_id,
        "exchange_name": row.exchange_name,
        "account_name": row.account_name,
        "coin_id": row.coin_id,
        "symbol": row.symbol,
        "balance": row.balance,
        "value_usd": row.value_usd,
        "auto_watch_enabled": row.auto_watch_enabled,
    }


def portfolio_state_cache_payload(state: PortfolioStateReadModel) -> dict[str, object]:
    return dict(portfolio_state_payload(state))


def portfolio_sync_result_payload(result: PortfolioSyncResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": result.status,
        "accounts": result.accounts,
        "balances": result.balances,
        "items": [portfolio_sync_item_payload(item) for item in result.items],
    }
    payload["portfolio_state"] = portfolio_state_payload(result.state)
    return payload


def portfolio_action_evaluation_payload(result: PortfolioActionEvaluationResult) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": result.status,
        "coin_id": result.coin_id,
        "timeframe": result.timeframe,
    }
    if result.reason is not None:
        payload["reason"] = result.reason
    if result.decision is not None:
        payload["decision"] = result.decision
    if result.action is not None:
        payload["action"] = result.action
    if result.status == "ok":
        payload["size"] = float(result.size)
        payload["portfolio_state"] = (
            portfolio_state_payload(result.portfolio_state) if result.portfolio_state is not None else None
        )
    return payload


__all__ = [
    "portfolio_action_evaluation_payload",
    "portfolio_cached_balance_row_payload",
    "portfolio_state_cache_payload",
    "portfolio_sync_item_payload",
    "portfolio_sync_result_payload",
]
