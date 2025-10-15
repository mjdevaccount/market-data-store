"""
Ensures sink metrics are visible in Prometheus global REGISTRY.
Simply import this module at app startup.
"""

from market_data_store.sinks import SINK_WRITES_TOTAL, SINK_WRITE_LATENCY  # noqa: F401
