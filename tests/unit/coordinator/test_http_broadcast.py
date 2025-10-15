"""
Unit tests for HTTP feedback broadcaster.
"""

import pytest
from unittest.mock import Mock
from market_data_store.coordinator.http_broadcast import HttpFeedbackBroadcaster, HTTPX_AVAILABLE
from market_data_store.coordinator.feedback import FeedbackEvent, BackpressureLevel, feedback_bus


pytestmark = pytest.mark.skipif(not HTTPX_AVAILABLE, reason="httpx not installed")


@pytest.fixture
def fresh_bus():
    """Clear singleton bus subscribers before each test."""
    bus = feedback_bus()
    bus._subs.clear()
    yield bus
    bus._subs.clear()


@pytest.fixture
def event():
    """Sample feedback event."""
    return FeedbackEvent(
        coordinator_id="test",
        queue_size=8000,
        capacity=10000,
        level=BackpressureLevel.HARD,
        reason="test_event",
    )


@pytest.mark.asyncio
async def test_broadcaster_starts_and_stops():
    """HTTP broadcaster can start and stop cleanly."""
    broadcaster = HttpFeedbackBroadcaster(endpoint="http://localhost:9999/feedback", enabled=True)

    await broadcaster.start()
    assert broadcaster._started
    assert broadcaster._client is not None

    await broadcaster.stop()
    assert not broadcaster._started
    assert broadcaster._client is None


@pytest.mark.asyncio
async def test_broadcaster_disabled():
    """Disabled broadcaster doesn't create client."""
    broadcaster = HttpFeedbackBroadcaster(endpoint="http://localhost:9999/feedback", enabled=False)

    await broadcaster.start()
    assert not broadcaster._started
    assert broadcaster._client is None


@pytest.mark.asyncio
async def test_broadcast_success(fresh_bus, event, monkeypatch):
    """Successful broadcast logs and returns."""
    broadcaster = HttpFeedbackBroadcaster(endpoint="http://localhost:9999/feedback", enabled=True)
    await broadcaster.start()

    # Mock successful HTTP response
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "OK"

    async def mock_post(url, json):
        return mock_response

    monkeypatch.setattr(broadcaster._client, "post", mock_post)

    # Broadcast event
    await broadcaster._on_feedback(event)

    # Should succeed without raising
    await broadcaster.stop()


@pytest.mark.asyncio
async def test_broadcast_http_error(fresh_bus, event, monkeypatch):
    """HTTP error status triggers retry."""
    broadcaster = HttpFeedbackBroadcaster(
        endpoint="http://localhost:9999/feedback", max_retries=2, backoff_base=0.01, enabled=True
    )
    await broadcaster.start()

    # Mock error response
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    call_count = {"n": 0}

    async def mock_post(url, json):
        call_count["n"] += 1
        return mock_response

    monkeypatch.setattr(broadcaster._client, "post", mock_post)

    # Broadcast event (should retry)
    await broadcaster._on_feedback(event)

    # Should have attempted max_retries times
    assert call_count["n"] == 2

    await broadcaster.stop()


@pytest.mark.asyncio
async def test_broadcast_network_error(fresh_bus, event, monkeypatch):
    """Network error triggers retry with backoff."""
    broadcaster = HttpFeedbackBroadcaster(
        endpoint="http://localhost:9999/feedback", max_retries=3, backoff_base=0.01, enabled=True
    )
    await broadcaster.start()

    call_count = {"n": 0}

    async def mock_post(url, json):
        call_count["n"] += 1
        raise Exception("Network error")

    monkeypatch.setattr(broadcaster._client, "post", mock_post)

    # Broadcast event (should retry)
    await broadcaster._on_feedback(event)

    # Should have attempted max_retries times
    assert call_count["n"] == 3

    await broadcaster.stop()


@pytest.mark.asyncio
async def test_broadcast_payload_format(fresh_bus, event, monkeypatch):
    """Broadcast sends correct JSON payload."""
    broadcaster = HttpFeedbackBroadcaster(endpoint="http://localhost:9999/feedback", enabled=True)
    await broadcaster.start()

    captured_payload = {}

    async def mock_post(url, json):
        captured_payload.update(json)
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        return mock_response

    monkeypatch.setattr(broadcaster._client, "post", mock_post)

    await broadcaster._on_feedback(event)

    # Verify payload structure
    assert captured_payload["coordinator_id"] == "test"
    assert captured_payload["queue_size"] == 8000
    assert captured_payload["capacity"] == 10000
    assert captured_payload["level"] == "hard"
    assert captured_payload["reason"] == "test_event"
    assert captured_payload["utilization"] == 0.8

    await broadcaster.stop()


@pytest.mark.asyncio
async def test_broadcast_one_manual(fresh_bus, event, monkeypatch):
    """Manual broadcast_one method works."""
    broadcaster = HttpFeedbackBroadcaster(endpoint="http://localhost:9999/feedback", enabled=True)
    await broadcaster.start()

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.text = "OK"

    async def mock_post(url, json):
        return mock_response

    monkeypatch.setattr(broadcaster._client, "post", mock_post)

    # Manual broadcast
    result = await broadcaster.broadcast_one(event)
    assert result is True

    await broadcaster.stop()


@pytest.mark.asyncio
async def test_integration_with_feedback_bus(fresh_bus, event, monkeypatch):
    """Broadcaster integrates with feedback bus."""
    call_count = {"n": 0}

    broadcaster = HttpFeedbackBroadcaster(
        endpoint="http://localhost:9999/feedback", enabled=True, max_retries=1
    )

    # Mock HTTP client to avoid actual network calls
    async def mock_post(url, json):
        call_count["n"] += 1
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        return mock_response

    await broadcaster.start()
    monkeypatch.setattr(broadcaster._client, "post", mock_post)

    # Publish event to bus (broadcaster is subscribed)
    await fresh_bus.publish(event)

    # Broadcaster should have received it and made HTTP call
    assert call_count["n"] == 1

    await broadcaster.stop()


@pytest.mark.asyncio
async def test_broadcaster_unsubscribes_on_stop(fresh_bus):
    """Broadcaster unsubscribes from bus on stop."""
    broadcaster = HttpFeedbackBroadcaster(endpoint="http://localhost:9999/feedback", enabled=True)

    initial_count = fresh_bus.subscriber_count
    await broadcaster.start()
    assert fresh_bus.subscriber_count == initial_count + 1

    await broadcaster.stop()
    assert fresh_bus.subscriber_count == initial_count
