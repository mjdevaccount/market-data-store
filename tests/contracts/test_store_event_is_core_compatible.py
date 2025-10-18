"""
Store→Core FeedbackEvent compatibility contract tests.

Validates that Store's extended FeedbackEvent can be consumed by Core-only
systems without breaking. This is critical for cross-repo integration where
Core consumers (like Pipeline's RateCoordinator) need to process Store events.
"""

import time
from market_data_core.telemetry import (
    FeedbackEvent as CoreFeedbackEvent,
    BackpressureLevel,
)
from market_data_store.coordinator import FeedbackEvent as StoreFeedbackEvent


def test_store_feedback_extends_core():
    """Store FeedbackEvent is-a Core FeedbackEvent (inheritance contract)."""
    assert issubclass(StoreFeedbackEvent, CoreFeedbackEvent)


def test_core_can_deserialize_store_json():
    """
    Core consumers can parse Store event JSON (ignore extra fields).

    This is the critical cross-repo contract: Store events must be
    backward-compatible with Core's schema.
    """
    # Store creates event with Store-specific 'reason' field
    store_event = StoreFeedbackEvent.create(
        coordinator_id="bars_coordinator",
        queue_size=850,
        capacity=1000,
        level=BackpressureLevel.hard,
        reason="high_watermark_triggered",  # Store-specific extension
    )

    # Serialize as Store would send it
    json_payload = store_event.model_dump_json()

    # Core consumer deserializes (Pydantic ignores unknown 'reason' field)
    core_event = CoreFeedbackEvent.model_validate_json(json_payload)

    # Core sees all required fields correctly
    assert core_event.coordinator_id == "bars_coordinator"
    assert core_event.queue_size == 850
    assert core_event.capacity == 1000
    assert core_event.level == BackpressureLevel.hard
    assert core_event.source == "store"
    assert isinstance(core_event.ts, float)

    # Extra 'reason' field is silently ignored by Core
    assert not hasattr(core_event, "reason")


def test_store_to_core_dict_compatibility():
    """Store event dict can be validated by Core (dict → Core)."""
    store_event = StoreFeedbackEvent.create(
        coordinator_id="options_coord",
        queue_size=500,
        capacity=1000,
        level=BackpressureLevel.soft,
        reason="circuit_breaker_soft",
    )

    # Store serializes to dict
    event_dict = store_event.model_dump()

    # Core can validate the dict (extra fields ignored)
    core_event = CoreFeedbackEvent.model_validate(event_dict)

    assert core_event.coordinator_id == "options_coord"
    assert core_event.level == BackpressureLevel.soft


def test_backpressure_level_enum_stable():
    """BackpressureLevel enum values are stable (breaking change detector)."""
    # These values are part of the contract — changing them breaks all repos
    assert BackpressureLevel.ok.value == "ok"
    assert BackpressureLevel.soft.value == "soft"
    assert BackpressureLevel.hard.value == "hard"


def test_store_factory_provides_core_required_fields():
    """Store's factory method auto-fills all Core-required fields."""
    before = time.time()

    event = StoreFeedbackEvent.create(
        coordinator_id="test_coord",
        queue_size=100,
        capacity=1000,
        level=BackpressureLevel.ok,
    )

    after = time.time()

    # Core-required 'ts' field auto-filled
    assert before <= event.ts <= after

    # Core-required 'source' field auto-filled
    assert event.source == "store"

    # Store-optional 'reason' defaults to None
    assert event.reason is None


def test_store_event_isinstance_core():
    """Store event passes isinstance checks for Core type."""
    store_event = StoreFeedbackEvent.create(
        coordinator_id="test",
        queue_size=50,
        capacity=100,
        level=BackpressureLevel.ok,
    )

    # Type compatibility for duck typing / isinstance checks
    assert isinstance(store_event, CoreFeedbackEvent)
    assert isinstance(store_event, StoreFeedbackEvent)
