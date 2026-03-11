from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager

from sqlalchemy.orm import Session

from app.core.db.session import SessionLocal


class UnitOfWork(AbstractContextManager["UnitOfWork"]):
    def __init__(self) -> None:
        self.session: Session = SessionLocal()

    def __enter__(self) -> "UnitOfWork":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is None:
            self.session.commit()
        else:
            self.session.rollback()
        self.session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    uow = UnitOfWork()
    try:
        with uow:
            yield uow.session
    finally:
        if uow.session.is_active:
            uow.session.close()
