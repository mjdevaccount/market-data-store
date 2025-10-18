"""
Pulse configuration for event bus integration.

Provides environment-based settings for connecting Store's feedback system
to Core's event bus (inmem or Redis).
"""

import os
from dataclasses import dataclass, field


def _get_enabled() -> bool:
    """Get PULSE_ENABLED from environment."""
    return os.getenv("PULSE_ENABLED", "true").lower() == "true"


def _get_backend() -> str:
    """Get EVENT_BUS_BACKEND from environment."""
    return os.getenv("EVENT_BUS_BACKEND", "inmem")


def _get_redis_url() -> str:
    """Get REDIS_URL from environment."""
    return os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _get_namespace() -> str:
    """Get MD_NAMESPACE from environment."""
    return os.getenv("MD_NAMESPACE", "mdp")


def _get_track() -> str:
    """Get SCHEMA_TRACK from environment."""
    return os.getenv("SCHEMA_TRACK", "v1")


@dataclass(frozen=True)
class PulseConfig:
    """Environment-based configuration for Pulse event bus.

    All settings can be overridden via environment variables:
    - PULSE_ENABLED: Enable/disable Pulse integration (default: true)
    - EVENT_BUS_BACKEND: 'inmem' or 'redis' (default: inmem)
    - REDIS_URL: Redis connection URL (default: redis://localhost:6379/0)
    - MD_NAMESPACE: Namespace prefix for streams (default: mdp)
    - SCHEMA_TRACK: Schema version track (default: v1)

    Example:
        >>> cfg = PulseConfig()
        >>> cfg.enabled
        True
        >>> cfg.backend
        'inmem'
    """

    enabled: bool = field(default_factory=_get_enabled)
    backend: str = field(default_factory=_get_backend)
    redis_url: str = field(default_factory=_get_redis_url)
    ns: str = field(default_factory=_get_namespace)
    track: str = field(default_factory=_get_track)

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.backend not in ("inmem", "redis"):
            raise ValueError(f"Invalid backend: {self.backend}. Must be 'inmem' or 'redis'")
        if not self.ns:
            raise ValueError("MD_NAMESPACE cannot be empty")
        if self.track not in ("v1", "v2"):
            raise ValueError(f"Invalid track: {self.track}. Must be 'v1' or 'v2'")
