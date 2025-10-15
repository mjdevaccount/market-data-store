"""
Unit tests for BoundedQueue watermarks.
"""

import asyncio
import pytest

from market_data_store.coordinator import BoundedQueue


@pytest.mark.asyncio
async def test_watermark_signals_fire_once_and_recover():
    """Test that watermark signals fire once and recover properly."""
    high_called = 0
    low_called = 0

    async def on_high():
        nonlocal high_called
        high_called += 1

    async def on_low():
        nonlocal low_called
        low_called += 1

    q = BoundedQueue[int](
        capacity=10,
        high_watermark=8,
        low_watermark=4,
        on_high=on_high,
        on_low=on_low,
    )

    # push to high watermark
    for i in range(8):
        await q.put(i)
    assert q.size == 8
    await asyncio.sleep(0)  # allow callback
    assert high_called == 1

    # consume down below low watermark
    for _ in range(5):  # pop 5 -> size becomes 3
        await q.get()
    await asyncio.sleep(0)
    assert low_called == 1

    # push again and ensure we don't re-fire high unless crossing again
    for i in range(4):  # size goes 3->7
        await q.put(100 + i)
    assert high_called == 1  # still below high watermark

    await q.put(999)  # size=8 triggers high again
    await asyncio.sleep(0)
    assert high_called == 2


@pytest.mark.asyncio
async def test_drop_oldest_strategy():
    """Test drop_oldest overflow strategy."""
    dropped = []

    async def on_drop(item: int):
        dropped.append(item)

    q = BoundedQueue[int](
        capacity=5,
        overflow_strategy="drop_oldest",
        drop_callback=on_drop,
    )

    # Fill queue
    for i in range(5):
        await q.put(i)

    assert q.size == 5

    # Add one more - should drop oldest (0)
    await q.put(99)
    assert q.size == 5
    assert dropped == [0]

    # Verify queue has 1,2,3,4,99
    items = []
    for _ in range(5):
        items.append(await q.get())
    assert items == [1, 2, 3, 4, 99]


@pytest.mark.asyncio
async def test_error_strategy():
    """Test error overflow strategy."""
    from market_data_store.coordinator import QueueFullError

    q = BoundedQueue[int](capacity=3, overflow_strategy="error")

    # Fill queue
    for i in range(3):
        await q.put(i)

    # Next put should raise
    with pytest.raises(QueueFullError):
        await q.put(999)
