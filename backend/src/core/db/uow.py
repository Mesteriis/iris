from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db.persistence import PERSISTENCE_LOGGER
from src.core.db.session import AsyncSessionLocal


class BaseAsyncUnitOfWork(AbstractAsyncContextManager["BaseAsyncUnitOfWork"]):
    def __init__(self, session: AsyncSession, *, owns_session: bool) -> None:
        self._session = session
        self._owns_session = owns_session
        self._uow_id = uuid4().hex[:8]
        self._after_commit_actions: list[Callable[[], object]] = []

    @property
    def session(self) -> AsyncSession:
        return self._session

    def add_after_commit_action(self, action: Callable[[], Awaitable[object] | object]) -> None:
        self._after_commit_actions.append(action)

    async def __aenter__(self) -> BaseAsyncUnitOfWork:
        PERSISTENCE_LOGGER.debug(
            "uow.begin",
            extra={"persistence": {"event": "uow.begin", "uow_id": self._uow_id}},
        )
        return self

    async def commit(self) -> None:
        PERSISTENCE_LOGGER.debug(
            "uow.commit",
            extra={"persistence": {"event": "uow.commit", "uow_id": self._uow_id}},
        )
        await self._session.commit()
        actions = self._after_commit_actions
        self._after_commit_actions = []
        for action in actions:
            result = action()
            if inspect.isawaitable(result):
                await result

    async def rollback(self) -> None:
        PERSISTENCE_LOGGER.debug(
            "uow.rollback",
            extra={"persistence": {"event": "uow.rollback", "uow_id": self._uow_id}},
        )
        await self._session.rollback()
        self._after_commit_actions = []

    async def flush(self) -> None:
        PERSISTENCE_LOGGER.debug(
            "uow.flush",
            extra={"persistence": {"event": "uow.flush", "uow_id": self._uow_id}},
        )
        await self._session.flush()

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is None:
            if self._transaction_is_open():
                PERSISTENCE_LOGGER.debug(
                    "uow.rollback_uncommitted",
                    extra={"persistence": {"event": "uow.rollback_uncommitted", "uow_id": self._uow_id}},
                )
                await self._session.rollback()
                self._after_commit_actions = []
        else:
            PERSISTENCE_LOGGER.exception(
                "uow.exit_error",
                extra={"persistence": {"event": "uow.exit_error", "uow_id": self._uow_id}},
            )
            await self._session.rollback()
            self._after_commit_actions = []
        if self._owns_session:
            await self._session.close()

    def _transaction_is_open(self) -> bool:
        in_transaction = getattr(self._session, "in_transaction", None)
        if callable(in_transaction):
            return bool(in_transaction())
        return True


class AsyncUnitOfWork(BaseAsyncUnitOfWork):
    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession] | None = None,
    ) -> None:
        if session_factory is None:
            session_factory = AsyncSessionLocal
        super().__init__(session_factory(), owns_session=True)


class SessionUnitOfWork(BaseAsyncUnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, owns_session=False)


async def get_uow() -> AsyncIterator[AsyncUnitOfWork]:
    async with AsyncUnitOfWork() as uow:
        yield uow


@asynccontextmanager
async def async_session_scope() -> AsyncIterator[AsyncSession]:
    async with AsyncUnitOfWork() as uow:
        yield uow.session


__all__ = [
    "AsyncUnitOfWork",
    "BaseAsyncUnitOfWork",
    "SessionUnitOfWork",
    "async_session_scope",
    "get_uow",
]
