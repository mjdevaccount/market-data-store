"""
Custom exceptions for Market Data Store Client.

Provides structured error handling with retry logic and observability.
"""


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


def map_db_error(e: Exception) -> MDSOperationalError:
    import psycopg
    import psycopg.errors as E

    if isinstance(e, (E.SerializationFailure, E.DeadlockDetected, psycopg.OperationalError)):
        return RetryableError(str(e))
    if isinstance(e, (E.UniqueViolation, E.CheckViolation, E.ForeignKeyViolation)):
        return ConstraintViolation(str(e))
    if "row level security" in str(e).lower() or "app.tenant_id" in str(e):
        return RLSDenied(str(e))
    if isinstance(e, E.QueryCanceled):
        return TimeoutExceeded(str(e))
    return MDSOperationalError(str(e))
