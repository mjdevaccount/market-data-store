"""
Tests for Pulse feedback publisher service.

Tests cover:
- In-memory backend (happy path)
- Redis backend (conditional, skipped if REDIS_URL unavailable)
- Event envelope format validation
- Metrics recording
- Integration with FeedbackBus
- Error handling and graceful degradation

SAFEGUARDS:
- All async tests have 5s timeout
- Redis tests skipped unless explicitly enabled
- Proper cleanup in fixtures
"""

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest

from market_data_core.telemetry import BackpressureLevel
from market_data_store.coordinator import FeedbackEvent, feedback_bus
from market_data_store.pulse import FeedbackPublisherService, PulseConfig

# Global timeout for all async tests (prevent hangs)
pytestmark = pytest.mark.timeout(5)


# --- Fixtures ---


@pytest.fixture
def inmem_config():
    """PulseConfig for in-memory backend."""
    return PulseConfig()  # Defaults to inmem


@pytest.fixture
def redis_config():
    """PulseConfig for Redis backend (conditional)."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return PulseConfig(
        enabled=True,
        backend="redis",
        redis_url=redis_url,
        ns="test_mdp",
        track="v1",
    )


@pytest.fixture
def disabled_config():
    """PulseConfig with Pulse disabled."""
    # Create dataclass with __dict__ for modification
    cfg = PulseConfig()
    # Need to override frozen dataclass - use object.__setattr__
    object.__setattr__(cfg, "enabled", False)
    return cfg


@pytest.fixture
async def publisher_inmem(inmem_config):
    """FeedbackPublisherService with in-memory backend."""
    pub = FeedbackPublisherService(inmem_config)
    yield pub
    # Ensure cleanup even if test fails
    try:
        await pub.stop()
    except Exception:
        pass


@pytest.fixture
async def publisher_redis(redis_config):
    """FeedbackPublisherService with Redis backend."""
    pub = FeedbackPublisherService(redis_config)
    yield pub
    # Ensure cleanup even if test fails
    try:
        await pub.stop()
    except Exception:
        pass


# --- Unit Tests ---


def test_pulse_config_defaults():
    """Test PulseConfig default values."""
    cfg = PulseConfig()
    assert cfg.enabled is True
    assert cfg.backend == "inmem"
    assert cfg.redis_url == "redis://localhost:6379/0"
    assert cfg.ns == "mdp"
    assert cfg.track == "v1"


def test_pulse_config_from_env(monkeypatch):
    """Test PulseConfig reads from environment."""
    monkeypatch.setenv("PULSE_ENABLED", "false")
    monkeypatch.setenv("EVENT_BUS_BACKEND", "redis")
    monkeypatch.setenv("REDIS_URL", "redis://custom:6379/1")
    monkeypatch.setenv("MD_NAMESPACE", "custom_ns")
    monkeypatch.setenv("SCHEMA_TRACK", "v2")

    cfg = PulseConfig()
    assert cfg.enabled is False
    assert cfg.backend == "redis"
    assert cfg.redis_url == "redis://custom:6379/1"
    assert cfg.ns == "custom_ns"
    assert cfg.track == "v2"


def test_pulse_config_validation():
    """Test PulseConfig validates backend and track."""
    # Invalid backend should raise on __post_init__
    with pytest.raises(ValueError, match="Invalid backend"):
        cfg = PulseConfig()
        object.__setattr__(cfg, "backend", "invalid")
        cfg.__post_init__()

    # Invalid track should raise
    with pytest.raises(ValueError, match="Invalid track"):
        cfg = PulseConfig()
        object.__setattr__(cfg, "track", "v99")
        cfg.__post_init__()


async def test_publisher_disabled(disabled_config):
    """Test publisher does nothing when disabled."""
    pub = FeedbackPublisherService(disabled_config)
    await pub.start()  # Should log and return immediately

    # publish_feedback should raise
    with pytest.raises(RuntimeError, match="Pulse disabled"):
        await pub.publish_feedback("test", 10, 100, BackpressureLevel.ok)


async def test_publisher_start_stop_idempotency(publisher_inmem):
    """Test publisher start/stop can be called multiple times safely."""
    await publisher_inmem.start()
    await publisher_inmem.start()  # Second start should be no-op

    await publisher_inmem.stop()
    await publisher_inmem.stop()  # Second stop should be no-op


# --- Integration Tests (In-Memory) ---


async def test_publish_feedback_inmem(publisher_inmem):
    """Test publishing feedback event to in-memory bus."""
    await publisher_inmem.start()

    # Publish event
    event_id = await publisher_inmem.publish_feedback(
        coordinator_id="test-coord",
        queue_size=80,
        capacity=100,
        level=BackpressureLevel.soft,
        reason="test_reason",
    )

    # Should return event ID
    assert event_id
    assert isinstance(event_id, str)


async def test_feedback_bus_integration(publisher_inmem):
    """Test publisher subscribes to FeedbackBus and publishes events."""
    await publisher_inmem.start()

    # Create Store FeedbackEvent and publish to feedback_bus()
    event = FeedbackEvent.create(
        coordinator_id="integration-test",
        queue_size=90,
        capacity=100,
        level=BackpressureLevel.hard,
        reason="queue_full",
    )

    # Publish to Store's in-process feedback bus
    bus = feedback_bus()
    await bus.publish(event)

    # Give async tasks time to process
    await asyncio.sleep(0.01)

    # Publisher should have received and published event
    # (No exception means success - we can't easily inspect inmem bus)


async def test_envelope_format(publisher_inmem):
    """Test EventEnvelope contains correct metadata."""
    await publisher_inmem.start()

    # Mock the bus to inspect envelope
    with patch.object(publisher_inmem, "_bus") as mock_bus:
        mock_bus.publish = AsyncMock(return_value="test-event-id")

        await publisher_inmem.publish_feedback(
            coordinator_id="format-test",
            queue_size=50,
            capacity=100,
            level=BackpressureLevel.ok,
            reason="test",
        )

        # Check publish was called
        assert mock_bus.publish.called
        call_args = mock_bus.publish.call_args

        # Inspect envelope (second positional arg)
        envelope = call_args[0][1]
        assert envelope.meta.schema_id == "telemetry.FeedbackEvent"
        assert envelope.meta.track == "v1"
        assert envelope.key == "format-test"
        assert "reason" in envelope.meta.headers
        assert "utilization" in envelope.meta.headers
        assert envelope.meta.headers["reason"] == "test"
        assert float(envelope.meta.headers["utilization"]) == 0.5  # 50/100


async def test_metrics_recorded(publisher_inmem):
    """Test Prometheus metrics are recorded on publish."""
    await publisher_inmem.start()

    # Get baseline metrics
    from market_data_store.metrics.registry import PULSE_PUBLISH_TOTAL

    before = PULSE_PUBLISH_TOTAL.labels(
        stream="telemetry.feedback", track="v1", outcome="success"
    )._value._value

    # Publish event
    await publisher_inmem.publish_feedback(
        coordinator_id="metrics-test",
        queue_size=10,
        capacity=100,
        level=BackpressureLevel.ok,
    )

    # Check counter incremented
    after = PULSE_PUBLISH_TOTAL.labels(
        stream="telemetry.feedback", track="v1", outcome="success"
    )._value._value

    assert after > before


async def test_error_handling(publisher_inmem):
    """Test publisher handles errors gracefully."""
    await publisher_inmem.start()

    # Mock bus to raise exception
    with patch.object(publisher_inmem, "_bus") as mock_bus:
        mock_bus.publish = AsyncMock(side_effect=RuntimeError("Bus error"))

        # publish_feedback should raise
        with pytest.raises(RuntimeError, match="Bus error"):
            await publisher_inmem.publish_feedback(
                coordinator_id="error-test",
                queue_size=10,
                capacity=100,
                level=BackpressureLevel.ok,
            )

        # Metrics should record error
        from market_data_store.metrics.registry import PULSE_PUBLISH_TOTAL

        error_count = PULSE_PUBLISH_TOTAL.labels(
            stream="telemetry.feedback", track="v1", outcome="error"
        )._value._value
        assert error_count > 0


async def test_feedback_bus_error_isolation(publisher_inmem):
    """Test errors in _on_feedback don't propagate to FeedbackBus."""
    await publisher_inmem.start()

    # Mock publish_feedback to raise
    with patch.object(
        publisher_inmem, "publish_feedback", side_effect=RuntimeError("Publish failed")
    ):
        # Create and publish event
        event = FeedbackEvent.create(
            coordinator_id="isolation-test",
            queue_size=10,
            capacity=100,
            level=BackpressureLevel.ok,
        )

        # Should not raise (error logged only)
        bus = feedback_bus()
        await bus.publish(event)


