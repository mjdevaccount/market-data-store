"""
HTTP broadcaster for backpressure feedback events.

Sends FeedbackEvent JSON payloads to a configured HTTP endpoint.
Gracefully degrades if httpx is not installed or if disabled via settings.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from loguru import logger

from .feedback import FeedbackEvent, feedback_bus

# Optional httpx dependency
try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    httpx = None  # type: ignore


class HttpFeedbackBroadcaster:
    """HTTP broadcaster for feedback events.

    Subscribes to FeedbackBus and POSTs events to configured endpoint.
    Includes retry logic and graceful degradation.

    Example:
        broadcaster = HttpFeedbackBroadcaster(
            endpoint="http://dashboard:8080/feedback",
            timeout=2.5,
            max_retries=3
        )
        await broadcaster.start()
        # ... coordinator runs ...
        await broadcaster.stop()
    """

    def __init__(
        self,
        endpoint: str,
        *,
        timeout: float = 2.5,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        enabled: bool = True,
    ):
        """Initialize HTTP broadcaster.

        Args:
            endpoint: HTTP URL to POST feedback events to
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts on failure
            backoff_base: Base backoff in seconds (multiplied by attempt number)
            enabled: Whether broadcasting is enabled
        """
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.enabled = enabled
        self._client: Optional[httpx.AsyncClient] = None  # type: ignore
        self._started = False

    async def start(self) -> None:
        """Start broadcaster and subscribe to feedback bus."""
        if not self.enabled:
            logger.info("HTTP feedback broadcaster disabled")
            return

        if not HTTPX_AVAILABLE:
            logger.warning(
                "httpx not installed - HTTP feedback broadcaster disabled. "
                "Install with: pip install httpx"
            )
            return

        self._client = httpx.AsyncClient(timeout=self.timeout)
        feedback_bus().subscribe(self._on_feedback)
        self._started = True
        logger.info(f"HTTP feedback broadcaster started (endpoint={self.endpoint})")

    async def stop(self) -> None:
        """Stop broadcaster and unsubscribe from feedback bus."""
        if not self._started:
            return

        feedback_bus().unsubscribe(self._on_feedback)

        if self._client:
            await self._client.aclose()
            self._client = None

        self._started = False
        logger.info("HTTP feedback broadcaster stopped")

    async def _on_feedback(self, event: FeedbackEvent) -> None:
        """Handle feedback event by POSTing to endpoint.

        Args:
            event: Feedback event to broadcast
        """
        if not self.enabled or not self._client:
            return

        payload = {
            "coordinator_id": event.coordinator_id,
            "queue_size": event.queue_size,
            "capacity": event.capacity,
            "level": event.level.value,
            "reason": event.reason,
            "utilization": event.utilization,
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self._client.post(self.endpoint, json=payload)

                if response.status_code < 400:
                    logger.debug(
                        f"Feedback broadcast success: {event.coordinator_id} "
                        f"level={event.level.value} ({response.status_code})"
                    )
                    return
                else:
                    logger.warning(
                        f"Feedback broadcast HTTP {response.status_code}: " f"{response.text[:100]}"
                    )

            except Exception as exc:
                logger.debug(
                    f"Feedback broadcast attempt {attempt}/{self.max_retries} failed: "
                    f"{type(exc).__name__}: {exc}"
                )

            # Retry with exponential backoff
            if attempt < self.max_retries:
                await asyncio.sleep(self.backoff_base * attempt)

        # All retries exhausted
        logger.error(
            f"Feedback broadcast failed after {self.max_retries} attempts: "
            f"{event.coordinator_id} level={event.level.value}"
        )

    async def broadcast_one(self, event: FeedbackEvent) -> bool:
        """Manually broadcast a single event (for testing).

        Args:
            event: Feedback event to broadcast

        Returns:
            True if broadcast succeeded, False otherwise
        """
        if not self.enabled or not self._client:
            return False

        try:
            await self._on_feedback(event)
            return True
        except Exception as exc:
            logger.error(f"Manual broadcast failed: {exc}")
            return False
