"""
Custom exceptions for Market Data Store Client.

Provides structured error handling with retry logic and observability.
"""

from typing import Optional, Dict, Any


class MDSError(Exception):
    """Base exception for all MDS client errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConnectionError(MDSError):
    """Database connection or network errors."""

    pass


class RetryableError(MDSError):
    """Temporary errors that should be retried with backoff."""

    def __init__(
        self,
        message: str,
        retry_after: Optional[float] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.retry_after = retry_after


class ConstraintViolation(MDSError):
    """Database constraint violations (unique, foreign key, etc.)."""

    def __init__(
        self,
        message: str,
        constraint: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.constraint = constraint


class NotFoundError(MDSError):
    """Resource not found errors."""

    pass


class RLSViolation(MDSError):
    """Row Level Security policy violations."""

    def __init__(
        self,
        message: str,
        tenant_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.tenant_id = tenant_id


class TimeoutError(MDSError):
    """Query or connection timeout errors."""

    def __init__(
        self,
        message: str,
        timeout_ms: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, details)
        self.timeout_ms = timeout_ms


class ValidationError(MDSError):
    """Data validation errors before database operations."""

    pass
