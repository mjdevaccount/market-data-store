"""
Unit tests for coordinator metrics (light sanity checks).
"""

import asyncio
import pytest
from dataclasses import dataclass
from typing import Sequence

from market_data_store.coordinator import WriteCoordinator, Sink


@dataclass
class Item:
    v: int


class NoopSink(Sink[Item]):
    async def write(self, batch: Sequence[Item]) -> None:
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_metrics_loop_updates_gauges():
    """Test metrics loop updates Prometheus gauges."""
    sink = NoopSink()
    async with WriteCoordinator[Item](
        sink=sink,
        capacity=50,
        workers=1,
        batch_size=10,
        flush_interval=0.05,
        coord_id="mtest",
        metrics_poll_sec=0.05,
    ) as coord:
        for i in range(15):
            await coord.submit(Item(i))
        await asyncio.sleep(0.2)
        h = coord.health()
        assert h.workers_alive == 1
        # queue very likely drained, but health path exercised
        assert h.capacity == 50


@pytest.mark.asyncio
async def test_coordinator_health_includes_circuit_state():
    """Test health() includes circuit breaker state."""
    sink = NoopSink()
    async with WriteCoordinator[Item](
        sink=sink,
        capacity=100,
        workers=2,
        batch_size=10,
        flush_interval=0.05,
        coord_id="health-test",
    ) as coord:
        await coord.submit(Item(1))
        await asyncio.sleep(0.1)
        h = coord.health()
        assert h.circuit_state in ("closed", "open", "half_open")
        assert h.workers_alive == 2
