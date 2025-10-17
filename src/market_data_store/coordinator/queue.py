from __future__ import annotations

import asyncio
from typing import Generic, TypeVar, Optional, Literal, Awaitable, Callable

from market_data_core.telemetry import BackpressureLevel

from .types import BackpressureCallback, QueueFullError
from .feedback import FeedbackEvent, feedback_bus

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
        coord_id: str = "default",
        overflow_strategy: OverflowStrategy = "block",
        on_high: Optional[BackpressureCallback] = None,
        on_low: Optional[BackpressureCallback] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        drop_callback: Optional[Callable[[T], Awaitable[None]]] = None,
    ):
        if capacity <= 0:
            raise ValueError("capacity must be > 0")

        self._capacity = capacity
        self._coord_id = coord_id
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
        self._soft_fired = False  # track soft backpressure

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

    async def _emit_feedback(self, level: BackpressureLevel, reason: str | None = None) -> None:
        """Emit feedback event to FeedbackBus using Core-compatible factory."""
        event = FeedbackEvent.create(
            coordinator_id=self._coord_id,
            queue_size=self._size,
            capacity=self._capacity,
            level=level,
            reason=reason,
        )
        await feedback_bus().publish(event)

    async def _maybe_signal_high(self) -> None:
        """Signal when queue crosses high watermark or enters soft zone."""
        # HARD: crossed high watermark
        if not self._high_fired and self._size >= self._high_wm:
            self._high_fired = True
            self._soft_fired = True
            await self._emit_feedback(BackpressureLevel.hard)
            if self._on_high:
                await self._on_high()
        # SOFT: between low and high watermarks
        elif not self._soft_fired and self._low_wm < self._size < self._high_wm:
            self._soft_fired = True
            await self._emit_feedback(BackpressureLevel.soft)

    async def _maybe_signal_low(self) -> None:
        """Signal when queue recovers below low watermark."""
        if (self._high_fired or self._soft_fired) and self._size <= self._low_wm:
            self._high_fired = False
            self._soft_fired = False
            await self._emit_feedback(BackpressureLevel.ok, reason="queue_recovered")
            if self._on_low:
                await self._on_low()
