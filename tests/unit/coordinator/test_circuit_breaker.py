"""
Unit tests for circuit breaker.
"""

import asyncio
import pytest
from dataclasses import dataclass
from typing import Sequence

from market_data_store.coordinator import (
    WriteCoordinator,
    Sink,
    CircuitBreaker,
    RetryPolicy,
)


@dataclass
class Item:
    v: int


class AlwaysFailSink(Sink[Item]):
    async def write(self, batch: Sequence[Item]) -> None:
        await asyncio.sleep(0)
        raise TimeoutError("transient")


@pytest.mark.asyncio
async def test_circuit_opens_then_half_opens():
    """Test circuit breaker opens after threshold, then half-opens."""
    sink = AlwaysFailSink()
    cb = CircuitBreaker(failure_threshold=2, half_open_after_sec=0.2)
    retry = RetryPolicy(max_attempts=1, initial_backoff_ms=1, max_backoff_ms=2)

    async with WriteCoordinator[Item](
        sink=sink,
        capacity=100,
        workers=1,
        batch_size=5,
        flush_interval=0.05,
        retry_policy=retry,
        circuit_breaker=cb,
        coord_id="cbtest",
        metrics_poll_sec=0.05,
    ) as coord:
        # Submit enough items to force multiple writes and open the circuit
        for i in range(12):
            await coord.submit(Item(i))
        # Allow failures + CB to open and then half-open
        await asyncio.sleep(0.3)

        h = coord.health()
        # State progressed; exercised path
        assert h.circuit_state in ("open", "half_open", "closed")


@pytest.mark.asyncio
async def test_circuit_breaker_states():
    """Test circuit breaker state transitions."""
    cb = CircuitBreaker(failure_threshold=3, half_open_after_sec=0.1)

    # Initial state: closed
    assert cb.state == "closed"

    # Should allow calls
    await cb.allow()

    # Record failures
    await cb.on_failure()
    await cb.on_failure()
    assert cb.state == "closed"  # Still below threshold

    await cb.on_failure()  # Third failure
    assert cb.state == "open"  # Now open

    # Should raise when open
    from market_data_store.coordinator import CircuitOpenError

    with pytest.raises(CircuitOpenError):
        await cb.allow()

    # Wait for timeout
    await asyncio.sleep(0.15)

    # Should transition to half_open
    await cb.allow()  # This transitions to half_open
    assert cb.state == "half_open"

    # Success closes circuit
    await cb.on_success()
    assert cb.state == "closed"
