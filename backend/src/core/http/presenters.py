from __future__ import annotations

from typing import Protocol, TypeVar

SourceT = TypeVar("SourceT", contravariant=True)
ResultT = TypeVar("ResultT", covariant=True)


class Presenter(Protocol[SourceT, ResultT]):
    def __call__(self, value: SourceT) -> ResultT: ...
