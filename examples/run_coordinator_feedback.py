"""
Phase 6.0A Demo: In-Process Backpressure Feedback

Demonstrates the feedback system emitting backpressure events as the
WriteCoordinator queue fills and drains.

No HTTP or external dependencies - pure in-process pub/sub.
"""

import asyncio
from dataclasses import dataclass
from typing import Sequence

from loguru import logger

from market_data_store.coordinator import (
    WriteCoordinator,
    Sink,
    feedback_bus,
    FeedbackEvent,
    BackpressureLevel,
)


@dataclass
class DemoItem:
    """Simple demo item."""

    value: int


class SlowSink(Sink[DemoItem]):
    """Intentionally slow sink to demonstrate backpressure."""

    def __init__(self, delay: float = 0.5):
        self.delay = delay
        self.written = []

    async def write(self, batch: Sequence[DemoItem]) -> None:
        await asyncio.sleep(self.delay)  # Simulate slow I/O
        self.written.extend(batch)
        logger.info(f"SlowSink wrote batch of {len(batch)} items")


async def main():
    logger.info("🚀 Phase 6.0A In-Process Feedback Demo")
    logger.info("=" * 70)

    # Track feedback events
    events = []

    async def feedback_observer(event: FeedbackEvent):
        """Observer that logs feedback events."""
        events.append(event)

        level_emoji = {
            BackpressureLevel.OK: "✅",
            BackpressureLevel.SOFT: "⚠️ ",
            BackpressureLevel.HARD: "🔴",
        }

        logger.info(
            f"{level_emoji[event.level]} Feedback: {event.level.value.upper()} - "
            f"Queue: {event.queue_size}/{event.capacity} ({event.utilization:.1%}) - "
            f"Coordinator: {event.coordinator_id}"
        )

        if event.reason:
            logger.info(f"   Reason: {event.reason}")

    # Subscribe to feedback bus
    feedback_bus().subscribe(feedback_observer)
    logger.info("📡 Subscribed to feedback bus")
    logger.info("")

    # Create slow sink to demonstrate backpressure
    sink = SlowSink(delay=0.5)

    # Create coordinator with low capacity to trigger backpressure quickly
    async with WriteCoordinator[DemoItem](
        sink=sink,
        capacity=100,
        high_watermark=80,
        low_watermark=40,
        workers=2,
        batch_size=30,
        flush_interval=0.1,
        coord_id="demo-coordinator",
    ) as coord:
        logger.info("📊 Coordinator started (capacity=100, high_wm=80, low_wm=40)")
        logger.info("")

        # Phase 1: Fill queue to trigger SOFT then HARD
        logger.info("Phase 1: Filling queue (90 items)...")
        for i in range(90):
            await coord.submit(DemoItem(i))

        await asyncio.sleep(0.1)  # Let feedback fire
        logger.info("")

        # Phase 2: Let queue drain
        logger.info("Phase 2: Waiting for queue to drain...")
        await asyncio.sleep(3.0)

        logger.info("")
        logger.info("Phase 3: Final status")
        health = coord.health()
        logger.info(f"   Workers alive: {health.workers_alive}")
        logger.info(f"   Queue size: {health.queue_size}/{health.capacity}")
        logger.info(f"   Items written: {len(sink.written)}")

    logger.info("")
    logger.info("=" * 70)
    logger.info(f"✅ Demo complete! Captured {len(events)} feedback events:")

    for i, event in enumerate(events, 1):
        logger.info(
            f"   {i}. {event.level.value.upper()} - "
            f"queue={event.queue_size}/{event.capacity} "
            f"({event.utilization:.1%})"
        )

    logger.info("")
    logger.info("🎓 Key Observations:")
    logger.info("   • SOFT emitted when queue enters mid-range (40-80)")
    logger.info("   • HARD emitted when queue crosses high watermark (≥80)")
    logger.info("   • OK emitted when queue drains below low watermark (≤40)")
    logger.info("   • Events are fire-and-forget (non-blocking)")
    logger.info("")
    logger.info("🔗 Next: See examples/run_http_feedback_demo.py for HTTP webhook demo")


if __name__ == "__main__":
    asyncio.run(main())
