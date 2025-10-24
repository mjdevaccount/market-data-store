"""
Unit tests for StoreClient and AsyncStoreClient.

Tests:
- Protocol-based Bar interface (duck typing)
- Batch writing and automatic flushing
- Diff-aware upserts (IS DISTINCT FROM)
- Smart batching (executemany vs COPY)
- Context manager protocol
- Metrics recording
"""

import pytest
from datetime import datetime, timezone
from dataclasses import dataclass
from unittest.mock import MagicMock, patch
from datastore.writes import StoreClient, AsyncStoreClient, Bar


@dataclass
class MockBar:
    """Mock Bar for testing (duck typing via Protocol)."""

    provider: str
    symbol: str
    interval: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class TestBarProtocol:
    """Test that Bar protocol accepts duck-typed objects."""

    def test_protocol_accepts_dataclass(self):
        """Bar protocol should accept any object with matching attributes."""
        bar = MockBar(
            provider="ibkr",
            symbol="SPY",
            interval="5min",
            ts=datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc),
            open=450.0,
            high=451.0,
            low=449.0,
            close=450.5,
            volume=1000000,
        )

        # Duck typing - should work without explicit inheritance
        assert isinstance(bar, Bar)
        assert bar.provider == "ibkr"
        assert bar.symbol == "SPY"


class TestStoreClientContextManager:
    """Test context manager protocol."""

    @patch("datastore.writes.psycopg.connect")
    def test_context_manager_connects_and_closes(self, mock_connect):
        """Context manager should establish and close connection."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        with StoreClient("postgresql://test") as client:
            assert client._conn is not None

        mock_connect.assert_called_once_with("postgresql://test")
        mock_conn.close.assert_called_once()

    @patch("datastore.writes.psycopg.connect")
    def test_write_without_context_raises_error(self, mock_connect):
        """Writing without context manager should raise RuntimeError."""
        client = StoreClient("postgresql://test")

        with pytest.raises(RuntimeError, match="must be used as context manager"):
            client.write_bars([])


class TestStoreClientBatching:
    """Test batch accumulation and flushing logic."""

    @patch("datastore.writes.psycopg.connect")
    def test_write_bars_batches_correctly(self, mock_connect):
        """Bars should be batched and flushed at batch_size boundaries."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        bars = [
            MockBar(
                "ibkr",
                f"SYM{i}",
                "1min",
                datetime(2025, 1, 1, 9, 30 + i, tzinfo=timezone.utc),
                100.0,
                101.0,
                99.0,
                100.5,
                1000,
            )
            for i in range(25)
        ]

        with StoreClient("postgresql://test") as client:
            # Batch size of 10 should flush 3 times (10, 10, 5)
            client.write_bars(bars, batch_size=10)

        # Should call executemany 3 times (assuming batch_threshold=1000, so uses UPSERT)
        assert mock_cursor.executemany.call_count == 3
        mock_conn.commit.assert_called_once()

    @patch("datastore.writes.psycopg.connect")
    def test_small_batch_uses_executemany(self, mock_connect):
        """Small batches (< threshold) should use executemany."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        bars = [
            MockBar(
                "ibkr",
                "SPY",
                "1min",
                datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc),
                100.0,
                101.0,
                99.0,
                100.5,
                1000,
            )
        ]

        with StoreClient("postgresql://test", batch_threshold=1000) as client:
            client.write_bars(bars)

        # Should use executemany (not COPY)
        mock_cursor.executemany.assert_called_once()
        mock_cursor.execute.assert_not_called()


class TestDiffAwareUpsert:
    """Test that upserts only update when values differ (IS DISTINCT FROM)."""

    @patch("datastore.writes.psycopg.connect")
    def test_upsert_sql_contains_distinct_check(self, mock_connect):
        """Upsert SQL should include IS DISTINCT FROM clauses."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        bars = [
            MockBar(
                "ibkr",
                "SPY",
                "1min",
                datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc),
                100.0,
                101.0,
                99.0,
                100.5,
                1000,
            )
        ]

        with StoreClient("postgresql://test", batch_threshold=1000) as client:
            client.write_bars(bars)

        # Check SQL contains diff-aware update logic
        called_sql = mock_cursor.executemany.call_args[0][0]
        assert "IS DISTINCT FROM" in called_sql
        assert "WHERE" in called_sql


