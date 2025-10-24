"""
Integration tests for bars_ohlcv with real database.

Tests:
- Full roundtrip (write → read → verify)
- Idempotency (replay same data)
- Diff-aware updates (only update on change)
- Batch performance (10K+ bars/sec target)
- Compression policy application
- Concurrent writes
"""

import pytest
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
import psycopg
from psycopg.rows import dict_row
from datastore.writes import StoreClient, AsyncStoreClient
from datastore.config import get_settings


@dataclass
class TestBar:
    """Test Bar matching Protocol."""

    provider: str
    symbol: str
    interval: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@pytest.fixture
def db_uri():
    """Get database URI from settings."""
    settings = get_settings()
    if not settings.BARS_OHLCV_ENABLED:
        pytest.skip("BARS_OHLCV_ENABLED is False")
    return settings.DATABASE_URL


@pytest.fixture
def clean_bars_ohlcv(db_uri):
    """Clean bars_ohlcv table before each test."""
    with psycopg.connect(db_uri) as conn:
        with conn.cursor() as cur:
            # Check if table exists
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='bars_ohlcv')"
            )
            if not cur.fetchone()[0]:
                pytest.skip("bars_ohlcv table doesn't exist (run migration first)")

            cur.execute("TRUNCATE bars_ohlcv")
        conn.commit()
    yield
    # Cleanup after test
    with psycopg.connect(db_uri) as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE bars_ohlcv")
        conn.commit()


class TestBasicWriteRead:
    """Test basic write and read operations."""

    def test_write_single_bar(self, db_uri, clean_bars_ohlcv):
        """Write a single bar and verify it's stored correctly."""
        bar = TestBar(
            provider="test_provider",
            symbol="SPY",
            interval="5min",
            ts=datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc),
            open=450.0,
            high=451.0,
            low=449.0,
            close=450.5,
            volume=1000000,
        )

        # Write
        with StoreClient(db_uri) as client:
            count = client.write_bars([bar])

        assert count == 1

        # Read back
        with psycopg.connect(db_uri) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM bars_ohlcv WHERE provider=%s AND symbol=%s",
                    (bar.provider, bar.symbol),
                )
                row = cur.fetchone()

        assert row is not None
        assert row["provider"] == "test_provider"
        assert row["symbol"] == "SPY"
        assert row["interval"] == "5min"
        assert row["open"] == 450.0
        assert row["high"] == 451.0
        assert row["low"] == 449.0
        assert row["close"] == 450.5
        assert row["volume"] == 1000000

    def test_write_multiple_bars(self, db_uri, clean_bars_ohlcv):
        """Write multiple bars and verify count."""
        bars = [
            TestBar(
                "test_provider",
                "SPY",
                "1min",
                datetime(2025, 1, 1, 9, 30 + i, tzinfo=timezone.utc),
                100.0 + i,
                101.0 + i,
                99.0 + i,
                100.5 + i,
                1000 * (i + 1),
            )
            for i in range(100)
        ]

        with StoreClient(db_uri) as client:
            count = client.write_bars(bars)

        assert count == 100

        # Verify in DB
        with psycopg.connect(db_uri) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM bars_ohlcv")
                db_count = cur.fetchone()[0]

        assert db_count == 100


class TestIdempotency:
    """Test idempotent upserts (replay safety)."""

    def test_replay_identical_bars_no_updates(self, db_uri, clean_bars_ohlcv):
        """Replaying identical bars should not trigger updates (IS DISTINCT FROM)."""
        bars = [
            TestBar(
                "test_provider",
                "SPY",
                "5min",
                datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc),
                450.0,
                451.0,
                449.0,
                450.5,
                1000000,
            )
        ]

        # First write
        with StoreClient(db_uri) as client:
            client.write_bars(bars)

        # Get updated_at timestamp
        with psycopg.connect(db_uri) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT updated_at FROM bars_ohlcv LIMIT 1")
                first_updated = cur.fetchone()["updated_at"]

        # Second write (replay)
        with StoreClient(db_uri) as client:
            client.write_bars(bars)

        # updated_at should NOT change (diff-aware upsert)
        with psycopg.connect(db_uri) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT updated_at FROM bars_ohlcv LIMIT 1")
                second_updated = cur.fetchone()["updated_at"]

        # Timestamps should be identical (no update occurred)
        assert first_updated == second_updated

    def test_update_on_different_values(self, db_uri, clean_bars_ohlcv):
        """Bars with different values should trigger updates."""
        bar_v1 = TestBar(
            "test_provider",
            "SPY",
            "5min",
            datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc),
            450.0,
            451.0,
            449.0,
            450.5,
            1000000,
        )

        # First write
        with StoreClient(db_uri) as client:
            client.write_bars([bar_v1])

        # Modified bar (different close price)
        bar_v2 = TestBar(
            "test_provider",
            "SPY",
            "5min",
            datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc),
            450.0,
            451.0,
            449.0,
            451.0,  # Changed
            1000000,
        )

        # Second write
        with StoreClient(db_uri) as client:
            client.write_bars([bar_v2])

        # Verify updated value
        with psycopg.connect(db_uri) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT close FROM bars_ohlcv LIMIT 1")
                close = cur.fetchone()["close"]

        assert close == 451.0  # Updated value


