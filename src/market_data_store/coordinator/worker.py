"""
Sink worker with batching, retry logic, and circuit breaker integration.
"""

from __future__ import annotations

import asyncio
import time
from typing import Sequence, Generic, TypeVar, Optional, List

from loguru import logger

from .policy import RetryPolicy, CircuitBreaker, CircuitOpenError
from .types import Sink
from .queue import BoundedQueue
from .metrics import WORKER_BATCHES_WRITTEN, WORKER_WRITE_ERRORS, WORKER_WRITE_LATENCY

T = TypeVar("T")


class SinkWorker(Generic[T]):
    """Consumes items from queue, batches, and writes to sink with retries."""

    def __init__(
        self,
        *,
        worker_id: int,
        queue: BoundedQueue[T],
        sink: Sink[T],
        batch_size: int = 500,
        flush_interval: float = 0.25,
        retry_policy: Optional[RetryPolicy] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        coord_id: str = "default",
    ):
        if batch_size <= 0:
            raise ValueError("batch_size must be > 0")
        if flush_interval <= 0.0:
            raise ValueError("flush_interval must be > 0")

        self._id = worker_id
        self._q = queue
        self._sink = sink
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._retry = retry_policy or RetryPolicy()
        self._cb = circuit_breaker
        self._coord_id = coord_id

        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run(), name=f"sink-worker-{self._id}")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            await self._task

    async def _run(self) -> None:
        logger.info(f"[worker {self._id}] started")
        batch: List[T] = []
        last_flush = time.perf_counter()

        try:
            while not self._stop_event.is_set():
                elapsed = time.perf_counter() - last_flush
                timeout = max(0.0, self._flush_interval - elapsed)

                try:
                    item = await self._q.get(timeout=timeout)
                    batch.append(item)
                except asyncio.TimeoutError:
                    pass

                if batch and (
                    len(batch) >= self._batch_size
                    or (time.perf_counter() - last_flush) >= self._flush_interval
                ):
                    await self._write_with_retry(batch)
                    batch.clear()
                    last_flush = time.perf_counter()

            if batch:
                await self._write_with_retry(batch)
                batch.clear()

        except asyncio.CancelledError:
            logger.warning(f"[worker {self._id}] cancelled")
            raise
        except Exception as exc:
            logger.exception(f"[worker {self._id}] crashed: {exc}")
            raise
        finally:
            logger.info(f"[worker {self._id}] stopped")

    async def _write_with_retry(self, batch: Sequence[T]) -> None:
        attempts = 0
        start_ts = time.perf_counter()
        try:
            while True:
                attempts += 1
                try:
                    if self._cb:
                        await self._cb.allow()
                    await self._sink.write(batch)
                    if self._cb:
                        await self._cb.on_success()
                    WORKER_BATCHES_WRITTEN.labels(self._coord_id, str(self._id)).inc()
                    return
                except CircuitOpenError:
                    # Do not attempt actual write; sleep a little
                    WORKER_WRITE_ERRORS.labels(self._coord_id, str(self._id), "circuit_open").inc()
                    await asyncio.sleep(0.05)
                except Exception as exc:  # noqa: BLE001
                    retryable = self._retry.classify_retryable(exc)
                    if not retryable or attempts >= self._retry.max_attempts:
                        WORKER_WRITE_ERRORS.labels(
                            self._coord_id, str(self._id), type(exc).__name__
                        ).inc()
                        if self._cb:
                            await self._cb.on_failure()
                        raise
                    backoff_ms = self._retry.next_backoff_ms(attempts)
                    if self._cb:
                        await self._cb.on_failure()
                    await asyncio.sleep(backoff_ms / 1000.0)
        finally:
            span = time.perf_counter() - start_ts
            WORKER_WRITE_LATENCY.labels(self._coord_id, str(self._id)).observe(span)
