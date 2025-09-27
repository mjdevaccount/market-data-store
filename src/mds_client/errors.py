"""
Custom exceptions for Market Data Store Client.

Provides structured error handling with retry logic and observability.
"""

from psycopg import errors as pgerr


class MDSOperationalError(Exception):
    """Base operational error for MDS client."""

    pass


class RetryableError(MDSOperationalError):
    """Temporary errors that should be retried with backoff."""

    pass


class ConstraintViolation(MDSOperationalError):
    """Database constraint violations (unique, foreign key, etc.)."""

    pass


class RLSDenied(MDSOperationalError):
    """Row Level Security policy violations."""

    pass


class TimeoutExceeded(MDSOperationalError):
    """Query or connection timeout errors."""

    pass


def map_db_error(e: Exception) -> Exception:
    # retryable
    if isinstance(e, (pgerr.DeadlockDetected, pgerr.SerializationFailure, pgerr.AdminShutdown)):
        return RetryableError(str(e))
    # rls
    if isinstance(e, pgerr.InsufficientPrivilege):
        return RLSDenied(str(e))
    # timeouts
    if isinstance(e, pgerr.QueryCanceled):
        return TimeoutExceeded(str(e))
    # uniques / FK
    if isinstance(e, (pgerr.UniqueViolation, pgerr.ForeignKeyViolation, pgerr.CheckViolation)):
        return ConstraintViolation(str(e))
    return MDSOperationalError(str(e))
