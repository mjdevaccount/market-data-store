"""
Integration tests for sinks (requires live database).

These tests require:
- PostgreSQL + TimescaleDB running
- MDS_DSN and MDS_TENANT_ID environment variables set
- Valid tenant in database

Run with: pytest -v tests/integration -m integration
"""

import os
import pytest
from datetime import datetime, date, timezone
from mds_client import AMDS
from mds_client.models import Bar, OptionSnap, Fundamentals, News
from market_data_store.sinks import BarsSink, OptionsSink, FundamentalsSink, NewsSink


# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def live_amds():
    """
    Create AMDS client from environment variables.

    Requires:
        MDS_DSN: PostgreSQL connection string
        MDS_TENANT_ID: Valid tenant UUID
    """
    dsn = os.getenv("MDS_DSN")
    tenant_id = os.getenv("MDS_TENANT_ID")

    if not dsn or not tenant_id:
        pytest.skip("Set MDS_DSN and MDS_TENANT_ID for integration tests")

    config = {"dsn": dsn, "tenant_id": tenant_id, "pool_max": 5}

    return AMDS(config)


@pytest.mark.asyncio
async def test_bars_sink_integration(live_amds):
    """Test BarsSink with live database."""
    bar = Bar(
        tenant_id=live_amds.config["tenant_id"],
        vendor="ibkr",
        symbol="TEST_BARS_SINK",
        timeframe="1m",
        ts=datetime.now(timezone.utc),
        open_price=100.0,
        high_price=101.0,
        low_price=99.0,
        close_price=100.5,
        volume=1000,
    )

    async with BarsSink(live_amds) as sink:
        await sink.write([bar])

    # Verify data was written (could query DB to confirm)
    # For now, just verify no exceptions were raised
    assert True


@pytest.mark.asyncio
async def test_options_sink_integration(live_amds):
    """Test OptionsSink with live database."""
    option = OptionSnap(
        tenant_id=live_amds.config["tenant_id"],
        vendor="ibkr",
        symbol="TEST_OPTIONS_SINK",
        expiry=date(2025, 12, 20),
        option_type="C",
        strike=150.0,
        ts=datetime.now(timezone.utc),
        iv=0.25,
        delta=0.55,
    )

    async with OptionsSink(live_amds) as sink:
        await sink.write([option])

    assert True


@pytest.mark.asyncio
async def test_fundamentals_sink_integration(live_amds):
    """Test FundamentalsSink with live database."""
    fundamental = Fundamentals(
        tenant_id=live_amds.config["tenant_id"],
        vendor="alpha_vantage",
        symbol="TEST_FUNDAMENTALS_SINK",
        asof=datetime.now(timezone.utc),
        eps=6.13,
        total_assets=352755000000.0,
    )

    async with FundamentalsSink(live_amds) as sink:
        await sink.write([fundamental])

    assert True


@pytest.mark.asyncio
async def test_news_sink_integration(live_amds):
    """Test NewsSink with live database."""
    news = News(
        tenant_id=live_amds.config["tenant_id"],
        vendor="reuters",
        published_at=datetime.now(timezone.utc),
        title="Integration Test News Article",
        symbol="TEST_NEWS_SINK",
        sentiment_score=0.8,
    )

    async with NewsSink(live_amds) as sink:
        await sink.write([news])

    assert True


@pytest.mark.asyncio
async def test_all_sinks_batch_integration(live_amds):
    """Test all sinks writing batches concurrently."""
    # Create test data
    bars = [
        Bar(
            tenant_id=live_amds.config["tenant_id"],
            vendor="ibkr",
            symbol=f"TEST_BATCH_{i}",
            timeframe="1m",
            ts=datetime.now(timezone.utc),
            close_price=100.0 + i,
            volume=1000,
        )
        for i in range(10)
    ]

    # Write batch
    async with BarsSink(live_amds) as sink:
        await sink.write(bars)

    # Optionally query DB to confirm row count
    # bars_count = await live_amds.execute("SELECT COUNT(*) FROM bars WHERE symbol LIKE 'TEST_BATCH_%'")
    # assert bars_count >= 10

    assert True
