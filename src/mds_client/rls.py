"""
Row Level Security (RLS) helpers for tenant isolation.

Supports both DSN options (cheapest) and context manager (SET LOCAL) approaches.
"""

from typing import Optional
import psycopg
from psycopg_pool import ConnectionPool


def ensure_tenant_in_dsn(dsn: str, tenant_id: Optional[str] = None) -> str:
    """
    Ensure tenant_id is present in DSN options for RLS.

    Args:
        dsn: PostgreSQL connection string
        tenant_id: UUID string for tenant isolation

    Returns:
        DSN with tenant_id in options if not already present
    """
    if "options=" in dsn:
        return dsn

    if tenant_id:
        # Add options=-c app.tenant_id=<uuid>
        sep = "&" if "?" in dsn else "?"
        return f"{dsn}{sep}options=-c%20app.tenant_id%3D{tenant_id}"

    return dsn


class TenantContext:
    """
    Context manager for tenant isolation using SET LOCAL.

    Provides automatic RLS setup for operations that need explicit tenant context.
    """

    def __init__(self, pool: ConnectionPool, tenant_id: str):
        self.pool = pool
        self.tenant_id = tenant_id
        self.conn = None
        self.cur = None

    def __enter__(self):
        """Enter tenant context with SET LOCAL app.tenant_id."""
        self.conn = self.pool.connection().__enter__()
        self.cur = self.conn.cursor().__enter__()
        self.cur.execute("SET LOCAL app.tenant_id = %s", [self.tenant_id])
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit tenant context and clean up connections."""
        if self.cur:
            self.cur.__exit__(exc_type, exc_val, exc_tb)
        if self.conn:
            self.conn.__exit__(exc_type, exc_val, exc_tb)

    def cursor(self):
        """Get the cursor for database operations."""
        return self.cur


def check_tenant_context(conn: psycopg.Connection) -> Optional[str]:
    """
    Check if tenant context is set in the current connection.

    Args:
        conn: PostgreSQL connection

    Returns:
        tenant_id if set, None otherwise
    """
    with conn.cursor() as cur:
        cur.execute("SELECT current_setting('app.tenant_id', true)")
        result = cur.fetchone()
        return result[0] if result and result[0] else None


def set_tenant_context(conn: psycopg.Connection, tenant_id: str) -> None:
    """
    Set tenant context for the current connection.

    Args:
        conn: PostgreSQL connection
        tenant_id: UUID string for tenant isolation
    """
    with conn.cursor() as cur:
        cur.execute("SET LOCAL app.tenant_id = %s", [tenant_id])


def validate_tenant_access(conn: psycopg.Connection, required_tenant_id: str) -> bool:
    """
    Validate that the current connection has access to the required tenant.

    Args:
        conn: PostgreSQL connection
        required_tenant_id: UUID string for required tenant

    Returns:
        True if access is allowed, False otherwise
    """
    current_tenant = check_tenant_context(conn)
    return current_tenant == required_tenant_id
