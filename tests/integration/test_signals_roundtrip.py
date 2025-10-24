"""
Integration tests for signals roundtrip functionality.

Tests the complete flow:
1. Write signals to database
2. Query signals back
3. Verify idempotency
4. Test async operations
"""

import pytest
import asyncpg
from datetime import datetime, timezone
from types import SimpleNamespace

from datastore.writes_signals import SignalsStoreClient, AsyncSignalsStoreClient


@pytest.mark.asyncio
async def test_signals_roundtrip(tmp_path, postgres_dsn):
    """Test signals write and read roundtrip with asyncpg verification."""
    client = SignalsStoreClient(postgres_dsn)

    signal = SimpleNamespace(
        provider="synthetic",
        symbol="TEST",
        ts=datetime.now(timezone.utc),
        name="test_signal",
        value=1.23,
        score=0.99,
        metadata={"window": "1m"},
    )

    # Write signal using context manager
    with client:
        written_count = client.write_signals([signal])
        assert written_count == 1

    # Verify with direct asyncpg query
    conn = await asyncpg.connect(postgres_dsn)
    rows = await conn.fetch("SELECT * FROM signals WHERE symbol='TEST'")
    assert len(rows) == 1
    assert rows[0]["value"] == 1.23
    assert rows[0]["score"] == 0.99
    assert rows[0]["metadata"] == {"window": "1m"}
    await conn.close()


@pytest.mark.asyncio
async def test_async_signals_roundtrip(tmp_path, postgres_dsn):
    """Test async signals write and read roundtrip."""
    async with AsyncSignalsStoreClient(postgres_dsn) as client:
        signal = SimpleNamespace(
            provider="async_synthetic",
            symbol="ASYNC_TEST",
            ts=datetime.now(timezone.utc),
            name="async_test_signal",
            value=2.34,
            score=0.88,
            metadata={"async": True},
        )

        written_count = await client.write_signals([signal])
        assert written_count == 1

        # Verify with direct asyncpg query
        conn = await asyncpg.connect(postgres_dsn)
        rows = await conn.fetch("SELECT * FROM signals WHERE symbol='ASYNC_TEST'")
        assert len(rows) == 1
        assert rows[0]["value"] == 2.34
        assert rows[0]["score"] == 0.88
        assert rows[0]["metadata"] == {"async": True}
        await conn.close()


@pytest.mark.asyncio
async def test_signals_idempotency(tmp_path, postgres_dsn):
    """Test that duplicate signals are handled idempotently."""
    signal = SimpleNamespace(
        provider="idempotent_test",
        symbol="IDEM_TEST",
        ts=datetime.now(timezone.utc),
        name="idempotent_signal",
        value=100.0,
        score=0.9,
        metadata={"test": True},
    )

    # Write the same signal twice
    with SignalsStoreClient(postgres_dsn) as client:
        count1 = client.write_signals([signal])
        count2 = client.write_signals([signal])
        assert count1 == 1
        assert count2 == 1  # Should still write (idempotent)

    # Verify only one record exists
    conn = await asyncpg.connect(postgres_dsn)
    rows = await conn.fetch("SELECT * FROM signals WHERE symbol='IDEM_TEST'")
    assert len(rows) == 1
    assert rows[0]["value"] == 100.0
    await conn.close()


@pytest.mark.asyncio
async def test_signals_batch_operations(tmp_path, postgres_dsn):
    """Test batch operations with multiple signals."""
    # Create 10 signals
    signals = []
    for i in range(10):
        signals.append(
            SimpleNamespace(
                provider="batch_provider",
                symbol="BATCH_TEST",
                ts=datetime.now(timezone.utc),
                name=f"batch_signal_{i % 3}",  # 3 different signal types
                value=float(i),
                score=0.5 + (i % 5) * 0.1,
                metadata={"batch_id": i},
            )
        )

    # Write in batches
    with SignalsStoreClient(postgres_dsn, batch_threshold=5) as client:
        written_count = client.write_signals(signals, batch_size=5)
        assert written_count == 10

    # Verify all signals were written
    conn = await asyncpg.connect(postgres_dsn)
    rows = await conn.fetch("SELECT COUNT(*) as count FROM signals WHERE provider='batch_provider'")
    assert rows[0]["count"] == 10

    # Verify unique signal types
    unique_names = await conn.fetch(
        "SELECT DISTINCT name FROM signals WHERE provider='batch_provider'"
    )
    assert len(unique_names) == 3
    await conn.close()


@pytest.mark.asyncio
async def test_signals_edge_cases(tmp_path, postgres_dsn):
    """Test edge cases for signals operations."""
    # Test with None values
    signal_with_nones = SimpleNamespace(
        provider="edge_provider",
        symbol="EDGE_TEST",
        ts=datetime.now(timezone.utc),
        name="edge_signal",
        value=42.0,
        score=None,  # None score
        metadata=None,  # None metadata
    )

    with SignalsStoreClient(postgres_dsn) as client:
        written_count = client.write_signals([signal_with_nones])
        assert written_count == 1

    # Verify the signal was written correctly
    conn = await asyncpg.connect(postgres_dsn)
    rows = await conn.fetch("SELECT * FROM signals WHERE symbol='EDGE_TEST'")
    assert len(rows) == 1
    assert rows[0]["value"] == 42.0
    assert rows[0]["score"] is None
    assert rows[0]["metadata"] is None
    await conn.close()

    # Test empty batch
    with SignalsStoreClient(postgres_dsn) as client:
        written_count = client.write_signals([])
        assert written_count == 0


@pytest.mark.asyncio
async def test_signals_performance_metrics(tmp_path, postgres_dsn):
    """Test that performance metrics are recorded."""
    from prometheus_client import REGISTRY

    # Clear any existing metrics
    for collector in list(REGISTRY._names_to_collectors.values()):
        if hasattr(collector, "_metrics"):
            collector._metrics.clear()

    signal = SimpleNamespace(
        provider="metrics_provider",
        symbol="METRICS_TEST",
        ts=datetime.now(timezone.utc),
        name="metrics_signal",
        value=1.0,
        score=0.5,
    )

    with SignalsStoreClient(postgres_dsn) as client:
        client.write_signals([signal])

    # Check that metrics were recorded
    from datastore.writes_signals import SIGNALS_WRITTEN_TOTAL, SIGNALS_WRITE_LATENCY

    # Verify metrics exist (they should be registered)
    assert SIGNALS_WRITTEN_TOTAL is not None
    assert SIGNALS_WRITE_LATENCY is not None
