"""Tests for schema drift detection and reporting."""

import time
from unittest.mock import AsyncMock, patch

import pytest

from market_data_store.pulse.config import PulseConfig
from market_data_store.telemetry.drift_reporter import DriftReporter, SchemaSnapshot


@pytest.fixture
def pulse_config():
    """Pulse config with telemetry disabled."""
    return PulseConfig(enabled=False, backend="inmem", track="v1")


@pytest.fixture
def drift_reporter(pulse_config):
    """DriftReporter instance for testing."""
    return DriftReporter(pulse_config=pulse_config)


@pytest.fixture
async def drift_reporter_with_pulse(pulse_config):
    """DriftReporter with Pulse enabled (for integration tests)."""
    config = PulseConfig(enabled=True, backend="inmem", track="v1")
    reporter = DriftReporter(pulse_config=config)
    await reporter.start()
    yield reporter
    await reporter.stop()


class TestSchemaSnapshot:
    """Test SchemaSnapshot dataclass."""

    def test_snapshot_creation(self):
        """Test creating a schema snapshot."""
        snapshot = SchemaSnapshot(
            name="telemetry.FeedbackEvent",
            track="v1",
            sha256="abc123def456",
            version="1.2.0",
            fetched_at=time.time(),
        )

        assert snapshot.name == "telemetry.FeedbackEvent"
        assert snapshot.track == "v1"
        assert snapshot.sha256 == "abc123def456"
        assert snapshot.version == "1.2.0"
        assert snapshot.fetched_at is not None

    def test_snapshot_minimal(self):
        """Test snapshot with minimal required fields."""
        snapshot = SchemaSnapshot(name="test.schema", track="v1", sha256="hash123")

        assert snapshot.version is None
        assert snapshot.fetched_at is None


class TestDriftReporterInit:
    """Test DriftReporter initialization."""

    def test_init_default(self):
        """Test initialization with defaults."""
        reporter = DriftReporter()

        assert reporter.pulse_config is not None
        assert reporter.publisher is None
        assert isinstance(reporter._last_drift, dict)

    def test_init_with_config(self, pulse_config):
        """Test initialization with custom config."""
        reporter = DriftReporter(pulse_config=pulse_config)

        assert reporter.pulse_config == pulse_config
        assert reporter.publisher is None


class TestHashComputation:
    """Test SHA256 hash computation."""

    def test_compute_hash_from_string(self, drift_reporter):
        """Test computing hash from string content."""
        content = '{"type": "object", "properties": {}}'
        hash1 = drift_reporter.compute_sha256(content)
        hash2 = drift_reporter.compute_sha256(content)

        assert len(hash1) == 64  # SHA256 produces 64-char hex string
        assert hash1 == hash2  # Deterministic

    def test_compute_hash_from_dict(self, drift_reporter):
        """Test computing hash from dict content."""
        content = {"type": "object", "properties": {}, "required": []}
        hash1 = drift_reporter.compute_sha256(content)
        hash2 = drift_reporter.compute_sha256(content)

        assert len(hash1) == 64
        assert hash1 == hash2

    def test_compute_hash_dict_key_order_invariant(self, drift_reporter):
        """Test that dict key order doesn't affect hash."""
        content1 = {"a": 1, "b": 2, "c": 3}
        content2 = {"c": 3, "a": 1, "b": 2}

        hash1 = drift_reporter.compute_sha256(content1)
        hash2 = drift_reporter.compute_sha256(content2)

        assert hash1 == hash2  # sort_keys=True ensures consistent ordering


