"""
Benchmark harness for market_data_store sinks.
----------------------------------------------

Usage:
  python examples/benchmark_sinks.py --batches 50 --batch-size 1000 --parallel 4

Runs synthetic ingestion benchmarks comparing:
  • BarsSink
  • OptionsSink
  • FundamentalsSink
  • NewsSink

Each sink writes synthetic data through AMDS and reports:
  ops/sec, average latency, and total records written.
"""

import asyncio
import os
import random
import time
from argparse import ArgumentParser
from datetime import datetime, date, timezone
from statistics import mean
from loguru import logger

from mds_client import AMDS
from mds_client.models import Bar, OptionSnap, Fundamentals, News
from mds_client.runtime import boot_event_loop
from market_data_store.sinks import BarsSink, OptionsSink, FundamentalsSink, NewsSink


# --------------------------------------------------------------------------- #
# Synthetic Data Generators
# --------------------------------------------------------------------------- #
def make_bars(n: int, tenant_id: str):
    """Generate synthetic OHLCV bars."""
    base = random.uniform(100, 200)
    return [
        Bar(
            tenant_id=tenant_id,
            vendor="benchmark",
            symbol="AAPL",
            timeframe="1m",
            ts=datetime.now(timezone.utc),
            open_price=base,
            high_price=base + 1,
            low_price=base - 1,
            close_price=base + 0.3,
            volume=1000,
        )
        for _ in range(n)
    ]


def make_options(n: int, tenant_id: str):
    """Generate synthetic options snapshots."""
    return [
        OptionSnap(
            tenant_id=tenant_id,
            vendor="benchmark",
            symbol="AAPL",
            expiry=date(2025, 12, 20),
            option_type="C",
            strike=150.0 + i,
            ts=datetime.now(timezone.utc),
            iv=random.uniform(0.2, 0.4),
            delta=random.uniform(0.3, 0.7),
        )
        for i in range(n)
    ]


def make_fundamentals(n: int, tenant_id: str):
    """Generate synthetic fundamentals data."""
    return [
        Fundamentals(
            tenant_id=tenant_id,
            vendor="benchmark",
            symbol="AAPL",
            asof=datetime.now(timezone.utc),
            eps=random.uniform(3, 10),
            total_assets=random.uniform(300e9, 400e9),
        )
        for _ in range(n)
    ]


def make_news(n: int, tenant_id: str):
    """Generate synthetic news articles."""
    return [
        News(
            tenant_id=tenant_id,
            vendor="benchmark",
            published_at=datetime.now(timezone.utc),
            title=f"Benchmark news article #{i}",
            symbol="AAPL",
            sentiment_score=random.uniform(-1.0, 1.0),
        )
        for i in range(n)
    ]


# --------------------------------------------------------------------------- #
# Benchmark Logic
# --------------------------------------------------------------------------- #
async def bench_sink(
    name: str, sink_cls, make_data, amds, batches: int, batch_size: int, parallel: int
):
    """Run a benchmark for one sink type."""
    total_items = 0
    latencies = []
    tenant_id = amds.config["tenant_id"]

    async def worker():
        nonlocal total_items
        async with sink_cls(amds) as sink:
            for _ in range(batches // parallel):
                data = make_data(batch_size, tenant_id)
                start = time.perf_counter()
                await sink.write(data)
                lat = time.perf_counter() - start
                latencies.append(lat)
                total_items += len(data)

    start = time.perf_counter()
    await asyncio.gather(*[worker() for _ in range(parallel)])
    duration = time.perf_counter() - start

    throughput = total_items / duration if duration > 0 else 0
    avg_lat = mean(latencies) if latencies else 0
    return {
        "name": name,
        "records": total_items,
        "throughput": throughput,
        "avg_latency": avg_lat,
        "duration": duration,
    }


async def run_all(amds, batches, batch_size, parallel):
    """Run benchmarks for all sinks."""
    sinks = [
        ("BarsSink", BarsSink, make_bars),
        ("OptionsSink", OptionsSink, make_options),
        ("FundamentalsSink", FundamentalsSink, make_fundamentals),
        ("NewsSink", NewsSink, make_news),
    ]

    results = []
    for name, cls, gen in sinks:
        logger.info(f"→ Benchmarking {name} ({batches}×{batch_size}, {parallel} parallel)")
        res = await bench_sink(name, cls, gen, amds, batches, batch_size, parallel)
        results.append(res)
        logger.info(
            f"  ✓ {res['records']} records in {res['duration']:.2f}s "
            f"({res['throughput']:.0f} rec/s)"
        )
    return results


# --------------------------------------------------------------------------- #
# CLI Entrypoint
# --------------------------------------------------------------------------- #
def print_summary(results):
    """Print formatted benchmark results."""
    print("\n" + "=" * 72)
    print("Benchmark Results (Phase 4.1)")
    print("=" * 72)
    for r in results:
        print(
            f"{r['name']:<20} {r['throughput']:>10,.0f} rec/s   "
            f"avg latency {r['avg_latency']*1000:>6.1f} ms   "
            f"total {r['records']:>8,}"
        )
    print("=" * 72)


async def main_async(args):
    """Main async benchmark runner."""
    # Configure event loop
    boot_event_loop()

    # Get config from environment or use mock
    dsn = os.getenv("MDS_DSN")
    tenant_id = os.getenv("MDS_TENANT_ID")

    if not dsn or not tenant_id:
        logger.warning("MDS_DSN or MDS_TENANT_ID not set - using mock mode")
        logger.warning("Set environment variables for real database benchmarks")
        print("\n⚠️  Mock mode - no actual database writes")
        print("   Set MDS_DSN and MDS_TENANT_ID for real benchmarks\n")

        # Create mock AMDS
        from types import SimpleNamespace

        async def mock_upsert(data):
            await asyncio.sleep(0.001)  # Simulate minimal DB latency

        amds = SimpleNamespace(
            config={"tenant_id": "mock-tenant-id"},
            upsert_bars=mock_upsert,
            upsert_options=mock_upsert,
            upsert_fundamentals=mock_upsert,
            upsert_news=mock_upsert,
        )
    else:
        # Use real AMDS
        config = {
            "dsn": dsn,
            "tenant_id": tenant_id,
            "pool_max": args.parallel * 2,  # Allow for concurrency
        }
        amds = AMDS(config)
        logger.info(f"Using database: {dsn.split('@')[1] if '@' in dsn else 'localhost'}")

    # Run benchmarks
    results = await run_all(amds, args.batches, args.batch_size, args.parallel)

    # Print summary
    print_summary(results)

    # Summary stats
    total_records = sum(r["records"] for r in results)
    total_time = sum(r["duration"] for r in results)
    overall_throughput = total_records / total_time if total_time > 0 else 0

    print(f"\nOverall: {total_records:,} records in {total_time:.2f}s")
    print(f"         ({overall_throughput:,.0f} rec/s aggregate)\n")


def main():
    """CLI entrypoint."""
    parser = ArgumentParser(description="Async benchmark harness for market_data_store sinks")
    parser.add_argument("--batches", type=int, default=20, help="Number of batches per sink")
    parser.add_argument("--batch-size", type=int, default=500, help="Records per batch")
    parser.add_argument("--parallel", type=int, default=2, help="Parallel tasks per sink")
    args = parser.parse_args()

    logger.info("Starting Phase 4.1 sink benchmarks")
    logger.info(
        f"Config: {args.batches} batches × {args.batch_size} records × {args.parallel} parallel"
    )

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
