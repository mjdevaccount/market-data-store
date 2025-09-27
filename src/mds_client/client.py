"""
Market Data Store Client - Core API for Market Data Core.

Provides both sync (MDS) and async (AMDS) facades with connection pooling,
RLS, retries, and observability hooks.
"""

import psycopg
from psycopg_pool import ConnectionPool
from psycopg_pool import AsyncConnectionPool
from typing import Optional, List, Dict, Any, Union
from datetime import datetime

from .models import Bar, Fundamentals, News, OptionSnap, LatestPrice
from .sql import SQL
from .rls import ensure_tenant_in_dsn, TenantContext, check_tenant_context, set_tenant_context
from .errors import (
    MDSError,
    ConnectionError,
    ValidationError,
)
from .utils import format_dsn_with_tenant


class MDSConfig:
    """Configuration for Market Data Store Client."""

    def __init__(
        self,
        dsn: str,
        tenant_id: Optional[str] = None,
        app_name: Optional[str] = None,
        connect_timeout: float = 10.0,
        statement_timeout_ms: int = 30000,
        pool_min: int = 1,
        pool_max: int = 8,
        max_batch_rows: int = 1000,
        max_batch_bytes: int = 1024 * 1024,  # 1MB
        max_batch_ms: int = 5000,  # 5 seconds
    ):
        self.dsn = dsn
        self.tenant_id = tenant_id
        self.app_name = app_name
        self.connect_timeout = connect_timeout
        self.statement_timeout_ms = statement_timeout_ms
        self.pool_min = pool_min
        self.pool_max = pool_max
        self.max_batch_rows = max_batch_rows
        self.max_batch_bytes = max_batch_bytes
        self.max_batch_ms = max_batch_ms


