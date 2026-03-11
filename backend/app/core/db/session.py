from __future__ import annotations

import time
from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.settings import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ping_database() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def wait_for_database() -> None:
    last_error: Exception | None = None
    for _ in range(settings.database_connect_retries):
        try:
            ping_database()
            return
        except Exception as exc:  # pragma: no cover
            last_error = exc
            time.sleep(settings.database_connect_retry_delay)
    if last_error is not None:
        raise last_error
