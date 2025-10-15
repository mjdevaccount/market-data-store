"""
Unit tests for RetryPolicy.
"""

from market_data_store.coordinator import RetryPolicy, default_retry_classifier


def test_default_retry_classifier():
    """Test that default classifier recognizes transient errors."""
    assert default_retry_classifier(TimeoutError("socket timeout"))
    assert default_retry_classifier(Exception("Temporary failure"))
    assert default_retry_classifier(Exception("Database busy, please retry"))
    assert not default_retry_classifier(Exception("permission denied"))
    assert not default_retry_classifier(ValueError("invalid argument"))


def test_backoff_curve_monotonic_with_cap():
    """Test exponential backoff with max cap."""
    rp = RetryPolicy(
        initial_backoff_ms=50,
        max_backoff_ms=200,
        backoff_multiplier=2.0,
        jitter=False,
    )
    vals = [rp.next_backoff_ms(i) for i in range(1, 10)]
    # 50, 100, 200, 200, 200...
    assert vals[:3] == [50, 100, 200]
    assert all(v <= 200 for v in vals)


def test_backoff_with_jitter():
    """Test that jitter produces values in expected range."""
    rp = RetryPolicy(initial_backoff_ms=100, max_backoff_ms=1000, jitter=True)
    # With jitter, values should be 50-100% of calculated
    vals = [rp.next_backoff_ms(1) for _ in range(20)]
    assert all(50 <= v <= 100 for v in vals)


def test_custom_classifier():
    """Test custom error classifier."""

    def always_retry(exc: Exception) -> bool:
        return True

    rp = RetryPolicy(classify_retryable=always_retry)
    assert rp.classify_retryable(Exception("anything"))
    assert rp.classify_retryable(ValueError("anything"))
