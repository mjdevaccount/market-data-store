from __future__ import annotations

from typing import Protocol, TypeVar, Sequence, Awaitable, Callable, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class Sink(Protocol[T]):
    """Protocol for Phase 4.1 sinks."""

    async def write(self, batch: Sequence[T]) -> None: ...


BackpressureCallback = Callable[[], Awaitable[None]]


class QueueFullError(RuntimeError):
    """Raised when overflow_strategy='error' and queue is full."""


class Stoppable(Protocol):
    async def stop(self) -> None: ...
