"""
Advanced demo for Phase 4.2B WriteCoordinator.

Shows:
- Prometheus metrics (exposed on :8000/metrics)
- Dead Letter Queue (file-based NDJSON)
- Circuit breaker
- Environment-based settings
- Health monitoring
"""

import asyncio
from dataclasses import dataclass
from typing import Sequence
from loguru import logger
from prometheus_client import start_http_server

from market_data_store.coordinator import (
    WriteCoordinator,
    Sink,
    DeadLetterQueue,
    RetryPolicy,
    CircuitBreaker,
    CoordinatorRuntimeSettings,
)


@dataclass
class Item:
    v: int


class FlakySink(Sink[Item]):
    """Fails sometimes to demonstrate retries + circuit breaker + DLQ."""

    def __init__(self, fail_every: int = 37):
        self._n = 0
        self.fail_every = max(2, fail_every)

    async def write(self, batch: Sequence[Item]) -> None:
        self._n += 1
        if self._n % self.fail_every == 0:
            raise TimeoutError("simulated transient failure")
        await asyncio.sleep(0.005)  # simulate I/O


async def on_bp_high():
    logger.warning("⚠️  Backpressure HIGH")


async def on_bp_low():
    logger.info("✅ Backpressure recovered")


async def main():
    # Expose metrics on :8000/metrics for demo
    start_http_server(8000)
    logger.info("📊 Prometheus metrics available at http://localhost:8000/metrics")

    # Load env-configurable settings
    cfg = CoordinatorRuntimeSettings()
    logger.info(
        f"⚙️  Loaded settings: capacity={cfg.coordinator_capacity}, workers={cfg.coordinator_workers}"
    )

    # DLQ (file)
    dlq = DeadLetterQueue[Item](".dlq/items.ndjson")
    logger.info("📁 Dead Letter Queue: .dlq/items.ndjson")

    # Flaky sink
    sink = FlakySink(fail_every=25)

    # Coordinator with CB + retry policy
    retry = RetryPolicy(
        max_attempts=5,
        initial_backoff_ms=20,
        max_backoff_ms=250,
        backoff_multiplier=2.0,
        jitter=True,
    )
    cb = CircuitBreaker(failure_threshold=4, half_open_after_sec=5.0)

    async def on_drop(item: Item):
        # Save dropped items to DLQ too (overflow)
        await dlq.save([item], RuntimeError("dropped_by_overflow"), {"reason": "overflow"})

    logger.info("🚀 Starting coordinator with Circuit Breaker and DLQ...")

    async with WriteCoordinator[Item](
        sink=sink,
        capacity=2_000,
        workers=4,
        batch_size=200,
        flush_interval=0.1,
        on_backpressure_high=on_bp_high,
        on_backpressure_low=on_bp_low,
        drop_callback=on_drop,
        retry_policy=retry,
        circuit_breaker=cb,
        coord_id="demo",
        metrics_poll_sec=0.25,
    ) as coord:
        # Produce a bunch of items quickly
        logger.info("📦 Submitting 20,000 items...")
        for i in range(20_000):
            try:
                await coord.submit(Item(i))
                if i % 5000 == 0 and i > 0:
                    h = coord.health()
                    logger.info(
                        f"Progress: {i}/20000 | "
                        f"Queue: {h.queue_size}/{h.capacity} | "
                        f"Workers: {h.workers_alive} | "
                        f"Circuit: {h.circuit_state}"
                    )
            except Exception as e:  # noqa: BLE001
                await dlq.save([Item(i)], e, {"stage": "submit"})

        # Drain for a bit, then show health
        logger.info("⏳ Draining queue...")
        await asyncio.sleep(1.0)

        h = coord.health()
        logger.info(
            f"📊 Final health: "
            f"workers={h.workers_alive} "
            f"queue={h.queue_size}/{h.capacity} "
            f"circuit={h.circuit_state}"
        )

        # Show a few DLQ replay records (if any)
        recs = await dlq.replay(3)
        if recs:
            logger.info(f"💀 Found {len(recs)} DLQ records (showing first 3):")
            for r in recs:
                logger.info(
                    f"   ts={r.ts:.0f} err='{r.error}' " f"items={len(r.items)} meta={r.metadata}"
                )
        else:
            logger.info("✅ No items in DLQ (all writes successful)")

    logger.info("✅ Coordinator demo complete")
    logger.info("📊 Check metrics at http://localhost:8000/metrics")


if __name__ == "__main__":
    asyncio.run(main())
