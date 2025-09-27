"""
Utility functions for Market Data Store Client.

Includes time/size helpers, symbol normalization, and batch processing utilities.
"""

import time
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass


def generate_id() -> str:
    """Generate a UUID string for record identification."""
    return str(uuid.uuid4())


def normalize_symbol(symbol: str) -> str:
    """Normalize symbol to uppercase."""
    return symbol.upper().strip()


def normalize_timeframe(timeframe: str) -> str:
    """Normalize timeframe string."""
    return timeframe.lower().strip()


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


def parse_datetime(dt: Union[str, datetime]) -> datetime:
    """Parse datetime from string or return datetime object."""
    if isinstance(dt, str):
        return datetime.fromisoformat(dt.replace("Z", "+00:00"))
    return dt


@dataclass
class BatchConfig:
    """Configuration for batch processing."""

    max_rows: int = 1000
    max_bytes: int = 1024 * 1024  # 1MB
    max_ms: int = 5000  # 5 seconds
    retry_attempts: int = 3
    retry_delay_ms: int = 1000


class BatchWriter:
    """
    Batch writer for efficient bulk operations.

    Flushes based on row count, byte size, or time intervals.
    """

    def __init__(self, config: BatchConfig):
        self.config = config
        self.batches: Dict[str, List[Dict[str, Any]]] = {}
        self.last_flush: Dict[str, float] = {}
        self.total_bytes: Dict[str, int] = {}

    def add(self, table: str, record: Dict[str, Any]) -> None:
        """Add record to batch."""
        if table not in self.batches:
            self.batches[table] = []
            self.last_flush[table] = time.time()
            self.total_bytes[table] = 0

        self.batches[table].append(record)
        self.total_bytes[table] += self._estimate_size(record)

    def should_flush(self, table: str) -> bool:
        """Check if batch should be flushed."""
        if table not in self.batches:
            return False

        batch = self.batches[table]
        now = time.time()

        # Check row count
        if len(batch) >= self.config.max_rows:
            return True

        # Check byte size
        if self.total_bytes[table] >= self.config.max_bytes:
            return True

        # Check time interval
        if now - self.last_flush[table] >= self.config.max_ms / 1000:
            return True

        return False

    def get_batch(self, table: str) -> List[Dict[str, Any]]:
        """Get and clear batch for table."""
        if table not in self.batches:
            return []

        batch = self.batches[table]
        self.batches[table] = []
        self.last_flush[table] = time.time()
        self.total_bytes[table] = 0

        return batch

    def _estimate_size(self, record: Dict[str, Any]) -> int:
        """Estimate record size in bytes."""
        size = 0
        for key, value in record.items():
            size += len(str(key))
            if value is not None:
                size += len(str(value))
        return size


def calculate_retry_delay(
    attempt: int, base_delay_ms: int = 1000, max_delay_ms: int = 30000, jitter: bool = True
) -> float:
    """
    Calculate retry delay with exponential backoff and optional jitter.

    Args:
        attempt: Current attempt number (0-based)
        base_delay_ms: Base delay in milliseconds
        max_delay_ms: Maximum delay in milliseconds
        jitter: Add random jitter to prevent thundering herd

    Returns:
        Delay in seconds
    """
    import random

    # Exponential backoff: base_delay * 2^attempt
    delay_ms = min(base_delay_ms * (2**attempt), max_delay_ms)

    if jitter:
        # Add ±25% jitter
        jitter_range = delay_ms * 0.25
        delay_ms += random.uniform(-jitter_range, jitter_range)

    return max(0, delay_ms / 1000.0)


def format_dsn_with_tenant(dsn: str, tenant_id: str, app_name: Optional[str] = None) -> str:
    """
    Format DSN with tenant_id and optional app_name.

    Args:
        dsn: Base PostgreSQL connection string
        tenant_id: UUID string for tenant isolation
        app_name: Application name for pg_stat_activity

    Returns:
        Formatted DSN with options
    """
    options = [f"app.tenant_id={tenant_id}"]

    if app_name:
        options.append(f"application_name={app_name}")

    sep = "&" if "?" in dsn else "?"
    return f"{dsn}{sep}options=-c%20" + "%20".join(options)
