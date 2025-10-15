from __future__ import annotations

import asyncio
from typing import Generic, TypeVar, Optional, Literal, Awaitable, Callable

from .types import BackpressureCallback, QueueFullError

T = TypeVar("T")
OverflowStrategy = Literal["block", "drop_oldest", "error"]


class BoundedQueue(Generic[T]):
    """Bounded queue with high/low watermarks and overflow strategies."""

    def __init__(
        self,
        capacity: int,
        high_watermark: int | None = None,
        low_watermark: int | None = None,
        *,
        overflow_strategy: OverflowStrategy = "block",
        on_high: Optional[BackpressureCallback] = None,
        on_low: Optional[BackpressureCallback] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        drop_callback: Optional[Callable[[T], Awaitable[None]]] = None,
    ):
        if capacity <= 0:
            raise ValueError("capacity must be > 0")

        self._capacity = capacity
        self._q: asyncio.Queue[T] = asyncio.Queue(maxsize=capacity)
        self._size = 0  # mirrored for watermark checks

        self._high_wm = (
            high_watermark if high_watermark is not None else max(1, int(0.8 * capacity))
        )
        self._low_wm = low_watermark if low_watermark is not None else int(0.5 * capacity)
        self._overflow = overflow_strategy
        self._on_high = on_high
        self._on_low = on_low
        self._drop_cb = drop_callback

        self._loop = loop or asyncio.get_event_loop()
        self._high_fired = False  # avoid duplicate signals

        # Protect _size & signals across concurrent producers/consumers
        self._lock = asyncio.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def size(self) -> int:
        return self._size

    async def put(self, item: T) -> None:
        """Put item according to overflow policy; emits high watermark once."""
        if self._overflow == "block":
            await self._q.put(item)
            async with self._lock:
                self._size += 1
                await self._maybe_signal_high()
            return

        if self._overflow == "error":
            if self._q.full():
                raise QueueFullError("BoundedQueue is full")
            await self._q.put(item)
            async with self._lock:
                self._size += 1
                await self._maybe_signal_high()
            return

        # drop_oldest
        if self._q.full():
            # Remove one oldest
            oldest = await self._q.get()
            async with self._lock:
                self._size -= 1
            if self._drop_cb:
                await self._drop_cb(oldest)

        await self._q.put(item)
        async with self._lock:
            self._size += 1
            await self._maybe_signal_high()

    async def get(self, timeout: float | None = None) -> T:
        """Get item with optional timeout; emits low-watermark when recovering."""
        try:
            if timeout is None:
                item = await self._q.get()
            else:
                item = await asyncio.wait_for(self._q.get(), timeout=timeout)
        except asyncio.TimeoutError:
            raise

        async with self._lock:
            self._size -= 1
            await self._maybe_signal_low()
        return item

    async def _maybe_signal_high(self) -> None:
        if not self._high_fired and self._size >= self._high_wm:
            self._high_fired = True
            if self._on_high:
                await self._on_high()

    async def _maybe_signal_low(self) -> None:
        if self._high_fired and self._size <= self._low_wm:
            self._high_fired = False
            if self._on_low:
                await self._on_low()
