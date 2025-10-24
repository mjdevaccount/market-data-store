"""
SignalsStoreClient - Idempotent writer for streaming inference signals.

Features:
- Idempotent upserts (only update if values changed)
- Smart batching (COPY for 1000+, executemany otherwise)
- Prometheus metrics (signals_written_total, signals_write_latency_seconds)
- Protocol-based Signal interface (duck typing)
- Parallel sync/async APIs
"""

from typing import Iterable, Protocol, runtime_checkable, List
from datetime import datetime
import time
import psycopg
from loguru import logger
from prometheus_client import Counter, Histogram

# Prometheus metrics (auto-registered with global REGISTRY)
SIGNALS_WRITTEN_TOTAL = Counter(
    "store_signals_written_total",
    "Total signals written to signals table",
    ["method", "status"],
)
SIGNALS_WRITE_LATENCY = Histogram(
    "store_signals_write_latency_seconds",
    "Latency of signals table writes",
    ["method"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


@runtime_checkable
class Signal(Protocol):
    """Protocol for Signal objects from market_data_core (duck typing)."""

    provider: str
    symbol: str
    ts: datetime
    name: str
    value: float
    score: float | None
    metadata: dict | None


class SignalsStoreClient:
    """
    Sync writer for signals with idempotent upserts.

    Usage:
        with SignalsStoreClient(uri) as client:
            client.write_signals(signals)
    """

    def __init__(self, uri: str, batch_threshold: int = 1000):
        """
        Initialize SignalsStoreClient.

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

    def write_signals(self, signals: Iterable[Signal], batch_size: int = 1000) -> int:
        """
        Write signals with automatic batching and method selection.

        Args:
            signals: Iterable of Signal objects (protocol-based, duck typing)
            batch_size: Size of batches to accumulate before flushing

        Returns:
            Total number of signals written

        Raises:
            RuntimeError: If not used as context manager
            psycopg.Error: On database errors
        """
        if not self._conn:
            raise RuntimeError("SignalsStoreClient must be used as context manager")

        total = 0
        batch: List[Signal] = []

        for signal in signals:
            batch.append(signal)
            if len(batch) >= batch_size:
                total += self._flush_batch(batch)
                batch.clear()

        if batch:
            total += self._flush_batch(batch)

        self._conn.commit()
        return total

    def _flush_batch(self, batch: List[Signal]) -> int:
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
            SIGNALS_WRITTEN_TOTAL.labels(method=method, status="success").inc(len(batch))
            SIGNALS_WRITE_LATENCY.labels(method=method).observe(duration)
            logger.debug(f"Wrote {len(batch)} signals via {method} in {duration:.3f}s")
            return len(batch)

        except Exception as e:
            duration = time.perf_counter() - start
            SIGNALS_WRITTEN_TOTAL.labels(method=method, status="failure").inc(len(batch))
            SIGNALS_WRITE_LATENCY.labels(method=method).observe(duration)
            logger.error(f"Failed to write {len(batch)} signals via {method}: {e}")
            raise

    def _write_upsert(self, cur, batch: List[Signal]) -> None:
        """
        Executemany with diff-aware upsert (only update if values changed).

        Uses IS DISTINCT FROM to skip updates when values are identical,
        making replays truly idempotent and efficient.
        """
        sql = """
            INSERT INTO signals (provider, symbol, ts, name, value, score, metadata)
            VALUES (%s, UPPER(%s), %s, %s, %s, %s, %s)
            ON CONFLICT (provider, symbol, ts, name)
            DO UPDATE SET
                value = EXCLUDED.value,
                score = EXCLUDED.score,
                metadata = EXCLUDED.metadata
            WHERE
                signals.value IS DISTINCT FROM EXCLUDED.value OR
                signals.score IS DISTINCT FROM EXCLUDED.score OR
                signals.metadata IS DISTINCT FROM EXCLUDED.metadata
        """

        data = [
            (
                s.provider,
                s.symbol,
                s.ts,
                s.name,
                s.value,
                s.score,
                s.metadata,
            )
            for s in batch
        ]
        cur.executemany(sql, data)

    def _write_copy(self, cur, batch: List[Signal]) -> None:
        """
        COPY via temp table for high-volume inserts (1000+ rows).

        Steps:
        1. CREATE TEMP TABLE with same schema as signals
        2. COPY data into temp table (fastest bulk load)
        3. INSERT ... ON CONFLICT with diff-aware update
        4. Temp table auto-drops on commit
        """
        # Create temp table matching signals schema
        cur.execute(
            """
            CREATE TEMP TABLE tmp_signals_copy (
                LIKE signals INCLUDING DEFAULTS
            ) ON COMMIT DROP
        """
        )

        # COPY into temp table (binary protocol, fast)
        cols = ["provider", "symbol", "ts", "name", "value", "score", "metadata"]
        with cur.copy(f"COPY tmp_signals_copy ({','.join(cols)}) FROM STDIN") as copy:
            for s in batch:
                copy.write_row(
                    (
                        s.provider,
                        s.symbol.upper(),
                        s.ts,
                        s.name,
                        s.value,
                        s.score,
                        s.metadata,
                    )
                )

        # Upsert from temp with diff check
        cur.execute(
            """
            INSERT INTO signals (provider, symbol, ts, name, value, score, metadata)
            SELECT provider, symbol, ts, name, value, score, metadata
            FROM tmp_signals_copy
            ON CONFLICT (provider, symbol, ts, name)
            DO UPDATE SET
                value = EXCLUDED.value,
                score = EXCLUDED.score,
                metadata = EXCLUDED.metadata
            WHERE
                signals.value IS DISTINCT FROM EXCLUDED.value OR
                signals.score IS DISTINCT FROM EXCLUDED.score OR
                signals.metadata IS DISTINCT FROM EXCLUDED.metadata
        """
        )


class AsyncSignalsStoreClient:
    """
    Async writer for signals (parallel API to sync version).

    Usage:
        async with AsyncSignalsStoreClient(uri) as client:
            await client.write_signals(signals)
    """

    def __init__(self, uri: str, batch_threshold: int = 1000):
        """
        Initialize AsyncSignalsStoreClient.

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

    async def write_signals(self, signals: Iterable[Signal], batch_size: int = 1000) -> int:
        """
        Async write signals with automatic batching.

        Args:
            signals: Iterable of Signal objects (protocol-based, duck typing)
            batch_size: Size of batches to accumulate before flushing

        Returns:
            Total number of signals written

        Raises:
            RuntimeError: If not used as context manager
            psycopg.Error: On database errors
        """
        if not self._conn:
            raise RuntimeError("AsyncSignalsStoreClient must be used as context manager")

        total = 0
        batch: List[Signal] = []

        for signal in signals:
            batch.append(signal)
            if len(batch) >= batch_size:
                total += await self._flush_batch(batch)
                batch.clear()

        if batch:
            total += await self._flush_batch(batch)

        await self._conn.commit()
        return total

    async def _flush_batch(self, batch: List[Signal]) -> int:
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
            SIGNALS_WRITTEN_TOTAL.labels(method=method, status="success").inc(len(batch))
            SIGNALS_WRITE_LATENCY.labels(method=method).observe(duration)
            logger.debug(f"Wrote {len(batch)} signals via {method} in {duration:.3f}s")
            return len(batch)

        except Exception as e:
            duration = time.perf_counter() - start
            SIGNALS_WRITTEN_TOTAL.labels(method=method, status="failure").inc(len(batch))
            SIGNALS_WRITE_LATENCY.labels(method=method).observe(duration)
            logger.error(f"Failed to write {len(batch)} signals via {method}: {e}")
            raise

    async def _write_upsert(self, cur, batch: List[Signal]) -> None:
        """Async executemany with diff-aware upsert."""
        sql = """
            INSERT INTO signals (provider, symbol, ts, name, value, score, metadata)
            VALUES (%s, UPPER(%s), %s, %s, %s, %s, %s)
            ON CONFLICT (provider, symbol, ts, name)
            DO UPDATE SET
                value = EXCLUDED.value,
                score = EXCLUDED.score,
                metadata = EXCLUDED.metadata
            WHERE
                signals.value IS DISTINCT FROM EXCLUDED.value OR
                signals.score IS DISTINCT FROM EXCLUDED.score OR
                signals.metadata IS DISTINCT FROM EXCLUDED.metadata
        """

        data = [
            (
                s.provider,
                s.symbol,
                s.ts,
                s.name,
                s.value,
                s.score,
                s.metadata,
            )
            for s in batch
        ]
        await cur.executemany(sql, data)

    async def _write_copy(self, cur, batch: List[Signal]) -> None:
        """Async COPY via temp table for high-volume inserts."""
        # Create temp table
        await cur.execute(
            """
            CREATE TEMP TABLE tmp_signals_copy (
                LIKE signals INCLUDING DEFAULTS
            ) ON COMMIT DROP
        """
        )

        # COPY into temp
        cols = ["provider", "symbol", "ts", "name", "value", "score", "metadata"]
        async with cur.copy(f"COPY tmp_signals_copy ({','.join(cols)}) FROM STDIN") as copy:
            for s in batch:
                await copy.write_row(
                    (
                        s.provider,
                        s.symbol.upper(),
                        s.ts,
                        s.name,
                        s.value,
                        s.score,
                        s.metadata,
                    )
                )

        # Upsert from temp with diff check
        await cur.execute(
            """
            INSERT INTO signals (provider, symbol, ts, name, value, score, metadata)
            SELECT provider, symbol, ts, name, value, score, metadata
            FROM tmp_signals_copy
            ON CONFLICT (provider, symbol, ts, name)
            DO UPDATE SET
                value = EXCLUDED.value,
                score = EXCLUDED.score,
                metadata = EXCLUDED.metadata
            WHERE
                signals.value IS DISTINCT FROM EXCLUDED.value OR
                signals.score IS DISTINCT FROM EXCLUDED.score OR
                signals.metadata IS DISTINCT FROM EXCLUDED.metadata
        """
        )
