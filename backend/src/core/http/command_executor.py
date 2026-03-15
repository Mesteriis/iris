from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import HTTPException

from src.core.db.uow import BaseAsyncUnitOfWork
from src.core.http.errors import DomainHttpErrorTranslator

ResultT = TypeVar("ResultT")
ResponseT = TypeVar("ResponseT")


async def execute_command(
    *,
    action: Callable[[], Awaitable[ResultT]],
    uow: BaseAsyncUnitOfWork,
    presenter: Callable[[ResultT], ResponseT],
    post_commit: Callable[[ResultT], Awaitable[object] | object] | None = None,
    translate_error: DomainHttpErrorTranslator | None = None,
) -> ResponseT:
    try:
        result = await action()
        await uow.commit()
        if post_commit is not None:
            side_effect_result = post_commit(result)
            if inspect.isawaitable(side_effect_result):
                await side_effect_result
    except Exception as exc:
        if translate_error is not None:
            http_error = translate_error(exc)
            if http_error is not None:
                raise http_error from exc
        raise
    return presenter(result)


async def execute_command_no_content(
    *,
    action: Callable[[], Awaitable[object]],
    uow: BaseAsyncUnitOfWork,
    translate_error: DomainHttpErrorTranslator | None = None,
) -> None:
    try:
        await action()
        await uow.commit()
    except Exception as exc:
        if translate_error is not None:
            http_error = translate_error(exc)
            if http_error is not None:
                raise http_error from exc
        raise
