"""
Contract tests validating Store schemas against Registry.

These tests ensure Store's extended models remain compatible with
Core schemas published to the Schema Registry.
"""

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from market_data_store.coordinator.feedback import FeedbackEvent
from market_data_core.telemetry import BackpressureLevel


SCHEMA_DIR = Path(__file__).parent.parent / "fixtures" / "schemas"


@pytest.fixture
def registry_schemas():
    """Load schemas fetched from Registry."""
    schemas = {}
    for schema_file in SCHEMA_DIR.glob("*.json"):
        if not schema_file.name.startswith("_"):
            with open(schema_file) as f:
                schema_name = schema_file.stem
                schemas[schema_name] = json.load(f)
    return schemas


@pytest.fixture
def metadata():
    """Load Registry metadata."""
    meta_file = SCHEMA_DIR / "_metadata.json"
    if meta_file.exists():
        with open(meta_file) as f:
            return json.load(f)
    return None


def test_registry_schemas_available(registry_schemas):
    """Test that critical schemas were fetched from Registry."""
    assert "telemetry.FeedbackEvent" in registry_schemas
    assert "telemetry.HealthStatus" in registry_schemas
    assert "telemetry.HealthComponent" in registry_schemas


def test_metadata_present(metadata):
    """Test that Registry metadata exists."""
    assert metadata is not None
    assert "registry_url" in metadata
    assert "track" in metadata
    assert "fetched_at" in metadata


def test_feedback_event_v1_compatible(registry_schemas):
    """Test Store's FeedbackEvent is compatible with Registry v1 schema."""
    schema = registry_schemas["telemetry.FeedbackEvent"]

    # Create Store's extended FeedbackEvent
    event = FeedbackEvent.create(
        coordinator_id="test_coord",
        queue_size=80,
        capacity=100,
        level=BackpressureLevel.soft,
        reason="high_watermark",  # Store-specific extension
    )

    # Serialize to dict (as would be sent over wire)
    payload = event.model_dump(mode="json")

    # Validate against Registry schema
    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(payload))

    # Should pass - extra fields allowed by default
    assert len(errors) == 0, f"Validation errors: {[e.message for e in errors]}"


def test_feedback_event_core_fields(registry_schemas):
    """Test that Store's FeedbackEvent includes all Core required fields."""
    schema = registry_schemas["telemetry.FeedbackEvent"]

    # Get required fields from schema
    required_fields = schema.get("required", [])

    # Create minimal event
    event = FeedbackEvent.create(
        coordinator_id="test",
        queue_size=50,
        capacity=100,
        level=BackpressureLevel.ok,
    )

    payload = event.model_dump(mode="json")

    # Verify all required fields present
    for field in required_fields:
        assert field in payload, f"Missing required field: {field}"


def test_backpressure_level_enum_stable(registry_schemas):
    """Test that BackpressureLevel enum values match Registry schema."""
    schema = registry_schemas["telemetry.FeedbackEvent"]

    # Get enum values from schema (if defined)
    level_schema = schema.get("properties", {}).get("level", {})

    # Verify enum values if specified
    if "enum" in level_schema:
        expected_values = set(level_schema["enum"])
        actual_values = {level.value for level in BackpressureLevel}

        assert actual_values == expected_values, (
            f"BackpressureLevel enum mismatch: " f"expected {expected_values}, got {actual_values}"
        )


def test_store_extension_backward_compatible():
    """Test that Store's extensions don't break Core compatibility."""
    # Create Store event with all extensions
    store_event = FeedbackEvent.create(
        coordinator_id="store",
        queue_size=90,
        capacity=100,
        level=BackpressureLevel.hard,
        reason="queue_full",  # Store extension
    )

    # Serialize
    json_str = store_event.model_dump_json()

    # Core should be able to deserialize (will ignore extra fields)
    from market_data_core.telemetry import FeedbackEvent as CoreFeedback

    core_event = CoreFeedback.model_validate_json(json_str)

    # Core sees all required fields
    assert core_event.coordinator_id == "store"
    assert core_event.queue_size == 90
    assert core_event.capacity == 100
    assert core_event.level == BackpressureLevel.hard

    # Core doesn't see Store's extension (that's fine)
    assert not hasattr(core_event, "reason")


@pytest.mark.parametrize(
    "level",
    [BackpressureLevel.ok, BackpressureLevel.soft, BackpressureLevel.hard],
)
def test_feedback_event_all_levels_valid(registry_schemas, level):
    """Test all backpressure levels validate against Registry schema."""
    schema = registry_schemas["telemetry.FeedbackEvent"]

    event = FeedbackEvent.create(
        coordinator_id="test",
        queue_size=50,
        capacity=100,
        level=level,
    )

    payload = event.model_dump(mode="json")
    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(payload))

    assert len(errors) == 0, f"Level {level} failed: {[e.message for e in errors]}"


def test_utilization_property():
    """Test Store's utilization computed property."""
    event = FeedbackEvent.create(
        coordinator_id="test",
        queue_size=75,
        capacity=100,
        level=BackpressureLevel.soft,
    )

    assert event.utilization == 0.75

    # Test empty queue
    event_empty = FeedbackEvent.create(
        coordinator_id="test",
        queue_size=0,
        capacity=100,
        level=BackpressureLevel.ok,
    )

    assert event_empty.utilization == 0.0
