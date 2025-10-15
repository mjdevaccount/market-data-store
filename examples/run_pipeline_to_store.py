"""
Phase 4.3 Integration Demo
--------------------------

Demonstrates full dataflow:
Provider (mock or real IBKR/Polygon) ➜ Market-Data-Pipeline (router)
    ➜ WriteCoordinator (bounded async queue + worker pool)
        ➜ BarsSink (AMDS → database)

The demo runs self-contained with a MockProvider emitting Bar objects.

✅ Backpressure: pipeline pauses when coordinator queue is high
✅ Retry / Circuit-Breaker / DLQ handled by coordinator layer
✅ All metrics exported to Prometheus on :9000/metrics
"""

import asyncio
import random
from typing import AsyncIterator

from loguru import logger
from prometheus_client import start_http_server

# --- Imports from your repos ---
try:
    from market_data_pipeline import ProviderRouter  # Phase 3

    HAS_PIPELINE = True
except ImportError:
    logger.warning("market-data-pipeline not installed - using standalone MockProvider")
    HAS_PIPELINE = False

from market_data_store.coordinator import (
    WriteCoordinator,
    RetryPolicy,
    CircuitBreaker,
    DeadLetterQueue,
    CoordinatorRuntimeSettings,
)
from market_data_store.sinks import BarsSink  # Phase 4.1
from mds_client import AMDS  # Database client
from mds_client.models import Bar


# ──────────────────────────────────────────────
#  Mock Provider (simulates IBKR or Polygon)
# ──────────────────────────────────────────────


class MockProvider:
    """Simple async provider streaming fake Bars."""

    async def stream_bars(self, symbols: list[str]) -> AsyncIterator[Bar]:
        logger.info(f"[MockProvider] streaming {symbols}")
        count = 0
        while True:
            sym = random.choice(symbols)
            price = 100 + random.random() * 10
            bar = Bar(
                symbol=sym,
                open=price,
                high=price + random.random(),
                low=price - random.random(),
                close=price + (random.random() - 0.5),
                volume=random.randint(1000, 2000),
            )
            yield bar
            count += 1

            # Throttle to simulate realistic rate
            await asyncio.sleep(0.05)

            # Stop after a reasonable number for demo
            if count >= 1000:
                logger.info(f"[MockProvider] reached {count} bars, stopping")
                break


# ──────────────────────────────────────────────
#  Standalone Provider Router (fallback)
# ──────────────────────────────────────────────


class SimpleProviderRouter:
    """Minimal router for standalone demo (when pipeline not installed)."""

    def __init__(self, providers: list):
        self.providers = providers

    async def stream_bars(self, symbols: list[str]) -> AsyncIterator[Bar]:
        """Stream bars from all providers (simple merge)."""
        # For simplicity, just use first provider
        if not self.providers:
            return

        provider = self.providers[0]
        async for bar in provider.stream_bars(symbols):
            yield bar


# ──────────────────────────────────────────────
#  Integration glue
# ──────────────────────────────────────────────


async def main():
    logger.info("🚀 Starting Phase 4.3 Integration Demo")

    # Start metrics endpoint
    start_http_server(9000)
    logger.info("📊 Prometheus metrics available at http://localhost:9000/metrics")

    # AMDS client (connects to Timescale/Postgres)
    amds = AMDS.from_env()
    logger.info("✅ AMDS client initialized")

    # BarsSink → uses AMDS.upsert_bars
    sink = BarsSink(amds)

    # Runtime settings
    cfg = CoordinatorRuntimeSettings()
    logger.info(
        f"⚙️  Settings: capacity={cfg.coordinator_capacity}, " f"workers={cfg.coordinator_workers}"
    )

    # Coordinator plumbing (bounded queue + workers)
    retry = RetryPolicy(max_attempts=4, initial_backoff_ms=25, max_backoff_ms=400)
    circuit = CircuitBreaker(failure_threshold=5, half_open_after_sec=15)
    dlq = DeadLetterQueue[Bar](".dlq/pipeline_bars.ndjson")

    async def on_drop(bar: Bar):
        await dlq.save([bar], RuntimeError("overflow"), {"symbol": bar.symbol})

    async def on_bp_high():
        logger.warning("⚠️  Coordinator backpressure HIGH → slowing provider")

    async def on_bp_low():
        logger.info("✅ Backpressure recovered → normal rate")

    logger.info("🎯 Starting coordinator...")

    async with (
        sink,
        WriteCoordinator[Bar](
            sink=sink,
            capacity=5_000,
            workers=4,
            batch_size=200,
            flush_interval=0.25,
            on_backpressure_high=on_bp_high,
            on_backpressure_low=on_bp_low,
            drop_callback=on_drop,
            retry_policy=retry,
            circuit_breaker=circuit,
            coord_id="pipeline-store",
        ) as coord,
    ):
        # ProviderRouter (Phase 3): normally loads configured providers
        if HAS_PIPELINE:
            router = ProviderRouter([MockProvider()])
            logger.info("✅ Using market-data-pipeline ProviderRouter")
        else:
            router = SimpleProviderRouter([MockProvider()])
            logger.info("✅ Using standalone SimpleProviderRouter")

        # Simple throttle loop: forward each bar to coordinator
        symbols = ["AAPL", "MSFT", "NVDA"]
        logger.info(f"📈 Streaming bars for symbols: {symbols}")

        bar_count = 0
        async for bar in router.stream_bars(symbols):
            await coord.submit(bar)
            bar_count += 1

            # Show progress
            if bar_count % 100 == 0:
                h = coord.health()
                logger.info(
                    f"Progress: {bar_count} bars | "
                    f"Queue: {h.queue_size}/{h.capacity} | "
                    f"Workers: {h.workers_alive} | "
                    f"Circuit: {h.circuit_state}"
                )

            # Simulate provider backpressure reaction
            if coord.health().queue_size > 4000:
                logger.warning("Queue high, pausing provider...")
                await asyncio.sleep(0.25)

        # Let coordinator drain
        logger.info("⏳ Draining coordinator queue...")
        await asyncio.sleep(1.0)

        h = coord.health()
        logger.info(
            f"📊 Final health: {h.workers_alive} workers alive | "
            f"queue {h.queue_size}/{h.capacity} | CB={h.circuit_state}"
        )

        # Show DLQ summary if any
        recs = await dlq.replay(10)
        if recs:
            logger.warning(f"💀 DLQ has {len(recs)} record(s)")
            for i, rec in enumerate(recs[:3]):
                logger.info(
                    f"   [{i+1}] error='{rec.error}' items={len(rec.items)} " f"meta={rec.metadata}"
                )
        else:
            logger.info("✅ No DLQ records — all writes successful")

    logger.info(f"✅ Integration demo complete! Processed {bar_count} bars")
    logger.info("📊 Check metrics at http://localhost:9000/metrics")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⚠️  Interrupted – shutting down gracefully")
    except Exception as e:
        logger.exception(f"❌ Error: {e}")
        raise
