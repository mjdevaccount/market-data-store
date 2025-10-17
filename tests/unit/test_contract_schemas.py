"""
Contract tests for Core v1.1.0 DTOs.

Ensures Store uses Core types correctly and schemas match expectations.
Validates adapter pattern maintains Core compatibility.
"""

import time
from market_data_core.telemetry import (
    FeedbackEvent as CoreFeedbackEvent,
    BackpressureLevel,
    HealthStatus,
    HealthComponent,
)
from market_data_store.coordinator import FeedbackEvent


def test_feedback_event_extends_core():
    """Store FeedbackEvent is-a Core FeedbackEvent (subclass relationship)."""
    assert issubclass(FeedbackEvent, CoreFeedbackEvent)


def test_feedback_event_schema_roundtrip():
    """FeedbackEvent serializes/deserializes correctly with Core fields."""
    event = FeedbackEvent.create(
        coordinator_id="test-coord",
        queue_size=8000,
        capacity=10000,
        level=BackpressureLevel.hard,
        reason="high_watermark",
    )

    # Serialize
    json_str = event.model_dump_json()

    # Deserialize as Store FeedbackEvent
    rehydrated = FeedbackEvent.model_validate_json(json_str)

    assert rehydrated.coordinator_id == "test-coord"
    assert rehydrated.level == BackpressureLevel.hard
    assert rehydrated.queue_size == 8000
    assert rehydrated.capacity == 10000
    assert rehydrated.source == "store"
    assert isinstance(rehydrated.ts, float)
    assert rehydrated.reason == "high_watermark"


def test_feedback_event_core_subset_parseable():
    """Core-only consumers can parse Store events (ignore extra fields)."""
    store_event = FeedbackEvent.create(
        coordinator_id="test",
        queue_size=80,
        capacity=100,
        level=BackpressureLevel.soft,
        reason="store_specific_context",  # Extra field
    )

    # Serialize
    json_data = store_event.model_dump()

    # Core consumer parses (Pydantic ignores unknown fields)
    core_event = CoreFeedbackEvent.model_validate(json_data)

    # Core fields present
    assert core_event.coordinator_id == "test"
    assert core_event.queue_size == 80
    assert core_event.level == BackpressureLevel.soft

    # Extra field ignored (Core doesn't have 'reason')
    assert not hasattr(core_event, "reason")


def test_feedback_event_factory_auto_fills():
    """FeedbackEvent.create() factory auto-fills ts and source."""
    before = time.time()
    event = FeedbackEvent.create(
        coordinator_id="test",
        queue_size=50,
        capacity=100,
        level=BackpressureLevel.ok,
    )
    after = time.time()

    # ts auto-filled with current time
    assert before <= event.ts <= after

    # source auto-filled with "store"
    assert event.source == "store"

    # reason defaults to None
    assert event.reason is None


def test_feedback_event_utilization_property():
    """Store FeedbackEvent has utilization property (not in Core)."""
    event = FeedbackEvent.create(
        coordinator_id="test",
        queue_size=75,
        capacity=100,
        level=BackpressureLevel.soft,
    )

    # Store-specific property
    assert event.utilization == 0.75  # 75%


def test_feedback_event_utilization_zero_capacity():
    """FeedbackEvent.utilization handles zero queue_size gracefully."""
    # Core enforces capacity > 0, so test zero queue_size instead
    event = FeedbackEvent(
        coordinator_id="test",
        queue_size=0,
        capacity=100,  # Core requires capacity > 0
        level=BackpressureLevel.ok,
        source="store",
        ts=time.time(),
    )

    assert event.utilization == 0.0  # 0/100 = 0.0


def test_backpressure_level_values():
    """BackpressureLevel enum has expected Core values."""
    assert BackpressureLevel.ok.value == "ok"
    assert BackpressureLevel.soft.value == "soft"
    assert BackpressureLevel.hard.value == "hard"


def test_health_status_schema():
    """HealthStatus conforms to Core schema."""
    components = [
        HealthComponent(name="database", state="healthy"),
        HealthComponent(name="redis", state="degraded"),
    ]

    health = HealthStatus(
        service="market-data-store",
        state="degraded",
        components=components,
        version="0.4.0",
        ts=time.time(),
    )

    # Serialize
    json_str = health.model_dump_json()

    # Deserialize
    rehydrated = HealthStatus.model_validate_json(json_str)

    assert rehydrated.service == "market-data-store"
    assert rehydrated.state == "degraded"
    assert len(rehydrated.components) == 2
    assert rehydrated.version == "0.4.0"


def test_health_component_state_enum():
    """HealthComponent.state accepts Core enum values."""
    # Test all valid states
    for state in ["healthy", "degraded", "unhealthy"]:
        component = HealthComponent(name="test", state=state)
        assert component.state == state


def test_health_component_details():
    """HealthComponent supports optional details dict."""
    component = HealthComponent(
        name="database",
        state="degraded",
        details={"error": "connection_timeout", "retries": "3"},
    )

    assert component.details["error"] == "connection_timeout"
    assert component.details["retries"] == "3"


def test_health_status_aggregate_state():
    """HealthStatus state aggregates from components."""
    # All healthy
    healthy_components = [
        HealthComponent(name="db", state="healthy"),
        HealthComponent(name="redis", state="healthy"),
    ]

    # One degraded
    mixed_components = [
        HealthComponent(name="db", state="healthy"),
        HealthComponent(name="redis", state="degraded"),
    ]

    # Healthy case
    health_ok = HealthStatus(
        service="store",
        state="healthy",
        components=healthy_components,
        version="0.4.0",
        ts=time.time(),
    )
    assert health_ok.state == "healthy"

    # Degraded case
    health_degraded = HealthStatus(
        service="store",
        state="degraded",
        components=mixed_components,
        version="0.4.0",
        ts=time.time(),
    )
    assert health_degraded.state == "degraded"


def test_isinstance_checks():
    """Type checks work correctly with adapter pattern."""
    store_event = FeedbackEvent.create(
        coordinator_id="test",
        queue_size=50,
        capacity=100,
        level=BackpressureLevel.ok,
    )

    # Store event is-a Core event
    assert isinstance(store_event, CoreFeedbackEvent)
    assert isinstance(store_event, FeedbackEvent)

    # Enum compatibility
    assert isinstance(BackpressureLevel.ok, BackpressureLevel)
