"""
Market Data Store Client - Core API for Market Data Core.

Provides sync (MDS) facade with connection pooling, RLS, and error mapping.
"""

import psycopg
from psycopg_pool import ConnectionPool
from typing import TypedDict

from .models import Bar, Fundamentals, News, OptionSnap, LatestPrice
from .sql import SQL
from .rls import ensure_tenant_in_dsn, TenantContext
from .errors import map_db_error


class MDSConfig(TypedDict, total=False):
    """Configuration for Market Data Store Client."""

    dsn: str
    tenant_id: str
    app_name: str
    connect_timeout: float
    statement_timeout_ms: int
    pool_min: int
    pool_max: int
    max_batch_rows: int
    max_batch_ms: int


class MDS:
    """Synchronous Market Data Store Client."""

    def __init__(self, cfg: MDSConfig):
        dsn = cfg["dsn"]
        if cfg.get("app_name"):
            sep = "&" if "?" in dsn else "?"
            dsn = f"{dsn}{sep}application_name={cfg['app_name']}"
        dsn = ensure_tenant_in_dsn(dsn, cfg.get("tenant_id"))
        self.pool = ConnectionPool(
            dsn, min_size=cfg.get("pool_min", 1), max_size=cfg.get("pool_max", 8)
        )
        self.statement_timeout_ms = cfg.get("statement_timeout_ms", 0)

    def _apply_timeouts(self, conn: psycopg.Connection):
        if self.statement_timeout_ms:
            conn.execute(f"SET statement_timeout = {self.statement_timeout_ms};")

    def tenant(self, tenant_id: str) -> TenantContext:
        return TenantContext(self.pool, tenant_id)

    def health(self) -> dict:
        try:
            with self.pool.connection() as c, c.cursor() as cur:
                self._apply_timeouts(c)
                cur.execute("SELECT 1")
                return {"ok": True}
        except Exception as e:
            raise map_db_error(e)

    def schema_version(self) -> str:
        try:
            with self.pool.connection() as c, c.cursor() as cur:
                self._apply_timeouts(c)
                cur.execute(
                    "SELECT COALESCE(MAX(version_num::text),'unknown') FROM alembic_version"
                )
                return cur.fetchone()[0]
        except Exception as e:
            raise map_db_error(e)

    # ---------- writes
    def upsert_bars(self, rows: list[Bar]) -> int:
        if not rows:
            return 0
        try:
            with self.pool.connection() as c, c.cursor() as cur:
                self._apply_timeouts(c)
                cur.execute("SELECT current_setting('app.tenant_id', true)")
                if not cur.fetchone()[0]:
                    cur.execute("SET LOCAL app.tenant_id = %s", [rows[0].tenant_id])
                cur.executemany(SQL.UPSERT_BARS, [SQL.bar_params(r) for r in rows])
                c.commit()
                return cur.rowcount
        except Exception as e:
            raise map_db_error(e)

    def upsert_fundamentals(self, rows: list[Fundamentals]) -> int:
        if not rows:
            return 0
        try:
            with self.pool.connection() as c, c.cursor() as cur:
                self._apply_timeouts(c)
                cur.execute("SELECT current_setting('app.tenant_id', true)")
                if not cur.fetchone()[0]:
                    cur.execute("SET LOCAL app.tenant_id = %s", [rows[0].tenant_id])
                cur.executemany(SQL.UPSERT_FUNDAMENTALS, [SQL.fund_params(r) for r in rows])
                c.commit()
                return cur.rowcount
        except Exception as e:
            raise map_db_error(e)

    def upsert_news(self, rows: list[News]) -> int:
        if not rows:
            return 0
        try:
            with self.pool.connection() as c, c.cursor() as cur:
                self._apply_timeouts(c)
                cur.execute("SELECT current_setting('app.tenant_id', true)")
                if not cur.fetchone()[0]:
                    cur.execute("SET LOCAL app.tenant_id = %s", [rows[0].tenant_id])
                cur.executemany(SQL.UPSERT_NEWS, [SQL.news_params(r) for r in rows])
                c.commit()
                return cur.rowcount
        except Exception as e:
            raise map_db_error(e)

    def upsert_options(self, rows: list[OptionSnap]) -> int:
        if not rows:
            return 0
        try:
            with self.pool.connection() as c, c.cursor() as cur:
                self._apply_timeouts(c)
                cur.execute("SELECT current_setting('app.tenant_id', true)")
                if not cur.fetchone()[0]:
                    cur.execute("SET LOCAL app.tenant_id = %s", [rows[0].tenant_id])
                cur.executemany(SQL.UPSERT_OPTIONS, [SQL.opt_params(r) for r in rows])
                c.commit()
                return cur.rowcount
        except Exception as e:
            raise map_db_error(e)

    # ---------- reads
    def latest_prices(self, symbols: list[str], vendor: str) -> list[LatestPrice]:
        if not symbols:
            return []
        try:
            with self.pool.connection() as c, c.cursor() as cur:
                self._apply_timeouts(c)
                cur.execute(SQL.LATEST_PRICES, (vendor, symbols))
                return [
                    LatestPrice(
                        tenant_id=r[0], vendor=r[1], symbol=r[2], price=r[3], price_timestamp=r[4]
                    )
                    for r in cur.fetchall()
                ]
        except Exception as e:
            raise map_db_error(e)

    def bars_window(self, symbol: str, timeframe: str, start, end, vendor: str) -> list[Bar]:
        try:
            with self.pool.connection() as c, c.cursor() as cur:
                self._apply_timeouts(c)
                # rely on DSN options for tenant; caller must ensure it
                cur.execute("SELECT current_setting('app.tenant_id', true)")
                tenant = cur.fetchone()[0]
                cur.execute(
                    SQL.BARS_WINDOW, (tenant, vendor, symbol.upper(), timeframe, start, end)
                )
                return [
                    Bar(
                        **{
                            "ts": r[0],
                            "tenant_id": r[1],
                            "vendor": r[2],
                            "symbol": r[3],
                            "timeframe": r[4],
                            "open_price": r[5],
                            "high_price": r[6],
                            "low_price": r[7],
                            "close_price": r[8],
                            "volume": r[9],
                            "id": r[10],
                        }
                    )
                    for r in cur.fetchall()
                ]
        except Exception as e:
            raise map_db_error(e)

    def enqueue_job(
        self, idempotency_key: str, job_type: str, payload: dict, priority: str = "medium"
    ) -> int:
        """Enqueue job in outbox with idempotency."""
        try:
            with self.pool.connection() as c, c.cursor() as cur:
                self._apply_timeouts(c)
                cur.execute("SELECT current_setting('app.tenant_id', true)")
                tenant = cur.fetchone()[0]
                if not tenant:
                    raise map_db_error(Exception("No tenant context set"))

                cur.execute(
                    "INSERT INTO jobs_outbox(tenant_id, idempotency_key, job_type, payload, priority) "
                    "VALUES (%s, %s, %s, %s::jsonb, %s) ON CONFLICT (idempotency_key) DO NOTHING "
                    "RETURNING id",
                    (tenant, idempotency_key, job_type, payload, priority),
                )
                result = cur.fetchone()
                c.commit()
                return result[0] if result else 0
        except Exception as e:
            raise map_db_error(e)
