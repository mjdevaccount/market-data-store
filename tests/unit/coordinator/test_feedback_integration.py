"""
Integration tests for feedback system with WriteCoordinator and BoundedQueue.

Tests work with Store-extended FeedbackEvent (inherits from Core).
"""

import asyncio
import pytest
from dataclasses import dataclass
from typing import Sequence

from market_data_core.telemetry import BackpressureLevel
from market_data_store.coordinator import WriteCoordinator, Sink, FeedbackEvent, feedback_bus


@dataclass
class Item:
    """Test item."""

    v: int


class CollectSink(Sink[Item]):
    """Test sink that collects items."""

    def __init__(self, delay: float = 0.5):
        self.items: list[Item] = []
        self.delay = delay

    async def write(self, batch: Sequence[Item]) -> None:
        await asyncio.sleep(self.delay)  # Slow write to allow queue to fill
        self.items.extend(batch)


@pytest.fixture
def fresh_bus():
    """Clear singleton bus subscribers before each test."""
    bus = feedback_bus()
    # Clear subscribers
    bus._subs.clear()
    yield bus
    # Clean up after test
    bus._subs.clear()


@pytest.mark.asyncio
async def test_coordinator_emits_hard_on_high_watermark(fresh_bus):
    """Coordinator emits HARD when queue crosses high watermark."""
    events = []

    async def collector(event: FeedbackEvent):
        events.append(event)

    fresh_bus.subscribe(collector)

    sink = CollectSink(delay=1.0)  # Slow sink to let queue fill
    async with WriteCoordinator[Item](
        sink=sink,
        capacity=100,
        high_watermark=80,
        low_watermark=50,
        workers=1,
        batch_size=50,
        flush_interval=0.1,
        coord_id="test-coord",
    ) as coord:
        # Rapidly fill queue to trigger HARD
        for i in range(85):
            await coord.submit(Item(i))

        # Wait briefly for feedback emission
        await asyncio.sleep(0.05)

    # Should have emitted HARD
    hard_events = [e for e in events if e.level == BackpressureLevel.hard]
    assert len(hard_events) >= 1
    assert hard_events[0].coordinator_id == "test-coord"
    assert hard_events[0].queue_size >= 80


@pytest.mark.asyncio
async def test_coordinator_emits_soft_in_midrange(fresh_bus):
    """Coordinator emits SOFT when queue is between watermarks."""
    events = []

    async def collector(event: FeedbackEvent):
        events.append(event)

    fresh_bus.subscribe(collector)

    sink = CollectSink(delay=1.0)  # Slow sink
    async with WriteCoordinator[Item](
        sink=sink,
        capacity=100,
        high_watermark=80,
        low_watermark=40,
        workers=1,
        batch_size=50,
        flush_interval=0.1,
        coord_id="test-soft",
    ) as coord:
        # Fill to mid-range (between 40 and 80)
        for i in range(60):
            await coord.submit(Item(i))

        await asyncio.sleep(0.05)

    # Should have emitted SOFT
    soft_events = [e for e in events if e.level == BackpressureLevel.soft]
    assert len(soft_events) >= 1
    assert soft_events[0].coordinator_id == "test-soft"


@pytest.mark.asyncio
async def test_coordinator_emits_ok_on_recovery(fresh_bus):
    """Coordinator emits OK when queue drains below low watermark."""
    events = []

    async def collector(event: FeedbackEvent):
        events.append(event)

    fresh_bus.subscribe(collector)

    sink = CollectSink(delay=0.5)  # Moderate delay
    async with WriteCoordinator[Item](
        sink=sink,
        capacity=100,
        high_watermark=80,
        low_watermark=30,
        workers=2,
        batch_size=25,
        flush_interval=0.05,  # Fast flush for recovery
        coord_id="test-recovery",
    ) as coord:
        # Fill queue to trigger HARD
        for i in range(85):
            await coord.submit(Item(i))

        await asyncio.sleep(0.05)  # Let HARD fire

        # Wait for queue to drain
        await asyncio.sleep(2.0)

    # Should have OK event with recovery reason
    ok_events = [e for e in events if e.level == BackpressureLevel.ok]
    assert len(ok_events) >= 1
    assert any(e.reason == "queue_recovered" for e in ok_events)


