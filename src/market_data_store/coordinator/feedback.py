"""
Backpressure feedback system for write coordinator.

Provides in-process pub/sub for emitting and consuming backpressure signals.
Multiple subscribers can react to queue depth changes (e.g., pipeline rate
coordinator, HTTP webhooks, logging).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol

from loguru import logger


class BackpressureLevel(str, Enum):
    """Backpressure severity levels."""

    OK = "ok"  # Below low watermark - normal operation
    SOFT = "soft"  # Between low/high watermarks - caution
    HARD = "hard"  # At/above high watermark - producer MUST slow/stop


@dataclass(frozen=True)
class FeedbackEvent:
    """Immutable backpressure feedback event.

    Emitted by WriteCoordinator when queue depth crosses watermarks.
    Safe for async passing due to immutability.

    Attributes:
        coordinator_id: Identifies the coordinator (e.g., "bars-coord", "options-coord")
        queue_size: Current queue depth
        capacity: Maximum queue capacity
        level: Backpressure severity (OK, SOFT, HARD)
        reason: Optional context (e.g., "circuit_open", "queue_drained")
    """

    coordinator_id: str
    queue_size: int
    capacity: int
    level: BackpressureLevel
    reason: str | None = None

    @property
    def utilization(self) -> float:
        """Queue utilization as percentage (0.0 to 1.0)."""
        return self.queue_size / self.capacity if self.capacity > 0 else 0.0


class FeedbackSubscriber(Protocol):
    """Protocol for feedback event subscribers.

    Subscribers must be async callables accepting FeedbackEvent.
    Exceptions are caught and logged to prevent cascade failures.
    """

    async def __call__(self, event: FeedbackEvent) -> None:
        """Handle feedback event."""
        ...


class FeedbackBus:
    """In-process pub/sub bus for backpressure feedback.

    Supports multiple subscribers with error isolation. One subscriber's
    failure does not affect others. Best-effort delivery.

    Thread-safe for asyncio (no threading/multiprocessing).

    Example:
        bus = FeedbackBus()

        async def on_feedback(event: FeedbackEvent):
            if event.level == BackpressureLevel.HARD:
                await slow_down_producer()

        bus.subscribe(on_feedback)
        await bus.publish(FeedbackEvent(...))
    """

    def __init__(self) -> None:
        self._subs: list[FeedbackSubscriber] = []

    def subscribe(self, callback: FeedbackSubscriber) -> None:
        """Add a feedback subscriber.

        Args:
            callback: Async callable accepting FeedbackEvent
        """
        if callback not in self._subs:
            self._subs.append(callback)
            logger.debug(f"Feedback subscriber added (total: {len(self._subs)})")

    def unsubscribe(self, callback: FeedbackSubscriber) -> None:
        """Remove a feedback subscriber.

        Args:
            callback: Previously subscribed callback

        Note:
            No-op if callback not found (safe to call multiple times).
        """
        try:
            self._subs.remove(callback)
            logger.debug(f"Feedback subscriber removed (total: {len(self._subs)})")
        except ValueError:
            pass

    async def publish(self, event: FeedbackEvent) -> None:
        """Publish feedback event to all subscribers.

        Subscribers are called in registration order. Exceptions are caught
        and logged to prevent cascade failures (best-effort delivery).

        Args:
            event: Feedback event to publish
        """
        if not self._subs:
            return  # Fast path: no subscribers

        logger.debug(
            f"Publishing feedback: coord={event.coordinator_id} "
            f"level={event.level.value} "
            f"queue={event.queue_size}/{event.capacity} ({event.utilization:.1%})"
        )

        # Iterate over copy to allow unsubscribe during iteration
        for callback in list(self._subs):
            try:
                await callback(event)
            except Exception as exc:
                # Best-effort delivery - don't let one subscriber break others
                logger.debug(f"Feedback subscriber error (ignored): {type(exc).__name__}: {exc}")

    @property
    def subscriber_count(self) -> int:
        """Number of active subscribers."""
        return len(self._subs)


# --- Singleton accessor for in-process use ---

_bus: Optional[FeedbackBus] = None


def feedback_bus() -> FeedbackBus:
    """Get singleton FeedbackBus instance.

    For in-process use. Returns the same instance on all calls.
    Simple pattern suitable for library-first design.

    Returns:
        Singleton FeedbackBus instance

    Example:
        from market_data_store.coordinator import feedback_bus

        feedback_bus().subscribe(my_callback)
    """
    global _bus
    if _bus is None:
        _bus = FeedbackBus()
        logger.debug("FeedbackBus singleton initialized")
    return _bus