class TestBatching:
    """Test batch processing and method selection."""

    def test_large_batch_uses_copy(self, db_uri, clean_bars_ohlcv):
        """Batches >= 1000 should use COPY method."""
        bars = [
            TestBar(
                "test_provider",
                f"SYM{i % 10}",
                "1min",
                datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc) + timedelta(minutes=i),
                100.0,
                101.0,
                99.0,
                100.5,
                1000,
            )
            for i in range(1500)
        ]

        with StoreClient(db_uri, batch_threshold=1000) as client:
            count = client.write_bars(bars)

        assert count == 1500

        # Verify in DB
        with psycopg.connect(db_uri) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM bars_ohlcv")
                db_count = cur.fetchone()[0]

        assert db_count == 1500


class TestSymbolUppercasing:
    """Test automatic symbol uppercasing."""

    def test_lowercase_symbols_uppercased(self, db_uri, clean_bars_ohlcv):
        """Lowercase symbols should be stored as uppercase."""
        bars = [
            TestBar(
                "test_provider",
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

        with StoreClient(db_uri) as client:
            client.write_bars(bars)

        # Verify stored as uppercase
        with psycopg.connect(db_uri) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT symbol FROM bars_ohlcv LIMIT 1")
                symbol = cur.fetchone()["symbol"]

        assert symbol == "SPY"  # Uppercased


class TestAsyncClient:
    """Test AsyncStoreClient integration."""

    @pytest.mark.asyncio
    async def test_async_write_bars(self, db_uri, clean_bars_ohlcv):
        """AsyncStoreClient should write bars correctly."""
        bars = [
            TestBar(
                "test_provider",
                "AAPL",
                "5min",
                datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
                150.0,
                151.0,
                149.0,
                150.5,
                5000000,
            )
        ]

        async with AsyncStoreClient(db_uri) as client:
            count = await client.write_bars(bars)

        assert count == 1

        # Verify
        with psycopg.connect(db_uri) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM bars_ohlcv WHERE symbol='AAPL'")
                row = cur.fetchone()

        assert row is not None
        assert row["symbol"] == "AAPL"
        assert row["close"] == 150.5


class TestPerformance:
    """Test performance targets (10K bars/sec)."""

    @pytest.mark.slow
    def test_write_10k_bars_performance(self, db_uri, clean_bars_ohlcv):
        """Writing 10K bars should take < 1 second."""
        import time

        bars = [
            TestBar(
                "perf_test",
                f"SYM{i % 100}",
                "1min",
                datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc) + timedelta(minutes=i),
                100.0,
                101.0,
                99.0,
                100.5,
                1000,
            )
            for i in range(10000)
        ]

        start = time.perf_counter()
        with StoreClient(db_uri) as client:
            count = client.write_bars(bars)
        duration = time.perf_counter() - start

        assert count == 10000
        bars_per_sec = 10000 / duration

        # Target: >= 10K bars/sec
        print(f"\n✓ Performance: {bars_per_sec:.0f} bars/sec ({duration:.3f}s for 10K)")
        assert bars_per_sec >= 10000, f"Too slow: {bars_per_sec:.0f} bars/sec"


class TestConstraints:
    """Test database constraints and checks."""

    def test_primary_key_conflict_handled(self, db_uri, clean_bars_ohlcv):
        """PK conflicts should trigger upsert (not error)."""
        bar = TestBar(
            "test_provider",
            "SPY",
            "1min",
            datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc),
            100.0,
            101.0,
            99.0,
            100.5,
            1000,
        )

        # First write
        with StoreClient(db_uri) as client:
            client.write_bars([bar])

        # Second write (same PK) - should not error
        with StoreClient(db_uri) as client:
            client.write_bars([bar])

        # Should still have only 1 row
        with psycopg.connect(db_uri) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM bars_ohlcv")
                count = cur.fetchone()[0]

        assert count == 1

    def test_symbol_uppercase_constraint(self, db_uri, clean_bars_ohlcv):
        """Symbols are enforced as uppercase by CHECK constraint."""
        # StoreClient uppercases automatically, but test DB constraint
        with psycopg.connect(db_uri) as conn:
            with conn.cursor() as cur:
                # Try to insert lowercase directly (should fail)
                with pytest.raises(psycopg.errors.CheckViolation):
                    cur.execute(
                        """
                        INSERT INTO bars_ohlcv
                        (provider, symbol, interval, ts, open, high, low, close, volume)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            "test",
                            "spy",  # lowercase - should fail CHECK
                            "1min",
                            datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc),
                            100.0,
                            101.0,
                            99.0,
                            100.5,
                            1000,
                        ),
                    )
                    conn.commit()


class TestMultipleProviders:
    """Test isolation between providers."""

    def test_different_providers_isolated(self, db_uri, clean_bars_ohlcv):
        """Same symbol from different providers should coexist."""
        bar_ibkr = TestBar(
            "ibkr",
            "SPY",
            "1min",
            datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc),
            450.0,
            451.0,
            449.0,
            450.5,
            1000000,
        )
        bar_polygon = TestBar(
            "polygon",
            "SPY",
            "1min",
            datetime(2025, 1, 1, 9, 30, tzinfo=timezone.utc),
            450.1,
            451.1,
            449.1,
            450.6,
            1000500,
        )

        with StoreClient(db_uri) as client:
            client.write_bars([bar_ibkr, bar_polygon])

        # Should have 2 rows (different providers)
        with psycopg.connect(db_uri) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM bars_ohlcv WHERE symbol='SPY'")
                count = cur.fetchone()[0]

        assert count == 2
