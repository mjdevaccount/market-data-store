"""
Ensures sink and pulse metrics are visible in Prometheus global REGISTRY.
Simply import this module at app startup.
"""

from prometheus_client import Counter, Histogram

from market_data_store.sinks import SINK_WRITES_TOTAL, SINK_WRITE_LATENCY  # noqa: F401


# --- Pulse Metrics ---

PULSE_PUBLISH_TOTAL = Counter(
    "pulse_publish_total",
    "Total number of Pulse events published",
    ["stream", "track", "outcome"],
)

PULSE_PUBLISH_LATENCY_MS = Histogram(
    "pulse_publish_latency_ms",
    "Pulse publish latency in milliseconds",
    ["stream", "track"],
    buckets=[1, 2.5, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000],
)


class MetricsRegistry:
    """Centralized metrics registry for Store components.

    Provides access to all Store metrics in a structured way.
    Used by Pulse publisher and other components to record metrics.
    """

    pulse_publish_total = PULSE_PUBLISH_TOTAL
    pulse_publish_latency_ms = PULSE_PUBLISH_LATENCY_MS
    sink_writes_total = SINK_WRITES_TOTAL
    sink_write_latency = SINK_WRITE_LATENCY


# Singleton instance
metrics_registry = MetricsRegistry()
