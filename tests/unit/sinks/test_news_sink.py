"""
Unit tests for NewsSink.
"""

import pytest
from datetime import datetime, timezone
from market_data_store.sinks import NewsSink
from mds_client.models import News


@pytest.mark.asyncio
async def test_news_sink_success(mock_amds_success):
    """Test successful news write."""
    n = News(
        tenant_id="test-tenant-id",
        vendor="reuters",
        published_at=datetime.now(timezone.utc),
        title="Apple releases new chip",
        symbol="AAPL",
        sentiment_score=0.8,
    )
    sink = NewsSink(mock_amds_success)
    async with sink:
        await sink.write([n])

    assert "news" in mock_amds_success._calls
    assert mock_amds_success._calls["news"] == 1


@pytest.mark.asyncio
async def test_news_sink_failure(mock_amds_failure):
    """Test news write failure handling."""
    n = News(
        tenant_id="test-tenant-id",
        vendor="reuters",
        published_at=datetime.now(timezone.utc),
        title="Market crash",
        sentiment_score=-0.9,
    )
    sink = NewsSink(mock_amds_failure)
    with pytest.raises(RuntimeError, match="DB unavailable"):
        async with sink:
            await sink.write([n])
