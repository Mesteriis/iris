import asyncio
from collections.abc import AsyncGenerator

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.core.settings import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    pass


async_engine = create_async_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

# NOTE:
# This synchronous engine remains available intentionally for tests and legacy
# sync-only maintenance code that does not run inside the main HTTP request
# lifecycle. Runtime application code should use AsyncSessionLocal/get_db.
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


async def get_db() -> AsyncGenerator[AsyncSession]:
    db = AsyncSessionLocal()
    try:
        yield db
    finally:
        await db.close()


async def ping_database() -> None:
    async with async_engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def wait_for_database() -> None:
    last_error: Exception | None = None
    for _ in range(settings.database_connect_retries):
        try:
            await ping_database()
            return
        except Exception as exc:  # pragma: no cover
            last_error = exc
            await asyncio.sleep(settings.database_connect_retry_delay)
    if last_error is not None:
        raise last_error
