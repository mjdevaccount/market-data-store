"""
High-level write coordinator with metrics, health checks, and circuit breaker.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Generic, TypeVar, Sequence, Optional, Callable, Awaitable

from loguru import logger

from .policy import RetryPolicy, CircuitBreaker
from .queue import BoundedQueue, OverflowStrategy
from .types import Sink, BackpressureCallback
from .worker import SinkWorker
from .metrics import (
    COORD_ITEMS_SUBMITTED,
    COORD_ITEMS_DROPPED,
    COORD_QUEUE_DEPTH,
    COORD_WORKERS_ALIVE,
    CB_STATE,
)

T = TypeVar("T")


@dataclass
class CoordinatorHealth:
    """Health status of the coordinator."""

    workers_alive: int
    queue_size: int
    capacity: int
    circuit_state: str


class WriteCoordinator(Generic[T]):
    """High-level coordinator for producing → queue → workers → sink."""

    def __init__(
        self,
        *,
        sink: Sink[T],
        capacity: int = 10_000,
        workers: int = 4,
        batch_size: int = 500,
        flush_interval: float = 0.25,
        high_watermark: Optional[int] = None,
        low_watermark: Optional[int] = None,
        overflow_strategy: OverflowStrategy = "block",
        on_backpressure_high: Optional[BackpressureCallback] = None,
        on_backpressure_low: Optional[BackpressureCallback] = None,
        drop_callback: Optional[Callable[[T], Awaitable[None]]] = None,
        retry_policy: Optional[RetryPolicy] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        coord_id: str = "default",
        metrics_poll_sec: float = 0.25,
    ):
        if workers <= 0:
            raise ValueError("workers must be > 0")
        if capacity <= 0:
            raise ValueError("capacity must be > 0")

        self._sink = sink
        self._coord_id = coord_id
        self._metrics_poll_sec = metrics_poll_sec
        self._cb = circuit_breaker or CircuitBreaker()

        # Wrap user-provided drop callback to also count metric
        async def _drop_with_metric(item: T) -> None:
            COORD_ITEMS_DROPPED.labels(self._coord_id, "overflow").inc()
            if drop_callback:
                await drop_callback(item)

        self._q = BoundedQueue[T](
            capacity=capacity,
            high_watermark=high_watermark,
            low_watermark=low_watermark,
            coord_id=coord_id,
            overflow_strategy=overflow_strategy,
            on_high=on_backpressure_high,
            on_low=on_backpressure_low,
            drop_callback=(_drop_with_metric if overflow_strategy == "drop_oldest" else None),
        )

        self._workers = [
            SinkWorker[T](
                worker_id=i,
                queue=self._q,
                sink=self._sink,
                batch_size=batch_size,
                flush_interval=flush_interval,
                retry_policy=retry_policy or RetryPolicy(),
                circuit_breaker=self._cb,
                coord_id=self._coord_id,
            )
            for i in range(workers)
        ]

        self._started = False
        self._metrics_task: Optional[asyncio.Task] = None

    async def __aenter__(self) -> "WriteCoordinator[T]":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop(drain=True)

    async def start(self) -> None:
        if self._started:
            return
        for w in self._workers:
            w.start()
        self._started = True
        self._metrics_task = asyncio.create_task(
            self._metrics_loop(), name=f"coord-metrics-{self._coord_id}"
        )
        logger.info(
            f"[coordinator {self._coord_id}] started "
            f"(cap={self._q.capacity}, workers={len(self._workers)})"
        )

    async def stop(self, drain: bool = True, timeout: float = 10.0) -> None:
        if not self._started:
            return

        if drain:
            start = time.perf_counter()
            while self._q.size > 0 and (time.perf_counter() - start) < timeout:
                await asyncio.sleep(0.05)
            if self._q.size > 0:
                logger.warning("[coordinator] drain timeout reached, forcing shutdown")

        # stop metrics first
        if self._metrics_task:
            self._metrics_task.cancel()
            try:
                await self._metrics_task
            except asyncio.CancelledError:
                pass

        await asyncio.gather(*(w.stop() for w in self._workers), return_exceptions=True)
        self._started = False
        logger.info(f"[coordinator {self._coord_id}] stopped")

    async def submit(self, item: T) -> None:
        """Submit a single item (observes overflow strategy)."""
        COORD_ITEMS_SUBMITTED.labels(self._coord_id).inc()
        await self._q.put(item)

    async def submit_many(self, items: Sequence[T]) -> None:
        """Submit multiple items."""
        for it in items:
            await self.submit(it)

    def health(self) -> CoordinatorHealth:
        """Get current health status."""
        # workers alive
        alive = 0
        for w in self._workers:
            t = getattr(w, "_task", None)
            if t and not t.done():
                alive += 1
        state = self._cb.state
        return CoordinatorHealth(
            workers_alive=alive,
            queue_size=self._q.size,
            capacity=self._q.capacity,
            circuit_state=state,
        )

    async def _metrics_loop(self) -> None:
        """Background task to update Prometheus gauges."""
        try:
            while True:
                COORD_QUEUE_DEPTH.labels(self._coord_id).set(self._q.size)
                # map CB state
                state_map = {"closed": 0, "open": 1, "half_open": 2}
                CB_STATE.labels(self._coord_id).set(state_map.get(self._cb.state, -1))
                COORD_WORKERS_ALIVE.labels(self._coord_id).set(
                    sum(
                        1
                        for w in self._workers
                        if getattr(w, "_task", None) and not w._task.done()  # noqa: SLF001
                    )
                )
                await asyncio.sleep(self._metrics_poll_sec)
        except asyncio.CancelledError:
            return
