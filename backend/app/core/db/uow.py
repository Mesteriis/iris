from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import AsyncSessionLocal


class AsyncUnitOfWork(AbstractAsyncContextManager["AsyncUnitOfWork"]):
    def __init__(self) -> None:
        self.session: AsyncSession = AsyncSessionLocal()

    async def __aenter__(self) -> "AsyncUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is None:
            await self.session.commit()
        else:
            await self.session.rollback()
        await self.session.close()


@asynccontextmanager
async def async_session_scope() -> AsyncIterator[AsyncSession]:
    uow = AsyncUnitOfWork()
    try:
        async with uow:
            yield uow.session
    finally:
        await uow.session.close()
