"""
Datastore control-plane package.

Exports:
- config: Application settings and configuration
- writes: StoreClient and AsyncStoreClient for bars_ohlcv
- job_tracking: JobRunTracker for pipeline audit trail
"""

from .config import get_settings, Settings
from .writes import StoreClient, AsyncStoreClient, Bar, BARS_WRITTEN_TOTAL, BARS_WRITE_LATENCY
from .job_tracking import JobRunTracker, compute_config_fingerprint

__all__ = [
    # Config
    "get_settings",
    "Settings",
    # Writers
    "StoreClient",
    "AsyncStoreClient",
    "Bar",
    "BARS_WRITTEN_TOTAL",
    "BARS_WRITE_LATENCY",
    # Job tracking
    "JobRunTracker",
    "compute_config_fingerprint",
]
