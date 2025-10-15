from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable


def default_retry_classifier(exc: Exception) -> bool:
    """Classify retryability. Extend/replace in Phase 4.2B."""
    # Default: optimistic retry for transient-looking errors
    # Check both exception type and message
    exc_type = type(exc).__name__.lower()
    text = str(exc).lower()
    keywords = ("timeout", "temporar", "deadlock", "retry", "busy")
    return any(k in exc_type for k in keywords) or any(k in text for k in keywords)


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff with optional jitter."""

    max_attempts: int = 5
    initial_backoff_ms: int = 50
    max_backoff_ms: int = 2000
    backoff_multiplier: float = 2.0
    jitter: bool = True
    classify_retryable: Callable[[Exception], bool] = default_retry_classifier

    def next_backoff_ms(self, attempt: int) -> int:
        """
        attempt: 1..max_attempts (the attempt you've just failed)
        """
        base = int(self.initial_backoff_ms * (self.backoff_multiplier ** (attempt - 1)))
        base = min(base, self.max_backoff_ms)
        if self.jitter:
            # 50%..100% of calculated backoff
            base = int(base * (0.5 + random.random() * 0.5))
        return max(0, base)


class CircuitOpenError(RuntimeError):
    """Raised when circuit is open and call is denied."""


class CircuitBreaker:
    """Minimal async-friendly circuit breaker."""

    def __init__(self, *, failure_threshold: int = 5, half_open_after_sec: float = 60.0):
        self._threshold = max(1, int(failure_threshold))
        self._timeout = float(half_open_after_sec)
        self._state = "closed"  # closed | open | half_open
        self._failures = 0
        self._last_failure_ts: float | None = None

    @property
    def state(self) -> str:
        return self._state

    async def allow(self) -> None:
        """Check if call is allowed; raises CircuitOpenError if open."""
        now = time.time()
        if self._state == "open":
            if self._last_failure_ts is not None and (now - self._last_failure_ts) >= self._timeout:
                self._state = "half_open"
            else:
                raise CircuitOpenError("circuit is open")

    async def on_success(self) -> None:
        """Record a successful call; closes circuit if half-open."""
        # On half-open success -> close & reset
        self._state = "closed"
        self._failures = 0
        self._last_failure_ts = None

    async def on_failure(self) -> None:
        """Record a failed call; opens circuit if threshold exceeded."""
        self._failures += 1
        self._last_failure_ts = time.time()
        if self._failures >= self._threshold:
            self._state = "open"
