"""
Smoke test for Phase 4.1 sinks.

Tests basic import and context manager behavior without database.
"""

import asyncio
from datetime import datetime, date, timezone
from unittest.mock import AsyncMock, MagicMock
from mds_client.models import Bar, OptionSnap, Fundamentals, News
from market_data_store.sinks import BarsSink, OptionsSink, FundamentalsSink, NewsSink


async def test_bars_sink_smoke():
    """Smoke test: BarsSink with mock AMDS."""
    print("  🧪 Testing BarsSink...")

    # Mock AMDS
    mock_amds = MagicMock()
    mock_amds.upsert_bars = AsyncMock(return_value=None)
    mock_amds.config = {"tenant_id": "test-tenant-id"}

    # Create bar
    bar = Bar(
        tenant_id="test-tenant-id",
        vendor="ibkr",
        symbol="AAPL",
        timeframe="1m",
        ts=datetime.now(timezone.utc),
        open_price=190.0,
        high_price=191.0,
        low_price=189.5,
        close_price=190.8,
        volume=100,
    )

    # Test sink
    async with BarsSink(mock_amds) as sink:
        await sink.write([bar])

    # Verify
    assert mock_amds.upsert_bars.called
    print("    ✅ BarsSink OK")


async def test_options_sink_smoke():
    """Smoke test: OptionsSink with mock AMDS."""
    print("  🧪 Testing OptionsSink...")

    mock_amds = MagicMock()
    mock_amds.upsert_options = AsyncMock(return_value=None)

    option = OptionSnap(
        tenant_id="test-tenant-id",
        vendor="ibkr",
        symbol="AAPL",
        expiry=date(2025, 12, 20),
        option_type="C",
        strike=200.0,
        ts=datetime.now(timezone.utc),
        iv=0.25,
        delta=0.55,
    )

    async with OptionsSink(mock_amds) as sink:
        await sink.write([option])

    assert mock_amds.upsert_options.called
    print("    ✅ OptionsSink OK")


async def test_fundamentals_sink_smoke():
    """Smoke test: FundamentalsSink with mock AMDS."""
    print("  🧪 Testing FundamentalsSink...")

    mock_amds = MagicMock()
    mock_amds.upsert_fundamentals = AsyncMock(return_value=None)

    fund = Fundamentals(
        tenant_id="test-tenant-id",
        vendor="alpha",
        symbol="AAPL",
        asof=datetime.now(timezone.utc),
        eps=6.13,
    )

    async with FundamentalsSink(mock_amds) as sink:
        await sink.write([fund])

    assert mock_amds.upsert_fundamentals.called
    print("    ✅ FundamentalsSink OK")


async def test_news_sink_smoke():
    """Smoke test: NewsSink with mock AMDS."""
    print("  🧪 Testing NewsSink...")

    mock_amds = MagicMock()
    mock_amds.upsert_news = AsyncMock(return_value=None)

    news = News(
        tenant_id="test-tenant-id",
        vendor="reuters",
        published_at=datetime.now(timezone.utc),
        title="Test News",
        sentiment_score=0.8,
    )

    async with NewsSink(mock_amds) as sink:
        await sink.write([news])

    assert mock_amds.upsert_news.called
    print("    ✅ NewsSink OK")


async def test_context_manager_lifecycle():
    """Test context manager open/close lifecycle."""
    print("  🧪 Testing context manager lifecycle...")

    mock_amds = MagicMock()
    mock_amds.upsert_bars = AsyncMock(return_value=None)

    sink = BarsSink(mock_amds)
    assert not sink._closed

    async with sink:
        assert not sink._closed

    assert sink._closed
    print("    ✅ Context manager lifecycle OK")


async def test_metrics_registration():
    """Verify metrics are registered and functional."""
    print("  🧪 Testing metrics registration...")

    from market_data_store.sinks import SINK_WRITES_TOTAL, SINK_WRITE_LATENCY

    # Check metrics exist and are usable
    assert SINK_WRITES_TOTAL is not None
    assert SINK_WRITE_LATENCY is not None

    # Test that metrics can be used (labels and increment/observe)
    SINK_WRITES_TOTAL.labels(sink="test", status="success").inc()
    SINK_WRITE_LATENCY.labels(sink="test").observe(0.001)

    # Verify metrics have correct names
    # Note: Prometheus Counter automatically appends "_total" suffix
    assert hasattr(SINK_WRITES_TOTAL, "_name")
    assert hasattr(SINK_WRITE_LATENCY, "_name")
    assert SINK_WRITES_TOTAL._name == "sink_writes"  # "_total" added automatically
    assert SINK_WRITE_LATENCY._name == "sink_write_latency_seconds"

    print("    ✅ Metrics registered and functional OK")


async def main():
    """Run all smoke tests."""
    print("\n🚀 Phase 4.1 Sinks - Smoke Test")
    print("=" * 50)

    await test_bars_sink_smoke()
    await test_options_sink_smoke()
    await test_fundamentals_sink_smoke()
    await test_news_sink_smoke()
    await test_context_manager_lifecycle()
    await test_metrics_registration()

    print("\n" + "=" * 50)
    print("✅ All smoke tests passed!")
    print("\nNext: Run unit tests with `pytest tests/unit/sinks/`")


if __name__ == "__main__":
    asyncio.run(main())
