"""Write Coordinator (Phase 4.2A + 4.2B)

Core producer→queue→worker→sink pipeline with:
- BoundedQueue (watermarks + overflow strategies)
- RetryPolicy with jitter
- CircuitBreaker for fault protection
- SinkWorker batcher with time/size flushing
- WriteCoordinator orchestration & health checks
- Prometheus metrics
- Dead Letter Queue (file-based NDJSON)
- Environment-based settings
"""

from .types import Sink, BackpressureCallback, T, QueueFullError
from .policy import (
    RetryPolicy,
    default_retry_classifier,
    CircuitBreaker,
    CircuitOpenError,
)
from .queue import BoundedQueue
from .worker import SinkWorker
from .write_coordinator import WriteCoordinator, CoordinatorHealth
from .settings import CoordinatorRuntimeSettings
from .dlq import DeadLetterQueue, DLQRecord

__all__ = [
    # types
    "Sink",
    "BackpressureCallback",
    "T",
    "QueueFullError",
    "CoordinatorHealth",
    "DLQRecord",
    # policies
    "RetryPolicy",
    "default_retry_classifier",
    "CircuitBreaker",
    "CircuitOpenError",
    # runtime
    "BoundedQueue",
    "SinkWorker",
    "WriteCoordinator",
    "CoordinatorRuntimeSettings",
    # tooling
    "DeadLetterQueue",
]
