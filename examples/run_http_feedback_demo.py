"""
Phase 6.0A Demo: HTTP Feedback Broadcasting

Demonstrates HTTP broadcaster sending feedback events to a webhook endpoint.

Requires:
- httpx installed (pip install httpx)
- Webhook endpoint running (or use mock server)

For testing without a real endpoint, this demo uses a mock HTTP server.
"""

import asyncio
from dataclasses import dataclass
from typing import Sequence
from aiohttp import web
from loguru import logger

from market_data_store.coordinator import (
    WriteCoordinator,
    Sink,
    HttpFeedbackBroadcaster,
)


@dataclass
class DemoItem:
    """Simple demo item."""

    value: int


class SlowSink(Sink[DemoItem]):
    """Intentionally slow sink."""

    def __init__(self, delay: float = 0.5):
        self.delay = delay
        self.written = []

    async def write(self, batch: Sequence[DemoItem]) -> None:
        await asyncio.sleep(self.delay)
        self.written.extend(batch)


# Mock webhook server
webhook_events = []


async def webhook_handler(request):
    """Mock webhook endpoint that receives feedback events."""
    data = await request.json()
    webhook_events.append(data)

    level_emoji = {
        "ok": "✅",
        "soft": "⚠️ ",
        "hard": "🔴",
    }

    logger.info(
        f"{level_emoji.get(data['level'], '❓')} Webhook received: "
        f"{data['level'].upper()} - "
        f"queue={data['queue_size']}/{data['capacity']} "
        f"({data['utilization']:.1%})"
    )

    return web.Response(text="OK", status=200)


async def run_mock_server():
    """Run mock webhook server."""
    app = web.Application()
    app.router.add_post("/feedback", webhook_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 8765)
    await site.start()

    logger.info("🌐 Mock webhook server started at http://localhost:8765/feedback")
    return runner


async def main():
    logger.info("🚀 Phase 6.0A HTTP Feedback Broadcasting Demo")
    logger.info("=" * 70)

    # Start mock webhook server
    server = await run_mock_server()
    await asyncio.sleep(0.5)  # Let server start

    try:
        # Create HTTP broadcaster
        broadcaster = HttpFeedbackBroadcaster(
            endpoint="http://localhost:8765/feedback",
            timeout=2.0,
            max_retries=3,
            backoff_base=0.5,
            enabled=True,
        )

        await broadcaster.start()
        logger.info("📡 HTTP broadcaster started")
        logger.info("")

        # Create slow sink
        sink = SlowSink(delay=0.5)

        # Create coordinator
        async with WriteCoordinator[DemoItem](
            sink=sink,
            capacity=100,
            high_watermark=80,
            low_watermark=40,
            workers=2,
            batch_size=30,
            flush_interval=0.1,
            coord_id="http-demo-coordinator",
        ) as coord:
            logger.info("📊 Coordinator started")
            logger.info("")

            # Fill queue to trigger backpressure
            logger.info("Phase 1: Filling queue (90 items)...")
            for i in range(90):
                await coord.submit(DemoItem(i))

            await asyncio.sleep(0.2)  # Let feedback fire
            logger.info("")

            # Let queue drain
            logger.info("Phase 2: Draining queue...")
            await asyncio.sleep(3.0)

            logger.info("")
            health = coord.health()
            logger.info(f"Final status: {health.queue_size}/{health.capacity} queue")

        await broadcaster.stop()
        logger.info("")
        logger.info("=" * 70)
        logger.info(f"✅ Demo complete! Webhook received {len(webhook_events)} events:")

        for i, event in enumerate(webhook_events, 1):
            logger.info(
                f"   {i}. {event['level'].upper()} - "
                f"queue={event['queue_size']}/{event['capacity']}"
            )

        logger.info("")
        logger.info("🎓 HTTP Broadcasting Features:")
        logger.info("   • Async HTTP POST with retry logic")
        logger.info("   • Exponential backoff on failures")
        logger.info("   • Graceful degradation if endpoint unavailable")
        logger.info("   • JSON payload with full event data")

    finally:
        # Cleanup mock server
        await server.cleanup()
        logger.info("")
        logger.info("🛑 Mock server stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⚠️  Interrupted")
