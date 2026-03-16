from iris.apps.cross_market.models import Sector
from iris.apps.portfolio.models import ExchangeAccount
from iris.apps.signals.models import MarketDecision
from sqlalchemy import select
from sqlalchemy.orm import Session


def create_market_decision(
    db: Session,
    *,
    coin_id: int,
    timeframe: int,
    decision: str,
    confidence: float,
    signal_count: int = 3,
) -> MarketDecision:
    row = MarketDecision(
        coin_id=coin_id,
        timeframe=timeframe,
        decision=decision,
        confidence=confidence,
        signal_count=signal_count,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_exchange_account(
    db: Session,
    *,
    exchange_name: str,
    account_name: str = "primary",
    enabled: bool = True,
) -> ExchangeAccount:
    row = ExchangeAccount(
        exchange_name=exchange_name,
        account_name=account_name,
        api_key="test-key",
        api_secret="test-secret",
        enabled=enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_sector(db: Session, *, name: str, description: str | None = None) -> Sector:
    existing = db.scalar(select(Sector).where(Sector.name == name).limit(1))
    if existing is not None:
        return existing
    row = Sector(name=name, description=description)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