class TestDriftDetection:
    """Test drift detection logic."""

    @pytest.mark.asyncio
    async def test_no_drift_detected(self, drift_reporter):
        """Test when local and registry schemas match."""
        snapshot = SchemaSnapshot(
            name="test.schema",
            track="v1",
            sha256="abc123",
            version="1.0.0",
        )

        with patch("market_data_store.telemetry.drift_reporter.SCHEMA_DRIFT_TOTAL") as mock_counter:
            drift_detected = await drift_reporter.detect_and_emit_drift(
                snapshot, registry_sha="abc123", registry_version="1.0.0"
            )

            assert drift_detected is False
            mock_counter.labels.assert_not_called()

    @pytest.mark.asyncio
    async def test_drift_detected(self, drift_reporter):
        """Test when local and registry schemas differ."""
        snapshot = SchemaSnapshot(
            name="test.schema",
            track="v1",
            sha256="local_hash",
            version="1.0.0",
        )

        with (
            patch("market_data_store.telemetry.drift_reporter.SCHEMA_DRIFT_TOTAL") as mock_counter,
            patch(
                "market_data_store.telemetry.drift_reporter.SCHEMA_DRIFT_LAST_DETECTED"
            ) as mock_gauge,
        ):
            drift_detected = await drift_reporter.detect_and_emit_drift(
                snapshot, registry_sha="registry_hash", registry_version="1.1.0"
            )

            assert drift_detected is True

            # Verify metrics recorded
            mock_counter.labels.assert_called_once_with(
                repo="market-data-store", track="v1", schema="test.schema"
            )
            mock_counter.labels().inc.assert_called_once()

            mock_gauge.labels.assert_called_once_with(
                repo="market-data-store", track="v1", schema="test.schema"
            )
            mock_gauge.labels().set.assert_called_once()

    @pytest.mark.asyncio
    async def test_drift_tracking_state(self, drift_reporter):
        """Test that drift reporter tracks last drift time."""
        snapshot = SchemaSnapshot(name="test.schema", track="v1", sha256="local", version="1.0.0")

        with (
            patch("market_data_store.telemetry.drift_reporter.SCHEMA_DRIFT_TOTAL"),
            patch("market_data_store.telemetry.drift_reporter.SCHEMA_DRIFT_LAST_DETECTED"),
        ):
            before = time.time()
            await drift_reporter.detect_and_emit_drift(snapshot, registry_sha="registry")
            after = time.time()

            last_drift = drift_reporter.get_last_drift_time("v1/test.schema")
            assert last_drift is not None
            assert before <= last_drift <= after


class TestPulseEventEmission:
    """Test Pulse event emission."""

    @pytest.mark.asyncio
    async def test_emit_event_pulse_disabled(self, drift_reporter):
        """Test that no event is emitted when Pulse is disabled."""
        snapshot = SchemaSnapshot(name="test.schema", track="v1", sha256="local", version="1.0.0")

        # _emit_drift_event should exit early
        await drift_reporter._emit_drift_event(snapshot, "registry", "1.1.0")
        # No exception raised = success (fail-open)

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_emit_event_pulse_enabled(self, drift_reporter_with_pulse):
        """Test event emission when Pulse is enabled."""
        snapshot = SchemaSnapshot(
            name="telemetry.FeedbackEvent",
            track="v1",
            sha256="local_hash",
            version="1.0.0",
        )

        # Mock the bus
        drift_reporter_with_pulse.publisher._bus = AsyncMock()

        await drift_reporter_with_pulse._emit_drift_event(snapshot, "registry_hash", "1.1.0")

        # Verify bus.publish was called
        drift_reporter_with_pulse.publisher._bus.publish.assert_called_once()

        # Verify event structure
        call_args = drift_reporter_with_pulse.publisher._bus.publish.call_args
        envelope = call_args[0][0]

        # EventMeta stores event_type and source in headers
        assert envelope.meta.schema_id == "telemetry.schema_drift"
        assert envelope.meta.track == "v1"
        assert envelope.meta.headers["event_type"] == "telemetry.schema_drift"
        assert envelope.meta.headers["source"] == "market-data-store"
        assert envelope.payload["repo"] == "market-data-store"
        assert envelope.payload["schema"] == "telemetry.FeedbackEvent"
        assert envelope.payload["track"] == "v1"
        assert envelope.payload["local_sha256"] == "local_hash"
        assert envelope.payload["registry_sha256"] == "registry_hash"

    @pytest.mark.asyncio
    async def test_emit_event_error_handling(self, drift_reporter_with_pulse):
        """Test that emission errors don't propagate (fail-open)."""
        snapshot = SchemaSnapshot(name="test.schema", track="v1", sha256="local", version="1.0.0")

        # Mock bus to raise exception
        drift_reporter_with_pulse.publisher._bus = AsyncMock()
        drift_reporter_with_pulse.publisher._bus.publish.side_effect = Exception("Bus error")

        # Should not raise
        await drift_reporter_with_pulse._emit_drift_event(snapshot, "registry", "1.1.0")


