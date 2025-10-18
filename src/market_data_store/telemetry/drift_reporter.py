"""Schema drift detection and telemetry reporting.

Detects when Store's local schemas drift from Registry and emits Pulse events
for centralized monitoring and alerting.
"""

import hashlib
import time
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from market_data_store.metrics.registry import (
    SCHEMA_DRIFT_LAST_DETECTED,
    SCHEMA_DRIFT_TOTAL,
)
from market_data_store.pulse.config import PulseConfig
from market_data_store.pulse.publisher import FeedbackPublisherService


@dataclass
class SchemaSnapshot:
    """Local schema metadata for drift comparison."""

    name: str
    track: str
    sha256: str
    version: Optional[str] = None
    fetched_at: Optional[float] = None


class DriftReporter:
    """Detects and reports schema drift between Store and Registry.

    Compares local schema checksums with Registry schemas and emits
    telemetry.schema_drift events when mismatches are detected.
    """

    def __init__(
        self,
        pulse_config: Optional[PulseConfig] = None,
        publisher: Optional[FeedbackPublisherService] = None,
    ):
        """Initialize drift reporter.

        Args:
            pulse_config: Pulse configuration (auto-created if None)
            publisher: Pulse publisher service (auto-created if None)
        """
        self.pulse_config = pulse_config or PulseConfig()
        self.publisher = publisher

        # Track last drift detection per schema
        self._last_drift: dict[str, float] = {}

    async def start(self) -> None:
        """Start the drift reporter (initializes Pulse publisher)."""
        if self.publisher is None and self.pulse_config.enabled:
            self.publisher = FeedbackPublisherService(self.pulse_config)
            await self.publisher.start()
            logger.info("DriftReporter: Pulse publisher started")

    async def stop(self) -> None:
        """Stop the drift reporter (cleans up Pulse publisher)."""
        if self.publisher:
            await self.publisher.stop()
            logger.info("DriftReporter: Pulse publisher stopped")

    def compute_sha256(self, content: str | dict) -> str:
        """Compute SHA256 hash of schema content.

        Args:
            content: Schema content (string or dict)

        Returns:
            Hex-encoded SHA256 hash
        """
        if isinstance(content, dict):
            import json

            content = json.dumps(content, sort_keys=True)

        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def detect_and_emit_drift(
        self,
        local_snapshot: SchemaSnapshot,
        registry_sha: str,
        registry_version: Optional[str] = None,
    ) -> bool:
        """Detect drift between local and registry schemas.

        Args:
            local_snapshot: Local schema snapshot
            registry_sha: Registry schema SHA256 hash
            registry_version: Registry schema version (optional)

        Returns:
            True if drift detected, False otherwise
        """
        schema_key = f"{local_snapshot.track}/{local_snapshot.name}"

        # Check if schemas match
        if local_snapshot.sha256 == registry_sha:
            logger.debug(f"Schema {schema_key} in sync: {local_snapshot.sha256[:8]}...")
            return False

        # Drift detected
        logger.warning(
            f"Schema drift detected: {schema_key}\n"
            f"  Local:    {local_snapshot.sha256[:12]}... (v{local_snapshot.version})\n"
            f"  Registry: {registry_sha[:12]}... (v{registry_version})"
        )

        # Record metrics
        SCHEMA_DRIFT_TOTAL.labels(
            repo="market-data-store",
            track=local_snapshot.track,
            schema=local_snapshot.name,
        ).inc()

        SCHEMA_DRIFT_LAST_DETECTED.labels(
            repo="market-data-store",
            track=local_snapshot.track,
            schema=local_snapshot.name,
        ).set(time.time())

        # Update internal tracking
        self._last_drift[schema_key] = time.time()

        # Emit Pulse event if enabled
        await self._emit_drift_event(local_snapshot, registry_sha, registry_version)

        return True

    async def _emit_drift_event(
        self,
        local_snapshot: SchemaSnapshot,
        registry_sha: str,
        registry_version: Optional[str],
    ) -> None:
        """Emit telemetry.schema_drift Pulse event.

        Args:
            local_snapshot: Local schema snapshot
            registry_sha: Registry schema SHA256
            registry_version: Registry version (optional)
        """
        if not self.publisher or not self.pulse_config.enabled:
            logger.debug("Pulse disabled, skipping drift event emission")
            return

        try:
            from market_data_core.events import EventEnvelope, EventMeta

            # Construct drift event payload
            payload = {
                "repo": "market-data-store",
                "schema": local_snapshot.name,
                "track": local_snapshot.track,
                "local_sha256": local_snapshot.sha256,
                "local_version": local_snapshot.version,
                "registry_sha256": registry_sha,
                "registry_version": registry_version,
                "detected_at": time.time(),
            }

            # Create event envelope
            envelope = EventEnvelope(
                meta=EventMeta(
                    event_type="telemetry.schema_drift",
                    source="market-data-store",
                    timestamp=time.time(),
                    schema_id="telemetry.schema_drift",  # Required by EventMeta
                ),
                payload=payload,
            )

            # Publish to event bus
            await self.publisher._bus.publish(envelope)

            logger.info(f"Emitted schema_drift event: {local_snapshot.track}/{local_snapshot.name}")

        except Exception as e:
            # Fail-open: don't block on telemetry errors
            error_msg = str(e).replace("{", "{{").replace("}", "}}")
            logger.error(f"Failed to emit drift event: {error_msg}", exc_info=False)

    def get_last_drift_time(self, schema_key: str) -> Optional[float]:
        """Get timestamp of last drift detection for a schema.

        Args:
            schema_key: Schema key in format "track/name"

        Returns:
            Timestamp or None if never detected
        """
        return self._last_drift.get(schema_key)
