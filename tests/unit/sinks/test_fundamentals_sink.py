"""
Unit tests for FundamentalsSink.
"""

import pytest
from datetime import datetime, timezone
from market_data_store.sinks import FundamentalsSink
from mds_client.models import Fundamentals


@pytest.mark.asyncio
async def test_fundamentals_sink_success(mock_amds_success):
    """Test successful fundamentals write."""
    f = Fundamentals(
        tenant_id="test-tenant-id",
        vendor="alpha_vantage",
        symbol="AAPL",
        asof=datetime.now(timezone.utc),
        eps=6.13,
        total_assets=352755000000.0,
    )
    sink = FundamentalsSink(mock_amds_success)
    async with sink:
        await sink.write([f])

    assert "fundamentals" in mock_amds_success._calls
    assert mock_amds_success._calls["fundamentals"] == 1


@pytest.mark.asyncio
async def test_fundamentals_sink_failure(mock_amds_failure):
    """Test fundamentals write failure handling."""
    f = Fundamentals(
        tenant_id="test-tenant-id",
        vendor="alpha_vantage",
        symbol="MSFT",
        asof=datetime.now(timezone.utc),
        eps=10.5,
    )
    sink = FundamentalsSink(mock_amds_failure)
    with pytest.raises(RuntimeError, match="DB unavailable"):
        async with sink:
            await sink.write([f])