class TestStartStop:
    """Test lifecycle management."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_start_creates_publisher(self):
        """Test that start() creates Pulse publisher if needed."""
        config = PulseConfig(enabled=True, backend="inmem", track="v1")
        reporter = DriftReporter(pulse_config=config)

        assert reporter.publisher is None

        await reporter.start()

        assert reporter.publisher is not None

        await reporter.stop()

    @pytest.mark.asyncio
    async def test_start_skips_if_disabled(self):
        """Test that start() skips publisher creation if disabled."""
        config = PulseConfig(enabled=False)
        reporter = DriftReporter(pulse_config=config)

        await reporter.start()

        assert reporter.publisher is None

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_stop_cleans_up_publisher(self):
        """Test that stop() cleans up Pulse publisher."""
        config = PulseConfig(enabled=True, backend="inmem", track="v1")
        reporter = DriftReporter(pulse_config=config)

        await reporter.start()
        publisher = reporter.publisher

        await reporter.stop()

        # Publisher should be stopped (bus closed)
        assert publisher._bus is None

    @pytest.mark.asyncio
    async def test_stop_idempotent(self):
        """Test that stop() can be called multiple times safely."""
        config = PulseConfig(enabled=False)
        reporter = DriftReporter(pulse_config=config)

        await reporter.stop()
        await reporter.stop()  # Should not raise


class TestIntegration:
    """Integration tests combining multiple components."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(5)
    async def test_end_to_end_drift_detection(self, drift_reporter_with_pulse):
        """Test complete drift detection and emission flow."""
        # Mock the event bus
        drift_reporter_with_pulse.publisher._bus = AsyncMock()

        # Create snapshot
        schema_dict = {"type": "object", "properties": {"name": {"type": "string"}}}
        local_hash = drift_reporter_with_pulse.compute_sha256(schema_dict)

        snapshot = SchemaSnapshot(
            name="test.MySchema",
            track="v1",
            sha256=local_hash,
            version="1.0.0",
            fetched_at=time.time(),
        )

        # Simulate drift
        registry_hash = "different_hash_from_registry"

        with (
            patch("market_data_store.telemetry.drift_reporter.SCHEMA_DRIFT_TOTAL") as mock_counter,
            patch(
                "market_data_store.telemetry.drift_reporter.SCHEMA_DRIFT_LAST_DETECTED"
            ) as mock_gauge,
        ):
            drift = await drift_reporter_with_pulse.detect_and_emit_drift(
                snapshot, registry_hash, "1.1.0"
            )

            assert drift is True

            # Metrics recorded
            mock_counter.labels().inc.assert_called_once()
            mock_gauge.labels().set.assert_called_once()

            # Event emitted
            drift_reporter_with_pulse.publisher._bus.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_schemas_tracked(self, drift_reporter):
        """Test tracking drift for multiple schemas."""
        schemas = [
            SchemaSnapshot("schema1", "v1", "hash1"),
            SchemaSnapshot("schema2", "v1", "hash2"),
            SchemaSnapshot("schema3", "v2", "hash3"),
        ]

        with (
            patch("market_data_store.telemetry.drift_reporter.SCHEMA_DRIFT_TOTAL"),
            patch("market_data_store.telemetry.drift_reporter.SCHEMA_DRIFT_LAST_DETECTED"),
        ):
            for snapshot in schemas:
                await drift_reporter.detect_and_emit_drift(snapshot, registry_sha="registry_hash")

            # All tracked
            assert drift_reporter.get_last_drift_time("v1/schema1") is not None
            assert drift_reporter.get_last_drift_time("v1/schema2") is not None
            assert drift_reporter.get_last_drift_time("v2/schema3") is not None
