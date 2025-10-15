"""
Unit tests for FeedbackBus and feedback system.
"""

import asyncio
import pytest

from market_data_store.coordinator.feedback import (
    BackpressureLevel,
    FeedbackEvent,
    FeedbackBus,
    feedback_bus,
)


@pytest.fixture
def bus():
    """Fresh FeedbackBus for each test."""
    return FeedbackBus()


@pytest.fixture
def event():
    """Sample feedback event."""
    return FeedbackEvent(
        coordinator_id="test-coord",
        queue_size=8000,
        capacity=10000,
        level=BackpressureLevel.HARD,
        reason="high_watermark",
    )


@pytest.mark.asyncio
async def test_feedback_event_immutable(event):
    """FeedbackEvent is frozen (immutable)."""
    with pytest.raises(Exception):  # dataclass frozen raises on assignment
        event.queue_size = 9000  # type: ignore


@pytest.mark.asyncio
async def test_feedback_event_utilization():
    """FeedbackEvent.utilization calculates percentage correctly."""
    event = FeedbackEvent(
        coordinator_id="test",
        queue_size=7500,
        capacity=10000,
        level=BackpressureLevel.SOFT,
    )
    assert event.utilization == 0.75  # 75%


@pytest.mark.asyncio
async def test_feedback_event_utilization_zero_capacity():
    """FeedbackEvent.utilization handles zero capacity gracefully."""
    event = FeedbackEvent(
        coordinator_id="test",
        queue_size=0,
        capacity=0,
        level=BackpressureLevel.OK,
    )
    assert event.utilization == 0.0


@pytest.mark.asyncio
async def test_subscribe_and_publish(bus, event):
    """Subscribe to feedback and receive published events."""
    received = []

    async def subscriber(evt: FeedbackEvent):
        received.append(evt)

    bus.subscribe(subscriber)
    await bus.publish(event)

    assert len(received) == 1
    assert received[0] is event
    assert received[0].level == BackpressureLevel.HARD


@pytest.mark.asyncio
async def test_multiple_subscribers(bus, event):
    """Multiple subscribers receive the same event."""
    received1 = []
    received2 = []

    async def sub1(evt: FeedbackEvent):
        received1.append(evt)

    async def sub2(evt: FeedbackEvent):
        received2.append(evt)

    bus.subscribe(sub1)
    bus.subscribe(sub2)
    await bus.publish(event)

    assert len(received1) == 1
    assert len(received2) == 1
    assert received1[0] is event
    assert received2[0] is event


@pytest.mark.asyncio
async def test_unsubscribe(bus, event):
    """Unsubscribe removes subscriber."""
    received = []

    async def subscriber(evt: FeedbackEvent):
        received.append(evt)

    bus.subscribe(subscriber)
    bus.unsubscribe(subscriber)
    await bus.publish(event)

    assert len(received) == 0


@pytest.mark.asyncio
async def test_unsubscribe_not_found(bus):
    """Unsubscribe is safe when callback not found."""

    async def subscriber(evt: FeedbackEvent):
        pass

    # Should not raise
    bus.unsubscribe(subscriber)


@pytest.mark.asyncio
async def test_subscribe_duplicate_ignored(bus, event):
    """Subscribing the same callback twice is idempotent."""
    received = []

    async def subscriber(evt: FeedbackEvent):
        received.append(evt)

    bus.subscribe(subscriber)
    bus.subscribe(subscriber)  # Second subscribe
    await bus.publish(event)

    # Should only receive once
    assert len(received) == 1


@pytest.mark.asyncio
async def test_subscriber_exception_isolation(bus, event):
    """One subscriber's exception doesn't affect others."""
    received = []

    async def bad_subscriber(evt: FeedbackEvent):
        raise RuntimeError("Intentional error")

    async def good_subscriber(evt: FeedbackEvent):
        received.append(evt)

    bus.subscribe(bad_subscriber)
    bus.subscribe(good_subscriber)

    # Should not raise, good_subscriber should still receive
    await bus.publish(event)

    assert len(received) == 1
    assert received[0] is event


@pytest.mark.asyncio
async def test_no_subscribers_no_error(bus, event):
    """Publishing with no subscribers is safe."""
    # Should not raise
    await bus.publish(event)


@pytest.mark.asyncio
async def test_subscriber_count(bus):
    """subscriber_count returns correct count."""
    assert bus.subscriber_count == 0

    async def sub1(evt: FeedbackEvent):
        pass

    async def sub2(evt: FeedbackEvent):
        pass

    bus.subscribe(sub1)
    assert bus.subscriber_count == 1

    bus.subscribe(sub2)
    assert bus.subscriber_count == 2

    bus.unsubscribe(sub1)
    assert bus.subscriber_count == 1


@pytest.mark.asyncio
async def test_feedback_bus_singleton():
    """feedback_bus() returns singleton instance."""
    bus1 = feedback_bus()
    bus2 = feedback_bus()

    assert bus1 is bus2


@pytest.mark.asyncio
async def test_backpressure_levels():
    """BackpressureLevel enum has expected values."""
    assert BackpressureLevel.OK.value == "ok"
    assert BackpressureLevel.SOFT.value == "soft"
    assert BackpressureLevel.HARD.value == "hard"


@pytest.mark.asyncio
async def test_feedback_event_with_reason():
    """FeedbackEvent can include optional reason."""
    event = FeedbackEvent(
        coordinator_id="test",
        queue_size=5000,
        capacity=10000,
        level=BackpressureLevel.OK,
        reason="queue_drained",
    )

    assert event.reason == "queue_drained"


@pytest.mark.asyncio
async def test_feedback_event_without_reason():
    """FeedbackEvent reason defaults to None."""
    event = FeedbackEvent(
        coordinator_id="test",
        queue_size=5000,
        capacity=10000,
        level=BackpressureLevel.OK,
    )

    assert event.reason is None


@pytest.mark.asyncio
async def test_async_subscribers(bus):
    """Subscribers can perform async operations."""
    results = []

    async def async_subscriber(evt: FeedbackEvent):
        await asyncio.sleep(0.01)  # Simulate async work
        results.append(evt.coordinator_id)

    bus.subscribe(async_subscriber)

    event = FeedbackEvent(
        coordinator_id="async-test",
        queue_size=1000,
        capacity=10000,
        level=BackpressureLevel.OK,
    )

    await bus.publish(event)

    assert len(results) == 1
    assert results[0] == "async-test"
