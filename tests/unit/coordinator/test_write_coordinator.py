"""
Unit tests for WriteCoordinator.
"""

import asyncio
import pytest
from dataclasses import dataclass
from typing import Sequence

from market_data_store.coordinator import WriteCoordinator, Sink


@dataclass
class Item:
    v: int


class CollectSink(Sink[Item]):
    """Sink that collects all items for verification."""

    def __init__(self):
        self.items: list[Item] = []

    async def write(self, batch: Sequence[Item]) -> None:
        await asyncio.sleep(0)  # simulate I/O
        self.items.extend(batch)


@pytest.mark.asyncio
async def test_submit_and_drain_health():
    """Test basic submit and drain with health checks."""
    sink = CollectSink()
    async with WriteCoordinator[Item](
        sink=sink,
        capacity=100,
        workers=2,
        batch_size=10,
        flush_interval=0.05,
    ) as coord:
        for i in range(47):
            await coord.submit(Item(i))
        await asyncio.sleep(0.2)
        h = coord.health()
        assert h.workers_alive == 2
        assert 0 <= h.queue_size <= 100

    # After context exit, queue drained and workers stopped
    assert len(sink.items) == 47


@pytest.mark.asyncio
async def test_backpressure_callbacks():
    """Test backpressure high/low callbacks are invoked."""
    high_called = False
    low_called = False

    async def on_high():
        nonlocal high_called
        high_called = True

    async def on_low():
        nonlocal low_called
        low_called = True

    sink = CollectSink()
    async with WriteCoordinator[Item](
        sink=sink,
        capacity=50,
        high_watermark=40,
        low_watermark=20,
        workers=1,
        batch_size=100,  # Large batch to slow down processing
        flush_interval=0.5,  # Slow flush to build up queue
        on_backpressure_high=on_high,
        on_backpressure_low=on_low,
    ) as coord:
        # Quickly submit items to hit high watermark
        for i in range(45):
            await coord.submit(Item(i))

        await asyncio.sleep(0.1)
        assert high_called

        # Wait for queue to drain
        await asyncio.sleep(1.0)
        assert low_called


@pytest.mark.asyncio
async def test_submit_many():
    """Test submit_many convenience method."""
    sink = CollectSink()
    async with WriteCoordinator[Item](
        sink=sink, capacity=100, workers=2, batch_size=10, flush_interval=0.05
    ) as coord:
        items = [Item(i) for i in range(100)]
        await coord.submit_many(items)
        await asyncio.sleep(0.3)

    assert len(sink.items) == 100


@pytest.mark.asyncio
async def test_graceful_shutdown_drain():
    """Test graceful shutdown waits for queue drain."""
    sink = CollectSink()
    coord = WriteCoordinator[Item](
        sink=sink, capacity=100, workers=2, batch_size=10, flush_interval=0.05
    )

    await coord.start()

    # Submit items
    for i in range(50):
        await coord.submit(Item(i))

    # Stop with drain
    await coord.stop(drain=True, timeout=2.0)

    # All items should be processed
    assert len(sink.items) == 50


@pytest.mark.asyncio
async def test_multiple_workers_parallel():
    """Test multiple workers process items in parallel."""

    class SlowSink(Sink[Item]):
        def __init__(self):
            self.batches = []

        async def write(self, batch: Sequence[Item]) -> None:
            await asyncio.sleep(0.05)  # Simulate slow write
            self.batches.append(list(batch))

    sink = SlowSink()
    async with WriteCoordinator[Item](
        sink=sink,
        capacity=100,
        workers=4,  # Multiple workers
        batch_size=5,
        flush_interval=0.05,
    ) as coord:
        # Submit many items
        for i in range(40):
            await coord.submit(Item(i))

        await asyncio.sleep(0.5)

    # With 4 workers, should process faster than 1 worker
    total_items = sum(len(b) for b in sink.batches)
    assert total_items == 40
    # With 4 workers, should have multiple batches processed concurrently
    assert len(sink.batches) >= 2
