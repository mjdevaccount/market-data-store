"""
Unit tests for OptionsSink.
"""

import pytest
from datetime import datetime, date, timezone
from market_data_store.sinks import OptionsSink
from mds_client.models import OptionSnap


@pytest.mark.asyncio
async def test_options_sink_success(mock_amds_success):
    """Test successful option write."""
    opt = OptionSnap(
        tenant_id="test-tenant-id",
        vendor="ibkr",
        symbol="AAPL",
        expiry=date(2025, 12, 20),
        option_type="C",
        strike=150.0,
        ts=datetime.now(timezone.utc),
        iv=0.25,
        delta=0.55,
    )
    sink = OptionsSink(mock_amds_success)
    async with sink:
        await sink.write([opt])

    assert "options" in mock_amds_success._calls
    assert mock_amds_success._calls["options"] == 1


@pytest.mark.asyncio
async def test_options_sink_failure(mock_amds_failure):
    """Test option write failure handling."""
    opt = OptionSnap(
        tenant_id="test-tenant-id",
        vendor="ibkr",
        symbol="AAPL",
        expiry=date(2025, 12, 20),
        option_type="P",
        strike=140.0,
        ts=datetime.now(timezone.utc),
    )
    sink = OptionsSink(mock_amds_failure)
    with pytest.raises(RuntimeError, match="DB unavailable"):
        async with sink:
            await sink.write([opt])