class TestMetricsRecording:
    """Test Prometheus metrics are recorded correctly."""

    @patch("datastore.writes.BARS_WRITTEN_TOTAL")
    @patch("datastore.writes.BARS_WRITE_LATENCY")
    @patch("datastore.writes.psycopg.connect")
    def test_metrics_recorded_on_success(self, mock_connect, mock_latency, mock_total):
        """Successful writes should increment success metrics."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        bars = [
            MockBar(
                "ibkr",
                "SPY",
                "1min",
                datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc),
                100.0,
                101.0,
                99.0,
                100.5,
                1000,
            )
        ]

        with StoreClient("postgresql://test") as client:
            client.write_bars(bars)

        # Should increment success counter
        mock_total.labels.return_value.inc.assert_called()
        mock_latency.labels.return_value.observe.assert_called()

    @patch("datastore.writes.BARS_WRITTEN_TOTAL")
    @patch("datastore.writes.BARS_WRITE_LATENCY")
    @patch("datastore.writes.psycopg.connect")
    def test_metrics_recorded_on_failure(self, mock_connect, mock_latency, mock_total):
        """Failed writes should increment failure metrics."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.executemany.side_effect = Exception("DB error")
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        bars = [
            MockBar(
                "ibkr",
                "SPY",
                "1min",
                datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc),
                100.0,
                101.0,
                99.0,
                100.5,
                1000,
            )
        ]

        with pytest.raises(Exception, match="DB error"):
            with StoreClient("postgresql://test") as client:
                client.write_bars(bars)

        # Should have recorded failure metrics
        mock_total.labels.return_value.inc.assert_called()


class TestAsyncStoreClient:
    """Test AsyncStoreClient parallel API."""

    @pytest.mark.asyncio
    @patch("datastore.writes.psycopg.AsyncConnection.connect")
    async def test_async_context_manager(self, mock_connect):
        """Async context manager should work correctly."""
        from unittest.mock import AsyncMock

        mock_conn = AsyncMock()
        mock_connect.return_value = mock_conn

        async with AsyncStoreClient("postgresql://test") as client:
            assert client._conn is not None

        mock_connect.assert_called_once_with("postgresql://test")
        mock_conn.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("datastore.writes.psycopg.AsyncConnection.connect")
    async def test_async_write_bars(self, mock_connect):
        """Async write_bars should accept same interface as sync version."""
        from unittest.mock import AsyncMock, MagicMock

        mock_conn = AsyncMock()
        mock_cursor = AsyncMock()

        # Configure cursor to be a non-async method that returns an async context manager
        mock_cursor_ctx = MagicMock()
        mock_cursor_ctx.__aenter__ = AsyncMock(return_value=mock_cursor)
        mock_cursor_ctx.__aexit__ = AsyncMock(return_value=None)
        # Make cursor a regular method (not async) that returns the context manager
        mock_conn.cursor = MagicMock(return_value=mock_cursor_ctx)

        mock_connect.return_value = mock_conn

        bars = [
            MockBar(
                "ibkr",
                "SPY",
                "1min",
                datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc),
                100.0,
                101.0,
                99.0,
                100.5,
                1000,
            )
        ]

        async with AsyncStoreClient("postgresql://test") as client:
            result = await client.write_bars(bars)

        assert result == 1


class TestSymbolUppercasing:
    """Test that symbols are automatically uppercased."""

    @patch("datastore.writes.psycopg.connect")
    def test_symbols_uppercased_in_upsert(self, mock_connect):
        """Symbols should be uppercased in SQL (UPPER(%s))."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        bars = [
            MockBar(
                "ibkr",
                "spy",  # lowercase
                "1min",
                datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc),
                100.0,
                101.0,
                99.0,
                100.5,
                1000,
            )
        ]

        with StoreClient("postgresql://test") as client:
            client.write_bars(bars)

        # SQL should have UPPER() function
        called_sql = mock_cursor.executemany.call_args[0][0]
        assert "UPPER" in called_sql


class TestReturnValue:
    """Test that write_bars returns correct row count."""

    @patch("datastore.writes.psycopg.connect")
    def test_returns_total_rows_written(self, mock_connect):
        """write_bars should return total number of bars written."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        bars = [
            MockBar(
                "ibkr",
                f"SYM{i}",
                "1min",
                datetime(2025, 1, 1, 9, 30 + i, tzinfo=timezone.utc),
                100.0,
                101.0,
                99.0,
                100.5,
                1000,
            )
            for i in range(15)
        ]

        with StoreClient("postgresql://test") as client:
            result = client.write_bars(bars)

        assert result == 15
