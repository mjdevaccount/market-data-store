"""Market Data Store - Persistence and CQRS-lite store for market data."""

__version__ = "0.6.2"

# Export coordinator components for external use (e.g., orchestrator integration)
from market_data_store.coordinator import (
    FeedbackBus,
    FeedbackEvent,
    feedback_bus,
    BackpressureLevel,
    WriteCoordinator,
)

__all__ = [
    "FeedbackBus",
    "FeedbackEvent",
    "feedback_bus",
    "BackpressureLevel",
    "WriteCoordinator",
]
