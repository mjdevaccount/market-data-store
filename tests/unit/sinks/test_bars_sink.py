"""
Unit tests for BarsSink.
"""

import pytest
from datetime import datetime, timezone
from market_data_store.sinks import BarsSink
from mds_client.models import Bar


@pytest.mark.asyncio
async def test_bars_sink_success(mock_amds_success):
    """Test successful bar write."""
    bar = Bar(
        tenant_id="test-tenant-id",
        vendor="ibkr",
        symbol="AAPL",
        timeframe="1m",
        ts=datetime.now(timezone.utc),
        open_price=1.0,
        high_price=2.0,
        low_price=0.5,
        close_price=1.5,
        volume=10,
    )
    sink = BarsSink(mock_amds_success)
    async with sink:
        await sink.write([bar])

    assert "bars" in mock_amds_success._calls
    assert mock_amds_success._calls["bars"] == 1


@pytest.mark.asyncio
async def test_bars_sink_multiple(mock_amds_success):
    """Test writing multiple bars."""
    bars = [
        Bar(
            tenant_id="test-tenant-id",
            vendor="ibkr",
            symbol="AAPL",
            timeframe="1m",
            ts=datetime.now(timezone.utc),
            close_price=150.0,
            volume=1000,
        ),
        Bar(
            tenant_id="test-tenant-id",
            vendor="ibkr",
            symbol="MSFT",
            timeframe="1m",
            ts=datetime.now(timezone.utc),
            close_price=420.0,
            volume=500,
        ),
    ]
    sink = BarsSink(mock_amds_success)
    async with sink:
        await sink.write(bars)

    assert mock_amds_success._calls["bars"] == 2


@pytest.mark.asyncio
async def test_bars_sink_failure(mock_amds_failure):
    """Test bar write failure handling."""
    bar = Bar(
        tenant_id="test-tenant-id",
        vendor="ibkr",
        symbol="MSFT",
        timeframe="1m",
        ts=datetime.now(timezone.utc),
        close_price=420.0,
        volume=5,
    )
    sink = BarsSink(mock_amds_failure)
    with pytest.raises(RuntimeError, match="DB unavailable"):
        async with sink:
            await sink.write([bar])
