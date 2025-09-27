"""
Market Data Store Client Library

A production-ready Python library for Market Data Core to consume market data
with TimescaleDB, RLS, and tenant isolation.

Usage:
    from mds_client import MDS, AMDS, Bar, Fundamentals, News, OptionSnap

    # Sync client
    mds = MDS({"dsn": "postgresql://...", "tenant_id": "uuid"})
    mds.upsert_bars([Bar(...)])

    # Async client
    amds = AMDS({"dsn": "postgresql://...", "tenant_id": "uuid"})
    await amds.upsert_bars([Bar(...)])
"""

from .client import MDS, MDSConfig
from .aclient import AMDS
from .batch import BatchProcessor, BatchConfig
from .abatch import AsyncBatchProcessor
from .models import Bar, Fundamentals, News, OptionSnap, LatestPrice

__version__ = "1.0.0"
__all__ = [
    "MDS",
    "AMDS",
    "MDSConfig",
    "BatchProcessor",
    "AsyncBatchProcessor",
    "BatchConfig",
    "Bar",
    "Fundamentals",
    "News",
    "OptionSnap",
    "LatestPrice",
]