@pytest.mark.asyncio
async def test_coordinator_id_propagation(fresh_bus):
    """coordinator_id propagates correctly through feedback events."""
    events = []

    async def collector(event: FeedbackEvent):
        events.append(event)

    fresh_bus.subscribe(collector)

    sink = CollectSink(delay=1.0)
    async with WriteCoordinator[Item](
        sink=sink,
        capacity=50,
        high_watermark=40,
        workers=1,
        coord_id="custom-id-123",
    ) as coord:
        for i in range(45):
            await coord.submit(Item(i))

        await asyncio.sleep(0.05)

    # All events should have correct coordinator_id
    assert len(events) > 0, "Should have emitted at least one event"
    assert all(e.coordinator_id == "custom-id-123" for e in events)


@pytest.mark.asyncio
async def test_multiple_coordinators_distinct_ids(fresh_bus):
    """Multiple coordinators emit with distinct IDs."""
    events = []

    async def collector(event: FeedbackEvent):
        events.append(event)

    fresh_bus.subscribe(collector)

    sink1 = CollectSink(delay=1.0)
    sink2 = CollectSink(delay=1.0)

    async with WriteCoordinator[Item](
        sink=sink1,
        capacity=50,
        high_watermark=40,
        workers=1,
        coord_id="coord-A",
    ) as coord1:
        async with WriteCoordinator[Item](
            sink=sink2,
            capacity=50,
            high_watermark=40,
            workers=1,
            coord_id="coord-B",
        ) as coord2:
            # Submit to both
            for i in range(45):
                await coord1.submit(Item(i))
                await coord2.submit(Item(i))

            await asyncio.sleep(0.1)

    # Should have events from both coordinators
    coord_a_events = [e for e in events if e.coordinator_id == "coord-A"]
    coord_b_events = [e for e in events if e.coordinator_id == "coord-B"]

    assert len(coord_a_events) > 0
    assert len(coord_b_events) > 0


@pytest.mark.asyncio
async def test_feedback_with_existing_callbacks(fresh_bus):
    """Feedback events work alongside existing on_high/on_low callbacks."""
    events = []
    callback_high_fired = []
    callback_low_fired = []

    async def collector(event: FeedbackEvent):
        events.append(event)

    async def on_high():
        callback_high_fired.append(True)

    async def on_low():
        callback_low_fired.append(True)

    fresh_bus.subscribe(collector)

    sink = CollectSink(delay=0.5)
    async with WriteCoordinator[Item](
        sink=sink,
        capacity=100,
        high_watermark=80,
        low_watermark=40,
        workers=2,
        batch_size=30,
        flush_interval=0.05,
        on_backpressure_high=on_high,
        on_backpressure_low=on_low,
        coord_id="test-callbacks",
    ) as coord:
        # Trigger high
        for i in range(85):
            await coord.submit(Item(i))

        await asyncio.sleep(0.05)  # Let HARD fire

        # Wait for recovery
        await asyncio.sleep(2.0)

    # Both feedback events AND callbacks should fire
    assert len(events) > 0
    assert len(callback_high_fired) > 0
    # Low callback fires on recovery
    assert len(callback_low_fired) > 0


@pytest.mark.asyncio
async def test_feedback_event_queue_utilization(fresh_bus):
    """FeedbackEvent.utilization reflects actual queue state."""
    events = []

    async def collector(event: FeedbackEvent):
        events.append(event)

    fresh_bus.subscribe(collector)

    sink = CollectSink(delay=1.0)
    async with WriteCoordinator[Item](
        sink=sink,
        capacity=100,
        high_watermark=60,
        workers=1,
        coord_id="test-util",
    ) as coord:
        for i in range(65):
            await coord.submit(Item(i))

        await asyncio.sleep(0.05)

    # Check utilization is reasonable
    assert len(events) > 0, "Should have emitted events"
    for event in events:
        assert 0.0 <= event.utilization <= 1.0
        assert event.capacity == 100