class MDS:
    """Synchronous Market Data Store Client."""

    def __init__(self, config: Union[MDSConfig, Dict[str, Any]]):
        if isinstance(config, dict):
            config = MDSConfig(**config)

        # Ensure tenant_id is in DSN for RLS
        dsn = ensure_tenant_in_dsn(config.dsn, config.tenant_id)
        if config.app_name:
            dsn = format_dsn_with_tenant(dsn, config.tenant_id or "", config.app_name)

        self.config = config
        self.pool = ConnectionPool(
            dsn, min_size=config.pool_min, max_size=config.pool_max, kwargs={"autocommit": False}
        )

    def _apply_timeouts(self, conn: psycopg.Connection) -> None:
        """Apply statement timeout to connection."""
        if self.config.statement_timeout_ms > 0:
            conn.execute(f"SET statement_timeout = {self.config.statement_timeout_ms};")

    def _ensure_tenant_context(self, conn: psycopg.Connection, tenant_id: str) -> None:
        """Ensure tenant context is set for RLS."""
        current_tenant = check_tenant_context(conn)
        if not current_tenant:
            set_tenant_context(conn, tenant_id)

    def health(self) -> Dict[str, Any]:
        """Check database health."""
        try:
            with self.pool.connection() as conn, conn.cursor() as cur:
                self._apply_timeouts(conn)
                cur.execute("SELECT 1")
                return {"ok": True, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            raise ConnectionError(f"Health check failed: {e}")

    def schema_version(self) -> str:
        """Get current schema version."""
        try:
            with self.pool.connection() as conn, conn.cursor() as cur:
                self._apply_timeouts(conn)
                cur.execute(
                    "SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1"
                )
                result = cur.fetchone()
                return result[0] if result else "unknown"
        except Exception:
            return "unknown"

    def tenant(self, tenant_id: str) -> TenantContext:
        """Get tenant context for RLS operations."""
        return TenantContext(self.pool, tenant_id)

    # ---------- Write Operations

    def upsert_bars(self, rows: List[Bar]) -> int:
        """Upsert bars data with conflict resolution."""
        if not rows:
            return 0

        try:
            with self.pool.connection() as conn, conn.cursor() as cur:
                self._apply_timeouts(conn)
                self._ensure_tenant_context(conn, rows[0].tenant_id)

                cur.executemany(SQL.UPSERT_BARS, [SQL.bar_params(r) for r in rows])
                conn.commit()
                return cur.rowcount
        except Exception as e:
            raise MDSError(f"Failed to upsert bars: {e}")

    def upsert_fundamentals(self, rows: List[Fundamentals]) -> int:
        """Upsert fundamentals data with conflict resolution."""
        if not rows:
            return 0

        try:
            with self.pool.connection() as conn, conn.cursor() as cur:
                self._apply_timeouts(conn)
                self._ensure_tenant_context(conn, rows[0].tenant_id)

                cur.executemany(SQL.UPSERT_FUNDAMENTALS, [SQL.fund_params(r) for r in rows])
                conn.commit()
                return cur.rowcount
        except Exception as e:
            raise MDSError(f"Failed to upsert fundamentals: {e}")

    def upsert_news(self, rows: List[News]) -> int:
        """Upsert news data with conflict resolution."""
        if not rows:
            return 0

        try:
            with self.pool.connection() as conn, conn.cursor() as cur:
                self._apply_timeouts(conn)
                self._ensure_tenant_context(conn, rows[0].tenant_id)

                cur.executemany(SQL.UPSERT_NEWS, [SQL.news_params(r) for r in rows])
                conn.commit()
                return cur.rowcount
        except Exception as e:
            raise MDSError(f"Failed to upsert news: {e}")

    def upsert_options(self, rows: List[OptionSnap]) -> int:
        """Upsert options data with conflict resolution."""
        if not rows:
            return 0

        try:
            with self.pool.connection() as conn, conn.cursor() as cur:
                self._apply_timeouts(conn)
                self._ensure_tenant_context(conn, rows[0].tenant_id)

                cur.executemany(SQL.UPSERT_OPTIONS, [SQL.opt_params(r) for r in rows])
                conn.commit()
                return cur.rowcount
        except Exception as e:
            raise MDSError(f"Failed to upsert options: {e}")

    # ---------- Read Operations

    def latest_prices(self, symbols: List[str], vendor: str) -> List[LatestPrice]:
        """Get latest prices for symbols from vendor."""
        if not symbols:
            return []

        try:
            with self.pool.connection() as conn, conn.cursor() as cur:
                self._apply_timeouts(conn)

                cur.execute(SQL.LATEST_PRICES, (vendor, symbols))
                rows = cur.fetchall()

                return [
                    LatestPrice(
                        tenant_id=r[0], vendor=r[1], symbol=r[2], price=r[3], price_timestamp=r[4]
                    )
                    for r in rows
                ]
        except Exception as e:
            raise MDSError(f"Failed to get latest prices: {e}")

    def bars_window(
        self,
        symbol: str,
        timeframe: str,
        start: Union[datetime, str],
        end: Union[datetime, str],
        vendor: str,
    ) -> List[Bar]:
        """Get bars for symbol in time window."""
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        if isinstance(end, str):
            end = datetime.fromisoformat(end)

        try:
            with self.pool.connection() as conn, conn.cursor() as cur:
                self._apply_timeouts(conn)

                cur.execute(
                    SQL.BARS_WINDOW, (self.config.tenant_id, vendor, symbol, timeframe, start, end)
                )
                rows = cur.fetchall()

                return [
                    Bar(
                        ts=r[0],
                        tenant_id=r[1],
                        vendor=r[2],
                        symbol=r[3],
                        timeframe=r[4],
                        open_price=r[5],
                        high_price=r[6],
                        low_price=r[7],
                        close_price=r[8],
                        volume=r[9],
                        id=r[10],
                    )
                    for r in rows
                ]
        except Exception as e:
            raise MDSError(f"Failed to get bars window: {e}")

    # ---------- Job Queue Operations

    def enqueue_job(
        self, idempotency_key: str, job_type: str, payload: Dict[str, Any], priority: str = "medium"
    ) -> int:
        """Enqueue job in outbox with idempotency."""
        if not self.config.tenant_id:
            raise ValidationError("tenant_id required for job operations")

        try:
            with self.pool.connection() as conn, conn.cursor() as cur:
                self._apply_timeouts(conn)
                self._ensure_tenant_context(conn, self.config.tenant_id)

                cur.execute(
                    SQL.ENQUEUE_JOB,
                    SQL.job_params(
                        self.config.tenant_id, idempotency_key, job_type, payload, priority
                    ),
                )
                result = cur.fetchone()
                conn.commit()

                return result[0] if result else 0
        except Exception as e:
            raise MDSError(f"Failed to enqueue job: {e}")


class AMDS:
    """Asynchronous Market Data Store Client."""

    def __init__(self, config: Union[MDSConfig, Dict[str, Any]]):
        if isinstance(config, dict):
            config = MDSConfig(**config)

        # Ensure tenant_id is in DSN for RLS
        dsn = ensure_tenant_in_dsn(config.dsn, config.tenant_id)
        if config.app_name:
            dsn = format_dsn_with_tenant(dsn, config.tenant_id or "", config.app_name)

        self.config = config
        self.pool = AsyncConnectionPool(
            dsn, min_size=config.pool_min, max_size=config.pool_max, kwargs={"autocommit": False}
        )

    async def _apply_timeouts(self, conn: psycopg.AsyncConnection) -> None:
        """Apply statement timeout to connection."""
        if self.config.statement_timeout_ms > 0:
            await conn.execute(f"SET statement_timeout = {self.config.statement_timeout_ms};")

    async def _ensure_tenant_context(self, conn: psycopg.AsyncConnection, tenant_id: str) -> None:
        """Ensure tenant context is set for RLS."""
        async with conn.cursor() as cur:
            await cur.execute("SELECT current_setting('app.tenant_id', true)")
            result = await cur.fetchone()
            if not result or not result[0]:
                await cur.execute("SET LOCAL app.tenant_id = %s", [tenant_id])

    async def health(self) -> Dict[str, Any]:
        """Check database health."""
        try:
            async with self.pool.connection() as conn, conn.cursor() as cur:
                await self._apply_timeouts(conn)
                await cur.execute("SELECT 1")
                return {"ok": True, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            raise ConnectionError(f"Health check failed: {e}")

    async def schema_version(self) -> str:
        """Get current schema version."""
        try:
            async with self.pool.connection() as conn, conn.cursor() as cur:
                await self._apply_timeouts(conn)
                await cur.execute(
                    "SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1"
                )
                result = await cur.fetchone()
                return result[0] if result else "unknown"
        except Exception:
            return "unknown"

    # ---------- Write Operations (Async)

    async def upsert_bars(self, rows: List[Bar]) -> int:
        """Upsert bars data with conflict resolution."""
        if not rows:
            return 0

        try:
            async with self.pool.connection() as conn, conn.cursor() as cur:
                await self._apply_timeouts(conn)
                await self._ensure_tenant_context(conn, rows[0].tenant_id)

                await cur.executemany(SQL.UPSERT_BARS, [SQL.bar_params(r) for r in rows])
                await conn.commit()
                return cur.rowcount
        except Exception as e:
            raise MDSError(f"Failed to upsert bars: {e}")

    async def upsert_fundamentals(self, rows: List[Fundamentals]) -> int:
        """Upsert fundamentals data with conflict resolution."""
        if not rows:
            return 0

        try:
            async with self.pool.connection() as conn, conn.cursor() as cur:
                await self._apply_timeouts(conn)
                await self._ensure_tenant_context(conn, rows[0].tenant_id)

                await cur.executemany(SQL.UPSERT_FUNDAMENTALS, [SQL.fund_params(r) for r in rows])
                await conn.commit()
                return cur.rowcount
        except Exception as e:
            raise MDSError(f"Failed to upsert fundamentals: {e}")

    async def upsert_news(self, rows: List[News]) -> int:
        """Upsert news data with conflict resolution."""
        if not rows:
            return 0

        try:
            async with self.pool.connection() as conn, conn.cursor() as cur:
                await self._apply_timeouts(conn)
                await self._ensure_tenant_context(conn, rows[0].tenant_id)

                await cur.executemany(SQL.UPSERT_NEWS, [SQL.news_params(r) for r in rows])
                await conn.commit()
                return cur.rowcount
        except Exception as e:
            raise MDSError(f"Failed to upsert news: {e}")

    async def upsert_options(self, rows: List[OptionSnap]) -> int:
        """Upsert options data with conflict resolution."""
        if not rows:
            return 0

        try:
            async with self.pool.connection() as conn, conn.cursor() as cur:
                await self._apply_timeouts(conn)
                await self._ensure_tenant_context(conn, rows[0].tenant_id)

                await cur.executemany(SQL.UPSERT_OPTIONS, [SQL.opt_params(r) for r in rows])
                await conn.commit()
                return cur.rowcount
        except Exception as e:
            raise MDSError(f"Failed to upsert options: {e}")

    # ---------- Read Operations (Async)

    async def latest_prices(self, symbols: List[str], vendor: str) -> List[LatestPrice]:
        """Get latest prices for symbols from vendor."""
        if not symbols:
            return []

        try:
            async with self.pool.connection() as conn, conn.cursor() as cur:
                await self._apply_timeouts(conn)

                await cur.execute(SQL.LATEST_PRICES, (vendor, symbols))
                rows = await cur.fetchall()

                return [
                    LatestPrice(
                        tenant_id=r[0], vendor=r[1], symbol=r[2], price=r[3], price_timestamp=r[4]
                    )
                    for r in rows
                ]
        except Exception as e:
            raise MDSError(f"Failed to get latest prices: {e}")

    async def bars_window(
        self,
        symbol: str,
        timeframe: str,
        start: Union[datetime, str],
        end: Union[datetime, str],
        vendor: str,
    ) -> List[Bar]:
        """Get bars for symbol in time window."""
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        if isinstance(end, str):
            end = datetime.fromisoformat(end)

        try:
            async with self.pool.connection() as conn, conn.cursor() as cur:
                await self._apply_timeouts(conn)

                await cur.execute(
                    SQL.BARS_WINDOW, (self.config.tenant_id, vendor, symbol, timeframe, start, end)
                )
                rows = await cur.fetchall()

                return [
                    Bar(
                        ts=r[0],
                        tenant_id=r[1],
                        vendor=r[2],
                        symbol=r[3],
                        timeframe=r[4],
                        open_price=r[5],
                        high_price=r[6],
                        low_price=r[7],
                        close_price=r[8],
                        volume=r[9],
                        id=r[10],
                    )
                    for r in rows
                ]
        except Exception as e:
            raise MDSError(f"Failed to get bars window: {e}")

    # ---------- Job Queue Operations (Async)

    async def enqueue_job(
        self, idempotency_key: str, job_type: str, payload: Dict[str, Any], priority: str = "medium"
    ) -> int:
        """Enqueue job in outbox with idempotency."""
        if not self.config.tenant_id:
            raise ValidationError("tenant_id required for job operations")

        try:
            async with self.pool.connection() as conn, conn.cursor() as cur:
                await self._apply_timeouts(conn)
                await self._ensure_tenant_context(conn, self.config.tenant_id)

                await cur.execute(
                    SQL.ENQUEUE_JOB,
                    SQL.job_params(
                        self.config.tenant_id, idempotency_key, job_type, payload, priority
                    ),
                )
                result = await cur.fetchone()
                await conn.commit()

                return result[0] if result else 0
        except Exception as e:
            raise MDSError(f"Failed to enqueue job: {e}")
