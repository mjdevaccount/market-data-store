"""
Example: Async sink pipeline for market_data_store.

Demonstrates all four sinks (BarsSink, OptionsSink, FundamentalsSink, NewsSink)
with AMDS client integration.
"""

import asyncio
import os
from datetime import datetime, date, timezone
from mds_client import AMDS
from mds_client.models import Bar, OptionSnap, Fundamentals, News
from mds_client.runtime import boot_event_loop
from market_data_store.sinks import BarsSink, OptionsSink, FundamentalsSink, NewsSink


async def example_bars_sink(amds: AMDS):
    """Example: Write bars via BarsSink."""
    print("\n📊 BarsSink Example")

    bars = [
        Bar(
            tenant_id=amds.config["tenant_id"],
            vendor="ibkr",
            symbol="AAPL",
            timeframe="1m",
            ts=datetime.now(timezone.utc),
            open_price=190.1,
            high_price=191.5,
            low_price=189.8,
            close_price=191.9,
            volume=1000,
        ),
        Bar(
            tenant_id=amds.config["tenant_id"],
            vendor="ibkr",
            symbol="MSFT",
            timeframe="1m",
            ts=datetime.now(timezone.utc),
            open_price=420.5,
            high_price=422.3,
            low_price=420.1,
            close_price=422.1,
            volume=500,
        ),
    ]

    async with BarsSink(amds) as sink:
        await sink.write(bars)
        print(f"  ✅ Wrote {len(bars)} bars")


async def example_options_sink(amds: AMDS):
    """Example: Write options via OptionsSink."""
    print("\n📈 OptionsSink Example")

    options = [
        OptionSnap(
            tenant_id=amds.config["tenant_id"],
            vendor="ibkr",
            symbol="AAPL",
            expiry=date(2025, 12, 20),
            option_type="C",
            strike=200.0,
            ts=datetime.now(timezone.utc),
            iv=0.25,
            delta=0.55,
            gamma=0.02,
            oi=1000,
            volume=50,
            spot=191.9,
        )
    ]

    async with OptionsSink(amds) as sink:
        await sink.write(options)
        print(f"  ✅ Wrote {len(options)} options")


async def example_fundamentals_sink(amds: AMDS):
    """Example: Write fundamentals via FundamentalsSink."""
    print("\n📋 FundamentalsSink Example")

    fundamentals = [
        Fundamentals(
            tenant_id=amds.config["tenant_id"],
            vendor="alpha_vantage",
            symbol="AAPL",
            asof=datetime.now(timezone.utc),
            total_assets=352755000000.0,
            total_liabilities=290437000000.0,
            net_income=96995000000.0,
            eps=6.13,
        )
    ]

    async with FundamentalsSink(amds) as sink:
        await sink.write(fundamentals)
        print(f"  ✅ Wrote {len(fundamentals)} fundamentals")


async def example_news_sink(amds: AMDS):
    """Example: Write news via NewsSink."""
    print("\n📰 NewsSink Example")

    news = [
        News(
            tenant_id=amds.config["tenant_id"],
            vendor="reuters",
            published_at=datetime.now(timezone.utc),
            title="AAPL Reports Strong Q4 Earnings",
            symbol="AAPL",
            url="https://example.com/news/aapl-q4",
            sentiment_score=0.8,
        )
    ]

    async with NewsSink(amds) as sink:
        await sink.write(news)
        print(f"  ✅ Wrote {len(news)} news items")


async def main():
    """Run example sink pipeline."""
    # Configure event loop for cross-platform compatibility
    boot_event_loop()

    # Get configuration from environment variables
    dsn = os.getenv("MDS_DSN")
    tenant_id = os.getenv("MDS_TENANT_ID")

    if not dsn or not tenant_id:
        print("❌ Error: Set MDS_DSN and MDS_TENANT_ID environment variables")
        print("\nExample:")
        print('  $env:MDS_DSN="postgresql://user:pass@localhost:5432/marketdata"')
        print('  $env:MDS_TENANT_ID="your-tenant-uuid"')
        return

    config = {"dsn": dsn, "tenant_id": tenant_id, "pool_max": 5}

    print("🚀 market_data_store Sink Pipeline Example")
    print(f"   Tenant: {tenant_id[:8]}...")

    # Use AMDS context manager for clean pool shutdown
    async with AMDS(config) as amds:
        # Run all sink examples
        await example_bars_sink(amds)
        await example_options_sink(amds)
        await example_fundamentals_sink(amds)
        await example_news_sink(amds)

        print("\n✅ All sinks completed successfully!")
        print("\nℹ️  Check Prometheus metrics at /metrics endpoint")


if __name__ == "__main__":
    asyncio.run(main())
