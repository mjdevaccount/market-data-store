"""
Environment-configurable runtime settings for the write coordinator.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class CoordinatorRuntimeSettings(BaseSettings):
    """Environment-configurable defaults for the write coordinator."""

    coordinator_capacity: int = Field(10_000, description="Queue capacity")
    coordinator_workers: int = Field(4, description="Number of worker tasks")
    coordinator_batch_size: int = Field(500, description="Max batch size per flush")
    coordinator_flush_interval: float = Field(0.25, description="Seconds between flushes")

    # Retry policy
    retry_max_attempts: int = Field(5, description="Max retry attempts")
    retry_initial_backoff_ms: int = Field(50, description="Initial backoff (ms)")
    retry_max_backoff_ms: int = Field(2_000, description="Max backoff cap (ms)")
    retry_backoff_multiplier: float = Field(2.0, description="Exponential multiplier")
    retry_jitter: bool = Field(True, description="Enable jitter")

    # Circuit breaker
    cb_failure_threshold: int = Field(5, description="Failures before opening")
    cb_half_open_after_sec: float = Field(60.0, description="Open -> half-open after N sec")

    # Metrics polling
    metrics_queue_poll_sec: float = Field(0.25, description="Gauge update period")

    class Config:
        env_prefix = "MDS_"
        env_file = ".env"


class FeedbackSettings(BaseSettings):
    """Environment-configurable settings for backpressure feedback system."""

    # Core feedback
    enable_feedback: bool = Field(True, description="Enable feedback system globally")

    # HTTP broadcasting
    enable_http_broadcast: bool = Field(False, description="Enable HTTP feedback broadcasting")
    http_endpoint: str | None = Field(None, description="HTTP endpoint URL for feedback events")
    http_timeout: float = Field(2.5, description="HTTP request timeout (seconds)")
    http_max_retries: int = Field(3, description="Max HTTP retry attempts")
    http_backoff: float = Field(0.5, description="HTTP retry backoff base (seconds)")

    class Config:
        env_prefix = "MDS_FB_"
        env_file = ".env"
