"""
Unit tests for SinkWorker retry logic.
"""

import asyncio
import pytest
from typing import Sequence

from market_data_store.coordinator import (
    BoundedQueue,
    SinkWorker,
    RetryPolicy,
    Sink,
)


class FlakySink(Sink[int]):
    """Sink that fails first N attempts, then succeeds."""

    def __init__(self, fail_first_n: int = 1):
        self._fail = fail_first_n
        self.batches = []

    async def write(self, batch: Sequence[int]) -> None:
        if self._fail > 0:
            self._fail -= 1
            raise TimeoutError("transient")
        self.batches.append(list(batch))


@pytest.mark.asyncio
async def test_worker_retries_then_succeeds():
    """Test worker retries on transient errors and eventually succeeds."""
    q = BoundedQueue[int](capacity=100)
    sink = FlakySink(fail_first_n=2)
    worker = SinkWorker[int](
        worker_id=1,
        queue=q,
        sink=sink,
        batch_size=5,
        flush_interval=0.05,
        retry_policy=RetryPolicy(max_attempts=5, initial_backoff_ms=1, max_backoff_ms=5),
    )
    worker.start()

    for i in range(10):
        await q.put(i)

    await asyncio.sleep(0.3)  # let it flush a couple times
    await worker.stop()

    # Expect two batches (5 each)
    assert len(sink.batches) >= 2
    assert sum(len(b) for b in sink.batches) == 10


@pytest.mark.asyncio
async def test_worker_exhaust_retries():
    """Test worker raises after exhausting retries."""

    class AlwaysFailSink(Sink[int]):
        async def write(self, batch: Sequence[int]) -> None:
            raise TimeoutError("always fails")

    q = BoundedQueue[int](capacity=100)
    sink = AlwaysFailSink()
    worker = SinkWorker[int](
        worker_id=1,
        queue=q,
        sink=sink,
        batch_size=5,
        flush_interval=0.05,
        retry_policy=RetryPolicy(max_attempts=3, initial_backoff_ms=1, max_backoff_ms=5),
    )
    worker.start()

    # Add items
    for i in range(5):
        await q.put(i)

    # Wait and expect worker task to fail
    await asyncio.sleep(0.2)

    # Worker task should be done and have exception
    assert worker._task.done()
    with pytest.raises(TimeoutError):
        await worker._task


@pytest.mark.asyncio
async def test_worker_time_based_flush():
    """Test worker flushes based on time interval."""

    class RecordingSink(Sink[int]):
        def __init__(self):
            self.batches = []

        async def write(self, batch: Sequence[int]) -> None:
            self.batches.append(list(batch))

    q = BoundedQueue[int](capacity=100)
    sink = RecordingSink()
    worker = SinkWorker[int](
        worker_id=1,
        queue=q,
        sink=sink,
        batch_size=100,  # High batch size
        flush_interval=0.1,  # But short time interval
        retry_policy=RetryPolicy(),
    )
    worker.start()

    # Add just a few items (well below batch_size)
    for i in range(5):
        await q.put(i)

    # Wait for time-based flush
    await asyncio.sleep(0.15)
    await worker.stop()

    # Should have flushed despite small batch
    assert len(sink.batches) >= 1
    assert sum(len(b) for b in sink.batches) == 5
