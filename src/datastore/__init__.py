"""
Datastore control-plane package.

Exports:
- config: Application settings and configuration
- writes: StoreClient and AsyncStoreClient for bars_ohlcv
- job_tracking: JobRunTracker for pipeline audit trail
"""

from .config import get_settings, Settings
from .writes import StoreClient, AsyncStoreClient, Bar, BARS_WRITTEN_TOTAL, BARS_WRITE_LATENCY
from .writes_signals import (
    SignalsStoreClient,
    AsyncSignalsStoreClient,
    Signal,
    SIGNALS_WRITTEN_TOTAL,
    SIGNALS_WRITE_LATENCY,
)
from .queries_signals import (
    SignalsQueryClient,
    AsyncSignalsQueryClient,
)
from .job_tracking import (
    JobRunTracker,
    compute_config_fingerprint,
    JOB_RUNS_TOTAL,
    JOB_RUNS_DURATION,
)

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
    # Signals writers
    "SignalsStoreClient",
    "AsyncSignalsStoreClient",
    "Signal",
    "SIGNALS_WRITTEN_TOTAL",
    "SIGNALS_WRITE_LATENCY",
    # Signals queries
    "SignalsQueryClient",
    "AsyncSignalsQueryClient",
    # Job tracking
    "JobRunTracker",
    "compute_config_fingerprint",
    "JOB_RUNS_TOTAL",
    "JOB_RUNS_DURATION",
]
