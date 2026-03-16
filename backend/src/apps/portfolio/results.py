from dataclasses import dataclass

from src.apps.portfolio.read_models import PortfolioStateReadModel


@dataclass(slots=True, frozen=True)
class PortfolioSyncItem:
    exchange_account_id: int
    symbol: str
    balance: float
    value_usd: float


@dataclass(slots=True, frozen=True)
class PortfolioCachedBalanceRow:
    exchange_account_id: int
    exchange_name: str
    account_name: str
    coin_id: int
    symbol: str
    balance: float
    value_usd: float
    auto_watch_enabled: bool


@dataclass(slots=True, frozen=True)
class PortfolioPendingEvent:
    event_type: str
    payload: dict[str, object]


@dataclass(slots=True, frozen=True)
class PortfolioSyncResult:
    status: str
    accounts: int
    items: tuple[PortfolioSyncItem, ...]
    cached_rows: tuple[PortfolioCachedBalanceRow, ...]
    state: PortfolioStateReadModel
    pending_events: tuple[PortfolioPendingEvent, ...]

    @property
    def balances(self) -> int:
        return len(self.items)


@dataclass(slots=True, frozen=True)
class PortfolioActionEvaluationResult:
    status: str
    coin_id: int
    timeframe: int
    reason: str | None = None
    decision: str | None = None
    action: str | None = None
    size: float = 0.0
    portfolio_state: PortfolioStateReadModel | None = None
    pending_events: tuple[PortfolioPendingEvent, ...] = ()


@dataclass(slots=True, frozen=True)
class BalanceSyncOutcome:
    item: PortfolioSyncItem
    cached_row: PortfolioCachedBalanceRow
    pending_events: tuple[PortfolioPendingEvent, ...]


__all__ = [
    "PortfolioActionEvaluationResult",
    "PortfolioCachedBalanceRow",
    "PortfolioPendingEvent",
    "PortfolioSyncItem",
    "PortfolioSyncResult",
]
