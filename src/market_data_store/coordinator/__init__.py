"""Write Coordinator (Phase 4.2A + 4.2B + Phase 8.0)

Core producer→queue→worker→sink pipeline with:
- BoundedQueue (watermarks + overflow strategies)
- RetryPolicy with jitter
- CircuitBreaker for fault protection
- SinkWorker batcher with time/size flushing
- WriteCoordinator orchestration & health checks
- Prometheus metrics
- Dead Letter Queue (file-based NDJSON)
- Environment-based settings
- Phase 8.0: Core v1.1.0 contract adoption (FeedbackEvent extends Core DTO)
"""

# Core v1.1.0 contracts (imported directly)
from market_data_core.telemetry import BackpressureLevel

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
from .settings import CoordinatorRuntimeSettings, FeedbackSettings
from .dlq import DeadLetterQueue, DLQRecord
from .feedback import (
    FeedbackEvent,  # Store-extended (inherits from Core)
    FeedbackSubscriber,
    FeedbackBus,
    feedback_bus,
)
from .http_broadcast import HttpFeedbackBroadcaster

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
    # feedback (Phase 6.0A)
    "BackpressureLevel",
    "FeedbackEvent",
    "FeedbackSubscriber",
    "FeedbackBus",
    "feedback_bus",
    "FeedbackSettings",
    "HttpFeedbackBroadcaster",
]
