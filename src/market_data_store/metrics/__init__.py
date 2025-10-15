"""
Metrics module for market_data_store.

Ensures sink metrics are registered with the global Prometheus registry.
"""

# Import to trigger metric registration
from market_data_store.sinks.base import SINK_WRITES_TOTAL, SINK_WRITE_LATENCY

__all__ = ["SINK_WRITES_TOTAL", "SINK_WRITE_LATENCY"]
