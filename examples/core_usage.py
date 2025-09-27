"""
Example usage of Market Data Store Client for Market Data Core.

This demonstrates how Core would import and use the mds_client library.
"""

import asyncio
from datetime import datetime, date
from mds_client import MDS, AMDS, Bar, Fundamentals, News, OptionSnap


def sync_example():
    """Synchronous usage example."""
    print("=== Synchronous Usage ===")

    # Configuration
    cfg = {
        "dsn": "postgresql://postgres:postgres@127.0.0.1:5432/market_data"
        "?application_name=core-writer"
        "&options=-c%20app.tenant_id%3D6b6a6a8a-3e2e-4a8e-9c3d-9ef0ffa4d111",
        "pool_min": 1,
        "pool_max": 8,
        "statement_timeout_ms": 30000,
    }

    # Create client
    mds = MDS(cfg)

    # Health check
    health = mds.health()
    print(f"Health: {health}")

    # Write quotes -> bars
    bars = [
        Bar(
            tenant_id="6b6a6a8a-3e2e-4a8e-9c3d-9ef0ffa4d111",
            vendor="ibkr",
            symbol="AAPL",
            timeframe="1m",
            ts=datetime.now(),
            open_price=150.0,
            high_price=151.0,
            low_price=149.5,
            close_price=150.5,
            volume=1000,
        ),
        Bar(
            tenant_id="6b6a6a8a-3e2e-4a8e-9c3d-9ef0ffa4d111",
            vendor="ibkr",
            symbol="MSFT",
            timeframe="1m",
            ts=datetime.now(),
            open_price=300.0,
            high_price=301.0,
            low_price=299.0,
            close_price=300.5,
            volume=500,
        ),
    ]

    count = mds.upsert_bars(bars)
    print(f"Inserted {count} bars")

    # Fetch latest snapshots for hot cache
    prices = mds.latest_prices(["AAPL", "MSFT"], vendor="ibkr")
    print(f"Latest prices: {[(p.symbol, p.price) for p in prices]}")


async def async_example():
    """Asynchronous usage example."""
    print("\n=== Asynchronous Usage ===")

    # Configuration
    cfg = {
        "dsn": "postgresql://postgres:postgres@127.0.0.1:5432/market_data"
        "?application_name=core-async"
        "&options=-c%20app.tenant_id%3D6b6a6a8a-3e2e-4a8e-9c3d-9ef0ffa4d111",
        "pool_min": 2,
        "pool_max": 10,
    }

    # Create async client
    amds = AMDS(cfg)

    # Health check
    health = await amds.health()
    print(f"Health: {health}")

    # Write options snapshots
    options = [
        OptionSnap(
            tenant_id="6b6a6a8a-3e2e-4a8e-9c3d-9ef0ffa4d111",
            vendor="ibkr",
            symbol="AAPL",
            expiry=date(2024, 12, 20),
            option_type="C",
            strike=200.0,
            ts=datetime.now(),
            iv=0.34,
            delta=0.55,
            gamma=0.012,
            oi=123,
            volume=45,
            spot=191.25,
        )
    ]

    count = await amds.upsert_options(options)
    print(f"Inserted {count} options")

    # Write fundamentals
    fundamentals = [
        Fundamentals(
            tenant_id="6b6a6a8a-3e2e-4a8e-9c3d-9ef0ffa4d111",
            vendor="ibkr",
            symbol="AAPL",
            asof=datetime.now(),
            total_assets=1000000.0,
            total_liabilities=500000.0,
            net_income=100000.0,
            eps=6.0,
        )
    ]

    count = await amds.upsert_fundamentals(fundamentals)
    print(f"Inserted {count} fundamentals")

    # Write news
    news = [
        News(
            tenant_id="6b6a6a8a-3e2e-4a8e-9c3d-9ef0ffa4d111",
            vendor="reuters",
            title="Apple reports strong Q4 earnings",
            published_at=datetime.now(),
            symbol="AAPL",
            url="https://example.com/news/apple-earnings",
            sentiment_score=0.8,
        )
    ]

    count = await amds.upsert_news(news)
    print(f"Inserted {count} news items")


def batch_example():
    """Batch processing example."""
    print("\n=== Batch Processing ===")

    from mds_client.batch import BatchProcessor, BatchConfig

    cfg = {
        "dsn": "postgresql://postgres:postgres@127.0.0.1:5432/market_data"
        "?options=-c%20app.tenant_id%3D6b6a6a8a-3e2e-4a8e-9c3d-9ef0ffa4d111",
    }

    mds = MDS(cfg)

    # Batch configuration
    batch_config = BatchConfig(
        max_rows=100,
        max_bytes=1024 * 1024,  # 1MB
        max_ms=5000,  # 5 seconds
    )

    processor = BatchProcessor(mds, batch_config)

    # Add multiple bars (will auto-flush when limits reached)
    for i in range(150):  # Will trigger flush at 100 rows
        bar = Bar(
            tenant_id="6b6a6a8a-3e2e-4a8e-9c3d-9ef0ffa4d111",
            vendor="ibkr",
            symbol="AAPL",
            timeframe="1m",
            ts=datetime.now(),
            close_price=150.0 + i * 0.1,
            volume=1000 + i,
        )
        processor.add_bar(bar)

    # Flush remaining
    processor.flush_all()

    stats = processor.get_stats()
    print(f"Batch stats: {stats.total_rows} rows, {stats.total_batches} batches")


if __name__ == "__main__":
    # Run examples
    sync_example()
    asyncio.run(async_example())
    batch_example()

    print("\n=== Examples Complete ===")
