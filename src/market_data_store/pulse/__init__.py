"""
Pulse integration for Store's feedback system.

Provides event bus publishing for backpressure signals, enabling cross-service
coordination. Bridges Store's in-process FeedbackBus with Core's distributed
event bus (InMemory or Redis).

Usage:
    >>> from market_data_store.pulse import FeedbackPublisherService, PulseConfig
    >>> cfg = PulseConfig()
    >>> publisher = FeedbackPublisherService(cfg)
    >>> await publisher.start()  # Auto-subscribes to feedback_bus()

Environment Variables:
    PULSE_ENABLED: Enable Pulse integration (default: true)
    EVENT_BUS_BACKEND: 'inmem' or 'redis' (default: inmem)
    REDIS_URL: Redis connection URL (default: redis://localhost:6379/0)
    MD_NAMESPACE: Stream namespace (default: mdp)
    SCHEMA_TRACK: Schema version (default: v1)

Example:
    # Start publisher as background service
    publisher = FeedbackPublisherService()
    await publisher.start()

    # WriteCoordinator automatically emits feedback events
    # Publisher translates to EventEnvelope and publishes to event bus

    # Stop gracefully
    await publisher.stop()
"""

from .config import PulseConfig
from .publisher import FeedbackPublisherService

__all__ = [
    "PulseConfig",
    "FeedbackPublisherService",
]
