"""
Demo script for Phase 4.2A WriteCoordinator.

Shows backpressure callbacks, worker pool processing, and graceful shutdown.
"""

import asyncio
from dataclasses import dataclass
from typing import Sequence
from loguru import logger

from market_data_store.coordinator import WriteCoordinator, Sink


@dataclass
class Item:
    value: int


class PrintSink(Sink[Item]):
    """Simple sink that prints batches."""

    async def write(self, batch: Sequence[Item]) -> None:
        # Simulate I/O latency
        await asyncio.sleep(0.01)
        logger.info(
            f"PrintSink wrote batch of {len(batch)} " f"(first={batch[0].value if batch else None})"
        )


async def on_bp_high():
    logger.warning("⚠️  Backpressure HIGH (queue above high watermark)")


async def on_bp_low():
    logger.info("✅ Backpressure recovered (queue below low watermark)")


async def main():
    sink = PrintSink()
    async with WriteCoordinator[Item](
        sink=sink,
        capacity=1000,
        workers=2,
        batch_size=50,
        flush_interval=0.1,
        on_backpressure_high=on_bp_high,
        on_backpressure_low=on_bp_low,
    ) as coord:
        logger.info("🚀 Starting coordinator demo - producing 5,000 items")

        # Produce 5k items quickly to trigger backpressure
        for i in range(5_000):
            await coord.submit(Item(value=i))
            if i % 1000 == 0:
                health = coord.health()
                logger.info(
                    f"Progress: {i}/5000 | "
                    f"Queue: {health.queue_size}/{health.capacity} | "
                    f"Workers: {health.workers_alive}"
                )

        # Let workers drain for a moment (coord __aexit__ will drain too)
        logger.info("⏳ Waiting for workers to process...")
        await asyncio.sleep(0.5)

        health = coord.health()
        logger.info(
            f"Final health: alive={health.workers_alive} "
            f"queue={health.queue_size}/{health.capacity}"
        )

    logger.info("✅ Coordinator demo complete")


if __name__ == "__main__":
    asyncio.run(main())
