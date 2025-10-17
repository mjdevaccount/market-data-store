"""
Integration tests for health endpoint contract compliance.

Validates that health endpoints return Core v1.1.0 HealthStatus DTOs.
"""

import pytest
from fastapi.testclient import TestClient
from market_data_core.telemetry import HealthStatus


@pytest.fixture
def client():
    """Create FastAPI test client."""
    from datastore.service.app import app

    return TestClient(app)


def test_healthz_returns_health_status(client):
    """GET /healthz returns Core HealthStatus schema."""
    response = client.get("/healthz")

    assert response.status_code == 200

    # Parse as Core DTO
    health = HealthStatus.model_validate(response.json())

    assert health.service == "market-data-store"
    assert health.state in ("healthy", "degraded")
    assert len(health.components) > 0
    assert health.version == "0.4.0"
    assert isinstance(health.ts, float)


def test_healthz_components_present(client):
    """Health endpoint includes component breakdown."""
    response = client.get("/healthz")

    assert response.status_code == 200

    health = HealthStatus.model_validate(response.json())

    # Should have database and prometheus components
    component_names = [c.name for c in health.components]
    assert "database" in component_names
    assert "prometheus" in component_names


def test_readyz_returns_health_status_on_success(client):
    """GET /readyz returns Core HealthStatus schema when ready."""
    response = client.get("/readyz")

    # May be 200 or 503 depending on DB connectivity
    if response.status_code == 200:
        health = HealthStatus.model_validate(response.json())
        assert health.state == "healthy"
        assert health.service == "market-data-store"
        assert health.version == "0.4.0"


def test_readyz_returns_503_on_failure(client, monkeypatch):
    """Readiness check returns 503 when database fails."""

    # Mock database connection to fail
    def mock_create_engine(*args, **kwargs):
        raise Exception("DB connection failed")

    monkeypatch.setattr("sqlalchemy.create_engine", mock_create_engine)

    response = client.get("/readyz")

    assert response.status_code == 503
    assert "not ready" in response.json()["detail"].lower()


def test_health_backward_compatible(client):
    """Health response is backward compatible with old consumers.

    Old consumers expecting {"ok": True} can still function,
    though they'll ignore extra fields.
    """
    response = client.get("/healthz")

    assert response.status_code == 200

    # JSON contains the structured data
    data = response.json()

    # Has Core fields
    assert "service" in data
    assert "state" in data
    assert "components" in data
    assert "version" in data
    assert "ts" in data

    # Old consumers can parse it (extra fields ignored)
    # This is forward-compatible by design


def test_health_component_state_values(client):
    """Component states use valid Core enum values."""
    response = client.get("/healthz")

    assert response.status_code == 200

    health = HealthStatus.model_validate(response.json())

    # All component states should be valid
    valid_states = {"healthy", "degraded", "unhealthy"}
    for component in health.components:
        assert component.state in valid_states


def test_health_json_schema_valid(client):
    """Health response matches Pydantic schema exactly."""
    response = client.get("/healthz")

    assert response.status_code == 200

    # Validate against Core DTO schema
    try:
        health = HealthStatus.model_validate(response.json())
        # If this passes, schema is correct
        assert health.service == "market-data-store"
    except Exception as e:
        pytest.fail(f"Schema validation failed: {e}")


def test_health_timestamp_reasonable(client):
    """Health timestamp is current time."""
    import time

    before = time.time()
    response = client.get("/healthz")
    after = time.time()

    assert response.status_code == 200

    health = HealthStatus.model_validate(response.json())

    # Timestamp should be between request start and end
    assert before <= health.ts <= after


def test_multiple_health_checks_consistent(client):
    """Multiple health checks return consistent structure."""
    responses = [client.get("/healthz") for _ in range(3)]

    for response in responses:
        assert response.status_code == 200
        health = HealthStatus.model_validate(response.json())
        assert health.service == "market-data-store"
        assert len(health.components) >= 2  # At least db + prometheus