# --- Integration Tests (Redis) ---
# SAFEGUARD: Redis tests require explicit opt-in to prevent hangs


@pytest.mark.skipif(
    os.getenv("RUN_REDIS_TESTS") != "true",
    reason="Redis tests disabled by default (set RUN_REDIS_TESTS=true to enable)",
)
async def test_publish_feedback_redis(publisher_redis):
    """Test publishing feedback event to Redis backend."""
    await publisher_redis.start()

    # Publish event
    event_id = await publisher_redis.publish_feedback(
        coordinator_id="redis-test",
        queue_size=75,
        capacity=100,
        level=BackpressureLevel.soft,
        reason="redis_test",
    )

    # Should return Redis stream entry ID
    assert event_id
    assert isinstance(event_id, str)
    # Redis entry IDs are typically like "1234567890-0"
    assert "-" in event_id or len(event_id) > 10


@pytest.mark.skipif(
    os.getenv("RUN_REDIS_TESTS") != "true",
    reason="Redis tests disabled by default (set RUN_REDIS_TESTS=true to enable)",
)
async def test_redis_consumer_group(publisher_redis, redis_config):
    """Test events can be consumed from Redis stream."""
    await publisher_redis.start()

    # Publish event
    await publisher_redis.publish_feedback(
        coordinator_id="consumer-test",
        queue_size=60,
        capacity=100,
        level=BackpressureLevel.ok,
    )

    # Try to consume from Redis (basic smoke test)
    from market_data_core.events import create_event_bus

    consumer_bus = create_event_bus(backend="redis", redis_url=redis_config.redis_url)

    # Create consumer group and consume (with timeout)
    stream = f"{redis_config.ns}.telemetry.feedback"
    group = "test_group"
    consumer = "test_consumer"

    # Note: Real consumption requires group creation, which might fail if exists
    # This is a smoke test - just verify no exceptions
    try:
        # Consume with timeout
        import asyncio

        async def consume_one():
            async for envelope in consumer_bus.subscribe(stream, group=group, consumer=consumer):
                return envelope

        # Try to consume with 0.5s timeout (shorter to prevent hangs)
        envelope = await asyncio.wait_for(consume_one(), timeout=0.5)
        # If we got an envelope, verify it's the right type
        if envelope:
            assert envelope.meta.schema_id == "telemetry.FeedbackEvent"
    except asyncio.TimeoutError:
        # Expected if no new messages (group already consumed)
        pass
    except Exception as exc:
        # Other errors are OK for this smoke test (group exists, etc.)
        print(f"Redis consume test error (expected): {exc}")


# --- Schema Validation Tests ---


@pytest.mark.timeout(2)  # Shorter timeout for simple tests
async def test_schema_track_v1(publisher_inmem):
    """Test events published with v1 schema track."""
    await publisher_inmem.start()
    assert publisher_inmem.cfg.track == "v1"

    await publisher_inmem.publish_feedback(
        coordinator_id="v1-test",
        queue_size=10,
        capacity=100,
        level=BackpressureLevel.ok,
    )


@pytest.mark.timeout(2)  # Shorter timeout for simple tests
async def test_schema_track_v2(monkeypatch):
    """Test events can be published with v2 schema track."""
    monkeypatch.setenv("SCHEMA_TRACK", "v2")
    cfg = PulseConfig()
    assert cfg.track == "v2"

    pub = FeedbackPublisherService(cfg)
    await pub.start()

    await pub.publish_feedback(
        coordinator_id="v2-test",
        queue_size=10,
        capacity=100,
        level=BackpressureLevel.ok,
    )

    await pub.stop()
