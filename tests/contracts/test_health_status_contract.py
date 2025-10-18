"""
HealthStatus/HealthComponent contract tests.

Validates Store's health endpoints return Core-compatible DTOs.
"""

import time
from market_data_core.telemetry import HealthStatus, HealthComponent


def test_health_status_roundtrip():
    """HealthStatus serializes and deserializes correctly."""
    components = [
        HealthComponent(name="database", state="healthy"),
        HealthComponent(name="coordinator", state="degraded"),
    ]

    health = HealthStatus(
        service="market-data-store",
        state="degraded",
        components=components,
        version="0.4.0",
        ts=time.time(),
    )

    # Roundtrip
    json_str = health.model_dump_json()
    restored = HealthStatus.model_validate_json(json_str)

    assert restored.service == "market-data-store"
    assert restored.state == "degraded"
    assert len(restored.components) == 2
    assert restored.version == "0.4.0"


def test_health_component_states_valid():
    """HealthComponent accepts all Core state enum values."""
    valid_states = ["healthy", "degraded", "unhealthy"]

    for state in valid_states:
        component = HealthComponent(name="test_component", state=state)
        assert component.state == state


def test_health_component_optional_details():
    """HealthComponent supports optional details dict."""
    component = HealthComponent(
        name="queue",
        state="degraded",
        details={"queue_size": "950", "capacity": "1000"},
    )

    assert component.details["queue_size"] == "950"
    assert component.details["capacity"] == "1000"

    # Roundtrip with details
    json_str = component.model_dump_json()
    restored = HealthComponent.model_validate_json(json_str)

    assert restored.details == component.details
