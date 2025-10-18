"""
Ensures sink and pulse metrics are visible in Prometheus global REGISTRY.
Simply import this module at app startup.
"""

from prometheus_client import Counter, Gauge, Histogram

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


# --- Schema Drift Metrics (Phase 11.1) ---

SCHEMA_DRIFT_TOTAL = Counter(
    "schema_drift_total",
    "Total number of schema drift events detected",
    ["repo", "track", "schema"],
)

SCHEMA_DRIFT_LAST_DETECTED = Gauge(
    "schema_drift_last_detected_timestamp",
    "Timestamp of last schema drift detection",
    ["repo", "track", "schema"],
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
    schema_drift_total = SCHEMA_DRIFT_TOTAL
    schema_drift_last_detected = SCHEMA_DRIFT_LAST_DETECTED


# Singleton instance
metrics_registry = MetricsRegistry()
