"""
StoreClient - Lightweight, idempotent writer for bars_ohlcv.

Distinct from mds_client (which handles tenant-based RLS system).
This is for provider-based, config-driven pipeline ingestion.

Features:
- Diff-aware upserts (only update if values changed)
- Smart batching (COPY for 1000+, executemany otherwise)
- Prometheus metrics (store_bars_written_total, store_bars_write_latency_seconds)
- Protocol-based Bar interface (duck typing)
- Parallel sync/async APIs
"""

from typing import Iterable, Protocol, runtime_checkable, List
from datetime import datetime
import time
import psycopg
from loguru import logger
from prometheus_client import Counter, Histogram

# Prometheus metrics (auto-registered with global REGISTRY)
BARS_WRITTEN_TOTAL = Counter(
    "store_bars_written_total",
    "Total bars written to bars_ohlcv",
    ["method", "status"],
)
BARS_WRITE_LATENCY = Histogram(
    "store_bars_write_latency_seconds",
    "Latency of bars_ohlcv writes",
    ["method"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


@runtime_checkable
class Bar(Protocol):
    """Protocol for Bar objects from market_data_core (duck typing)."""

    provider: str
    symbol: str
    interval: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class StoreClient:
    """
    Sync writer for bars_ohlcv with diff-aware upserts.

    Usage:
        with StoreClient(uri) as client:
            client.write_bars(bars)
    """

    def __init__(self, uri: str, batch_threshold: int = 1000):
        """
        Initialize StoreClient.

        Args:
            uri: PostgreSQL connection URI
            batch_threshold: Batch size threshold for COPY vs executemany (default 1000)
        """
        self._uri = uri
        self._batch_threshold = batch_threshold
        self._conn = None

    def __enter__(self):
        """Context manager entry - establish connection."""
        self._conn = psycopg.connect(self._uri)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close connection."""
        if self._conn:
            self._conn.close()
        return False

    def write_bars(self, bars: Iterable[Bar], batch_size: int = 1000) -> int:
        """
        Write bars with automatic batching and method selection.

        Args:
            bars: Iterable of Bar objects (protocol-based, duck typing)
            batch_size: Size of batches to accumulate before flushing

        Returns:
            Total number of bars written

        Raises:
            RuntimeError: If not used as context manager
            psycopg.Error: On database errors
        """
        if not self._conn:
            raise RuntimeError("StoreClient must be used as context manager")

        total = 0
        batch: List[Bar] = []

        for bar in bars:
            batch.append(bar)
            if len(batch) >= batch_size:
                total += self._flush_batch(batch)
                batch.clear()

        if batch:
            total += self._flush_batch(batch)

        self._conn.commit()
        return total

    def _flush_batch(self, batch: List[Bar]) -> int:
        """
        Flush batch using optimal method (executemany vs COPY).

        Uses COPY when len(batch) >= batch_threshold for efficiency.
        Records Prometheus metrics for observability.
        """
        method = "COPY" if len(batch) >= self._batch_threshold else "UPSERT"
        start = time.perf_counter()

        try:
            with self._conn.cursor() as cur:
                if method == "COPY":
                    self._write_copy(cur, batch)
                else:
                    self._write_upsert(cur, batch)

            duration = time.perf_counter() - start
            BARS_WRITTEN_TOTAL.labels(method=method, status="success").inc(len(batch))
            BARS_WRITE_LATENCY.labels(method=method).observe(duration)
            logger.debug(f"Wrote {len(batch)} bars via {method} in {duration:.3f}s")
            return len(batch)

        except Exception as e:
            duration = time.perf_counter() - start
            BARS_WRITTEN_TOTAL.labels(method=method, status="failure").inc(len(batch))
            BARS_WRITE_LATENCY.labels(method=method).observe(duration)
            logger.error(f"Failed to write {len(batch)} bars via {method}: {e}")
            raise

    def _write_upsert(self, cur, batch: List[Bar]) -> None:
        """
        Executemany with diff-aware upsert (only update if values changed).

        Uses IS DISTINCT FROM to skip updates when values are identical,
        making replays truly idempotent and efficient.
        """
        sql = """
            INSERT INTO bars_ohlcv (provider, symbol, interval, ts, open, high, low, close, volume)
            VALUES (%s, UPPER(%s), %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (provider, symbol, interval, ts)
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume
            WHERE
                bars_ohlcv.open IS DISTINCT FROM EXCLUDED.open OR
                bars_ohlcv.high IS DISTINCT FROM EXCLUDED.high OR
                bars_ohlcv.low IS DISTINCT FROM EXCLUDED.low OR
                bars_ohlcv.close IS DISTINCT FROM EXCLUDED.close OR
                bars_ohlcv.volume IS DISTINCT FROM EXCLUDED.volume
        """

        data = [
            (
                b.provider,
                b.symbol,
                b.interval,
                b.ts,
                b.open,
                b.high,
                b.low,
                b.close,
                b.volume,
            )
            for b in batch
        ]
        cur.executemany(sql, data)

    def _write_copy(self, cur, batch: List[Bar]) -> None:
        """
        COPY via temp table for high-volume inserts (1000+ rows).

        Steps:
        1. CREATE TEMP TABLE with same schema as bars_ohlcv
        2. COPY data into temp table (fastest bulk load)
        3. INSERT ... ON CONFLICT with diff-aware update
        4. Temp table auto-drops on commit
        """
        # Create temp table matching bars_ohlcv schema
        cur.execute(
            """
            CREATE TEMP TABLE tmp_bars_copy (
                LIKE bars_ohlcv INCLUDING DEFAULTS
            ) ON COMMIT DROP
        """
        )

        # COPY into temp table (binary protocol, fast)
        cols = ["provider", "symbol", "interval", "ts", "open", "high", "low", "close", "volume"]
        with cur.copy(f"COPY tmp_bars_copy ({','.join(cols)}) FROM STDIN") as copy:
            for b in batch:
                copy.write_row(
                    (
                        b.provider,
                        b.symbol.upper(),
                        b.interval,
                        b.ts,
                        b.open,
                        b.high,
                        b.low,
                        b.close,
                        b.volume,
                    )
                )

        # Upsert from temp with diff check
        cur.execute(
            """
            INSERT INTO bars_ohlcv (provider, symbol, interval, ts, open, high, low, close, volume)
            SELECT provider, symbol, interval, ts, open, high, low, close, volume
            FROM tmp_bars_copy
            ON CONFLICT (provider, symbol, interval, ts)
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume
            WHERE
                bars_ohlcv.open IS DISTINCT FROM EXCLUDED.open OR
                bars_ohlcv.high IS DISTINCT FROM EXCLUDED.high OR
                bars_ohlcv.low IS DISTINCT FROM EXCLUDED.low OR
                bars_ohlcv.close IS DISTINCT FROM EXCLUDED.close OR
                bars_ohlcv.volume IS DISTINCT FROM EXCLUDED.volume
        """
        )


class AsyncStoreClient:
    """
    Async writer for bars_ohlcv (parallel API to sync version).

    Usage:
        async with AsyncStoreClient(uri) as client:
            await client.write_bars(bars)
    """

    def __init__(self, uri: str, batch_threshold: int = 1000):
        """
        Initialize AsyncStoreClient.

        Args:
            uri: PostgreSQL connection URI
            batch_threshold: Batch size threshold for COPY vs executemany (default 1000)
        """
        self._uri = uri
        self._batch_threshold = batch_threshold
        self._conn = None

    async def __aenter__(self):
        """Async context manager entry - establish connection."""
        self._conn = await psycopg.AsyncConnection.connect(self._uri)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close connection."""
        if self._conn:
            await self._conn.close()
        return False

    async def write_bars(self, bars: Iterable[Bar], batch_size: int = 1000) -> int:
        """
        Async write bars with automatic batching.

        Args:
            bars: Iterable of Bar objects (protocol-based, duck typing)
            batch_size: Size of batches to accumulate before flushing

        Returns:
            Total number of bars written

        Raises:
            RuntimeError: If not used as context manager
            psycopg.Error: On database errors
        """
        if not self._conn:
            raise RuntimeError("AsyncStoreClient must be used as context manager")

        total = 0
        batch: List[Bar] = []

        for bar in bars:
            batch.append(bar)
            if len(batch) >= batch_size:
                total += await self._flush_batch(batch)
                batch.clear()

        if batch:
            total += await self._flush_batch(batch)

        await self._conn.commit()
        return total

    async def _flush_batch(self, batch: List[Bar]) -> int:
        """Async flush batch using optimal method."""
        method = "COPY" if len(batch) >= self._batch_threshold else "UPSERT"
        start = time.perf_counter()

        try:
            async with self._conn.cursor() as cur:
                if method == "COPY":
                    await self._write_copy(cur, batch)
                else:
                    await self._write_upsert(cur, batch)

            duration = time.perf_counter() - start
            BARS_WRITTEN_TOTAL.labels(method=method, status="success").inc(len(batch))
            BARS_WRITE_LATENCY.labels(method=method).observe(duration)
            logger.debug(f"Wrote {len(batch)} bars via {method} in {duration:.3f}s")
            return len(batch)

        except Exception as e:
            duration = time.perf_counter() - start
            BARS_WRITTEN_TOTAL.labels(method=method, status="failure").inc(len(batch))
            BARS_WRITE_LATENCY.labels(method=method).observe(duration)
            logger.error(f"Failed to write {len(batch)} bars via {method}: {e}")
            raise

    async def _write_upsert(self, cur, batch: List[Bar]) -> None:
        """Async executemany with diff-aware upsert."""
        sql = """
            INSERT INTO bars_ohlcv (provider, symbol, interval, ts, open, high, low, close, volume)
            VALUES (%s, UPPER(%s), %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (provider, symbol, interval, ts)
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume
            WHERE
                bars_ohlcv.open IS DISTINCT FROM EXCLUDED.open OR
                bars_ohlcv.high IS DISTINCT FROM EXCLUDED.high OR
                bars_ohlcv.low IS DISTINCT FROM EXCLUDED.low OR
                bars_ohlcv.close IS DISTINCT FROM EXCLUDED.close OR
                bars_ohlcv.volume IS DISTINCT FROM EXCLUDED.volume
        """

        data = [
            (
                b.provider,
                b.symbol,
                b.interval,
                b.ts,
                b.open,
                b.high,
                b.low,
                b.close,
                b.volume,
            )
            for b in batch
        ]
        await cur.executemany(sql, data)

    async def _write_copy(self, cur, batch: List[Bar]) -> None:
        """Async COPY via temp table for high-volume inserts."""
        # Create temp table
        await cur.execute(
            """
            CREATE TEMP TABLE tmp_bars_copy (
                LIKE bars_ohlcv INCLUDING DEFAULTS
            ) ON COMMIT DROP
        """
        )

        # COPY into temp
        cols = ["provider", "symbol", "interval", "ts", "open", "high", "low", "close", "volume"]
        async with cur.copy(f"COPY tmp_bars_copy ({','.join(cols)}) FROM STDIN") as copy:
            for b in batch:
                await copy.write_row(
                    (
                        b.provider,
                        b.symbol.upper(),
                        b.interval,
                        b.ts,
                        b.open,
                        b.high,
                        b.low,
                        b.close,
                        b.volume,
                    )
                )

        # Upsert from temp with diff check
        await cur.execute(
            """
            INSERT INTO bars_ohlcv (provider, symbol, interval, ts, open, high, low, close, volume)
            SELECT provider, symbol, interval, ts, open, high, low, close, volume
            FROM tmp_bars_copy
            ON CONFLICT (provider, symbol, interval, ts)
            DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume
            WHERE
                bars_ohlcv.open IS DISTINCT FROM EXCLUDED.open OR
                bars_ohlcv.high IS DISTINCT FROM EXCLUDED.high OR
                bars_ohlcv.low IS DISTINCT FROM EXCLUDED.low OR
                bars_ohlcv.close IS DISTINCT FROM EXCLUDED.close OR
                bars_ohlcv.volume IS DISTINCT FROM EXCLUDED.volume
        """
        )
