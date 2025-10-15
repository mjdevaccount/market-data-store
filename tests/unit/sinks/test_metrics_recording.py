"""
Unit tests for metrics recording.
"""

import pytest
from datetime import datetime, timezone
from market_data_store.sinks import SINK_WRITES_TOTAL, SINK_WRITE_LATENCY, BarsSink
from mds_client.models import Bar


@pytest.mark.asyncio
async def test_metrics_success_increment(mock_amds_success):
    """Test that successful writes increment success metrics."""
    bar = Bar(
        tenant_id="test-tenant-id",
        vendor="ibkr",
        symbol="AAPL",
        timeframe="1m",
        ts=datetime.now(timezone.utc),
        close_price=150.0,
        volume=1,
    )
    sink = BarsSink(mock_amds_success)

    async with sink:
        await sink.write([bar])

    # Ensure at least one sample recorded
    samples = list(SINK_WRITES_TOTAL.collect())[0].samples
    success_samples = [
        s for s in samples if s.labels.get("sink") == "bars" and s.labels.get("status") == "success"
    ]
    assert len(success_samples) > 0


@pytest.mark.asyncio
async def test_metrics_failure_increment(mock_amds_failure):
    """Test that failed writes increment failure metrics."""
    bar = Bar(
        tenant_id="test-tenant-id",
        vendor="ibkr",
        symbol="AAPL",
        timeframe="1m",
        ts=datetime.now(timezone.utc),
        close_price=150.0,
        volume=1,
    )
    sink = BarsSink(mock_amds_failure)

    with pytest.raises(RuntimeError):
        async with sink:
            await sink.write([bar])

    # Ensure failure metric recorded
    samples = list(SINK_WRITES_TOTAL.collect())[0].samples
    failure_samples = [
        s for s in samples if s.labels.get("sink") == "bars" and s.labels.get("status") == "failure"
    ]
    assert len(failure_samples) > 0


@pytest.mark.asyncio
async def test_metrics_latency_recorded(mock_amds_success):
    """Test that write latency is recorded."""
    bar = Bar(
        tenant_id="test-tenant-id",
        vendor="ibkr",
        symbol="AAPL",
        timeframe="1m",
        ts=datetime.now(timezone.utc),
        close_price=150.0,
        volume=1,
    )
    sink = BarsSink(mock_amds_success)

    async with sink:
        await sink.write([bar])

    # Ensure latency histogram has bars sink samples
    samples = list(SINK_WRITE_LATENCY.collect())[0].samples
    bars_samples = [s for s in samples if s.labels.get("sink") == "bars"]
    assert len(bars_samples) > 0
