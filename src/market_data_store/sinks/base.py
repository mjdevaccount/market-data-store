"""
BaseSink – async context manager + Prometheus metrics.
"""

import time
from abc import ABC, abstractmethod
from typing import Sequence, Callable, Awaitable
from loguru import logger
from prometheus_client import Counter, Histogram

# Auto-registered metrics (global REGISTRY)
SINK_WRITES_TOTAL = Counter(
    "sink_writes_total",
    "Number of sink write attempts",
    ["sink", "status"],
)
SINK_WRITE_LATENCY = Histogram(
    "sink_write_latency_seconds",
    "Duration of sink writes in seconds",
    ["sink"],
)


class BaseSink(ABC):
    """Abstract base for async sinks with proper context manager protocol."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._closed = False

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
        return False  # Don't suppress exceptions

    async def connect(self) -> None:
        """Establish connections or allocate resources."""
        logger.debug(f"[{self.name}] connect()")

    async def close(self) -> None:
        """Clean up resources."""
        logger.debug(f"[{self.name}] close()")
        self._closed = True

    @abstractmethod
    async def write(self, batch: Sequence) -> None:
        """Write a batch to storage. Must be implemented by subclasses."""
        raise NotImplementedError

    async def _record_metrics(self, status: str, duration: float) -> None:
        """Record Prometheus metrics for write operation."""
        SINK_WRITES_TOTAL.labels(sink=self.name, status=status).inc()
        SINK_WRITE_LATENCY.labels(sink=self.name).observe(duration)

    async def _safe_write(self, fn: Callable[[Sequence], Awaitable[None]], batch: Sequence) -> None:
        start = time.perf_counter()
        try:
            await fn(batch)
            dur = time.perf_counter() - start
            await self._record_metrics("success", dur)
            logger.info(f"[{self.name}] wrote {len(batch)} items in {dur:.3f}s")
        except Exception as exc:
            dur = time.perf_counter() - start
            await self._record_metrics("failure", dur)
            logger.exception(f"[{self.name}] write failed after {dur:.3f}s: {exc}")
            raise
