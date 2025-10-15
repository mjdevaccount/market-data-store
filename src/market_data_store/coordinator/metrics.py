"""
Prometheus metrics for the write coordinator.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# Coordinator-level
COORD_ITEMS_SUBMITTED = Counter(
    "mds_coord_items_submitted_total",
    "Items submitted to coordinator",
    ["coord_id"],
)
COORD_ITEMS_DROPPED = Counter(
    "mds_coord_items_dropped_total",
    "Items dropped by overflow/drop policies",
    ["coord_id", "reason"],
)
COORD_QUEUE_DEPTH = Gauge(
    "mds_coord_queue_depth",
    "Current coordinator queue depth",
    ["coord_id"],
)
COORD_WORKERS_ALIVE = Gauge(
    "mds_coord_workers_alive",
    "Number of alive workers",
    ["coord_id"],
)

# Worker-level
WORKER_BATCHES_WRITTEN = Counter(
    "mds_worker_batches_written_total",
    "Batches successfully written by worker",
    ["coord_id", "worker_id"],
)
WORKER_WRITE_ERRORS = Counter(
    "mds_worker_write_errors_total",
    "Worker write errors (post-retry fatal)",
    ["coord_id", "worker_id", "error_type"],
)
WORKER_WRITE_LATENCY = Histogram(
    "mds_worker_write_latency_seconds",
    "Latency of sink.write(batch) including retries",
    ["coord_id", "worker_id"],
)

# Circuit breaker
CB_STATE = Gauge(
    "mds_coord_circuit_state",
    "Circuit state: 0=closed, 1=open, 2=half_open",
    ["coord_id"],
)
