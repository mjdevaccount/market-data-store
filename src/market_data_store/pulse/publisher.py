"""
Feedback publisher service for Pulse event bus.

Publishes Store's FeedbackEvent instances to Core's event bus, enabling
cross-service backpressure signaling. Subscribes to the in-process FeedbackBus
and translates events to EventEnvelope format.
"""

import time
from typing import Optional

from loguru import logger

from market_data_core.events import create_event_bus
from market_data_core.events.envelope import EventEnvelope, EventMeta
from market_data_core.events.protocols import EventBus
from market_data_core.telemetry import BackpressureLevel

# Import Store's extended FeedbackEvent (contains reason field)
from ..coordinator.feedback import FeedbackEvent, feedback_bus

from .config import PulseConfig

STREAM = "telemetry.feedback"


class FeedbackPublisherService:
    """Publishes Store feedback events to Pulse event bus.

    Bridges Store's in-process FeedbackBus with Core's distributed event bus.
    Converts Store's FeedbackEvent (with reason/utilization) to Core-compatible
    EventEnvelope format.

    Metrics tracked:
    - pulse_publish_total: Counter by stream/track/outcome
    - pulse_publish_latency_ms: Histogram of publish latency

    Example:
        >>> cfg = PulseConfig()
        >>> publisher = FeedbackPublisherService(cfg)
        >>> await publisher.start()  # Subscribes to feedback_bus()
        >>> # ... feedback events automatically published ...
        >>> await publisher.stop()
    """

    def __init__(self, cfg: PulseConfig | None = None):
        """Initialize publisher service.

        Args:
            cfg: Pulse configuration (defaults to PulseConfig())
        """
        self.cfg = cfg or PulseConfig()
        self._bus: Optional[EventBus] = None
        self._started = False

        # Metrics (initialized lazily to avoid import cycles)
        self._metrics_registry = None

    def _ensure_bus(self) -> EventBus:
        """Lazy initialization of event bus."""
        if self._bus is None:
            self._bus = create_event_bus(
                backend=self.cfg.backend,
                redis_url=self.cfg.redis_url if self.cfg.backend == "redis" else None,
            )
            logger.debug(f"Event bus created (backend={self.cfg.backend})")
        return self._bus

    async def start(self) -> None:
        """Start publisher service.

        Subscribes to the global feedback_bus() to receive Store feedback events.
        Does nothing if PULSE_ENABLED=false.
        """
        if not self.cfg.enabled:
            logger.info("Pulse publisher disabled (PULSE_ENABLED=false)")
            return

        if self._started:
            logger.warning("Pulse publisher already started")
            return

        # Subscribe to Store's in-process feedback bus
        bus = feedback_bus()
        bus.subscribe(self._on_feedback)
        self._started = True

        logger.info(
            f"Pulse publisher started (backend={self.cfg.backend}, "
            f"track={self.cfg.track}, stream={self.cfg.ns}.{STREAM})"
        )

    async def stop(self) -> None:
        """Stop publisher service.

        Unsubscribes from feedback_bus() and closes event bus connection.
        """
        if not self.cfg.enabled or not self._started:
            return

        # Unsubscribe from Store's feedback bus
        bus = feedback_bus()
        bus.unsubscribe(self._on_feedback)
        self._started = False

        logger.info("Pulse publisher stopped")

    async def publish_feedback(
        self,
        coordinator_id: str,
        queue_size: int,
        capacity: int,
        level: BackpressureLevel,
        *,
        reason: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        """Publish feedback event manually (for testing or direct use).

        Args:
            coordinator_id: Coordinator identifier
            queue_size: Current queue depth
            capacity: Maximum queue capacity
            level: Backpressure level (ok/soft/hard)
            reason: Optional context string
            headers: Optional additional headers

        Returns:
            Event ID from bus

        Raises:
            RuntimeError: If publisher not started or bus unavailable
        """
        if not self.cfg.enabled:
            raise RuntimeError("Pulse disabled (PULSE_ENABLED=false)")

        # Create Core-compatible FeedbackEvent (no Store extensions in payload)
        from market_data_core.telemetry import FeedbackEvent as CoreFeedbackEvent

        payload = CoreFeedbackEvent(
            coordinator_id=coordinator_id,
            queue_size=queue_size,
            capacity=capacity,
            level=level,
            source="store",
            ts=time.time(),
        )

        # Build metadata with Store extensions in headers
        meta = EventMeta(
            schema_id="telemetry.FeedbackEvent",
            track=self.cfg.track,
            headers=headers or {},
        )

        # Add Store-specific metadata to headers
        if reason:
            meta.headers["reason"] = reason
        utilization = queue_size / capacity if capacity > 0 else 0.0
        meta.headers["utilization"] = f"{utilization:.6f}"

        # Create envelope
        env = EventEnvelope(
            id="",  # Bus will generate
            key=coordinator_id,
            ts=time.time(),
            meta=meta,
            payload=payload,
        )

        # Publish to bus
        t0 = time.perf_counter()
        try:
            bus = self._ensure_bus()
            stream_name = f"{self.cfg.ns}.{STREAM}"
            event_id = await bus.publish(stream_name, env, key=coordinator_id)

            # Metrics: success
            latency_ms = (time.perf_counter() - t0) * 1000
            self._record_metric("success", latency_ms)

            logger.debug(
                f"Feedback published: id={event_id[:8]} coord={coordinator_id} "
                f"level={level.value} util={utilization:.1%} latency={latency_ms:.1f}ms"
            )
            return event_id

        except Exception as exc:
            # Metrics: error
            latency_ms = (time.perf_counter() - t0) * 1000
            self._record_metric("error", latency_ms)

            logger.error(
                f"Feedback publish failed: coord={coordinator_id} level={level.value} "
                f"error={type(exc).__name__}: {exc}"
            )
            raise

    async def _on_feedback(self, event: FeedbackEvent) -> None:
        """Callback for Store's in-process FeedbackBus.

        Translates Store FeedbackEvent → Core EventEnvelope and publishes.

        Args:
            event: Store's extended FeedbackEvent (with reason/utilization)
        """
        try:
            await self.publish_feedback(
                coordinator_id=event.coordinator_id,
                queue_size=event.queue_size,
                capacity=event.capacity,
                level=event.level,
                reason=event.reason,
            )
        except Exception as exc:
            # Don't propagate exceptions to FeedbackBus (best-effort delivery)
            logger.debug(f"Pulse publish error (ignored): {type(exc).__name__}: {exc}")

    def _record_metric(self, outcome: str, latency_ms: float) -> None:
        """Record Prometheus metrics for publish operation.

        Args:
            outcome: 'success' or 'error'
            latency_ms: Operation latency in milliseconds
        """
        try:
            # Lazy import to avoid circular dependency
            if self._metrics_registry is None:
                from ..metrics.registry import metrics_registry

                self._metrics_registry = metrics_registry

            # Increment counter
            if hasattr(self._metrics_registry, "pulse_publish_total"):
                self._metrics_registry.pulse_publish_total.labels(
                    stream=STREAM,
                    track=self.cfg.track,
                    outcome=outcome,
                ).inc()

            # Record latency
            if hasattr(self._metrics_registry, "pulse_publish_latency_ms"):
                self._metrics_registry.pulse_publish_latency_ms.labels(
                    stream=STREAM,
                    track=self.cfg.track,
                ).observe(latency_ms)

        except Exception as exc:
            # Don't let metrics failures break publishing
            logger.debug(f"Metrics recording failed: {type(exc).__name__}: {exc}")
