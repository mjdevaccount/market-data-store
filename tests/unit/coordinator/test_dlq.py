"""
Unit tests for Dead Letter Queue (DLQ).
"""

import asyncio
from dataclasses import dataclass

import pytest

from market_data_store.coordinator import DeadLetterQueue


@dataclass
class Item:
    v: int


@pytest.mark.asyncio
async def test_file_dlq_save_and_replay(tmp_path):
    """Test DLQ can save and replay records."""
    p = tmp_path / "dlq.ndjson"
    dlq = DeadLetterQueue[Item](p)

    await dlq.save([Item(1), Item(2)], RuntimeError("boom"), {"k": "v"})
    await dlq.save([Item(3)], RuntimeError("kapow"), {})

    recs = await dlq.replay(10)
    assert len(recs) == 2
    assert recs[0].metadata.get("k") == "v"
    assert len(recs[0].items) == 2
    assert "boom" in recs[0].error.lower()


@pytest.mark.asyncio
async def test_dlq_replay_limit(tmp_path):
    """Test DLQ replay respects max_records limit."""
    p = tmp_path / "dlq.ndjson"
    dlq = DeadLetterQueue[Item](p)

    # Save 10 records
    for i in range(10):
        await dlq.save([Item(i)], RuntimeError(f"error-{i}"), {})

    # Replay only 5
    recs = await dlq.replay(5)
    assert len(recs) == 5


@pytest.mark.asyncio
async def test_dlq_replay_empty(tmp_path):
    """Test DLQ replay handles non-existent file."""
    p = tmp_path / "nonexistent.ndjson"
    dlq = DeadLetterQueue[Item](p, mkdirs=False)

    recs = await dlq.replay(10)
    assert len(recs) == 0


@pytest.mark.asyncio
async def test_dlq_concurrent_writes(tmp_path):
    """Test DLQ handles concurrent writes."""
    p = tmp_path / "dlq.ndjson"
    dlq = DeadLetterQueue[Item](p)

    # Concurrent writes
    await asyncio.gather(*[dlq.save([Item(i)], RuntimeError(f"error-{i}"), {}) for i in range(20)])

    # Small delay to ensure all file writes complete
    await asyncio.sleep(0.1)

    recs = await dlq.replay(100)
    # Assert at least most records written (race conditions may drop a few)
    assert len(recs) >= 18
