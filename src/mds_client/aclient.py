"""
Async Market Data Store Client - Core API for Market Data Core.

Provides async (AMDS) facade with connection pooling, RLS, and error mapping.
"""

import psycopg
from psycopg_pool import AsyncConnectionPool
from typing import TypedDict

from .models import Bar, Fundamentals, News, OptionSnap, LatestPrice
from .sql import SQL
from .rls import ensure_tenant_in_dsn, AsyncTenantContext
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


class AMDS:
    """Asynchronous Market Data Store Client."""

    def __init__(self, cfg: MDSConfig):
        dsn = cfg["dsn"]
        if cfg.get("app_name"):
            sep = "&" if "?" in dsn else "?"
            dsn = f"{dsn}{sep}application_name={cfg['app_name']}"
        dsn = ensure_tenant_in_dsn(dsn, cfg.get("tenant_id"))
        self.pool = AsyncConnectionPool(
            dsn, min_size=cfg.get("pool_min", 1), max_size=cfg.get("pool_max", 8)
        )
        self.statement_timeout_ms = cfg.get("statement_timeout_ms", 0)

    async def _apply_timeouts(self, conn: psycopg.AsyncConnection):
        if self.statement_timeout_ms:
            await conn.execute(f"SET statement_timeout = {self.statement_timeout_ms};")

    def tenant(self, tenant_id: str) -> AsyncTenantContext:
        return AsyncTenantContext(self.pool, tenant_id)

    async def health(self) -> dict:
        try:
            async with self.pool.connection() as c, c.cursor() as cur:
                await self._apply_timeouts(c)
                await cur.execute("SELECT 1")
                return {"ok": True}
        except Exception as e:
            raise map_db_error(e)

    async def schema_version(self) -> str:
        try:
            async with self.pool.connection() as c, c.cursor() as cur:
                await self._apply_timeouts(c)
                await cur.execute(
                    "SELECT COALESCE(MAX(version_num::text),'unknown') FROM alembic_version"
                )
                return (await cur.fetchone())[0]
        except Exception as e:
            raise map_db_error(e)

    # ---------- writes
    async def upsert_bars(self, rows: list[Bar]) -> int:
        if not rows:
            return 0
        try:
            async with self.pool.connection() as c, c.cursor() as cur:
                await self._apply_timeouts(c)
                await cur.execute("SELECT current_setting('app.tenant_id', true)")
                if not (await cur.fetchone())[0]:
                    await cur.execute("SET LOCAL app.tenant_id = %s", [rows[0].tenant_id])
                await cur.executemany(SQL.UPSERT_BARS, [SQL.bar_params(r) for r in rows])
                await c.commit()
                return cur.rowcount
        except Exception as e:
            raise map_db_error(e)

    async def upsert_fundamentals(self, rows: list[Fundamentals]) -> int:
        if not rows:
            return 0
        try:
            async with self.pool.connection() as c, c.cursor() as cur:
                await self._apply_timeouts(c)
                await cur.execute("SELECT current_setting('app.tenant_id', true)")
                if not (await cur.fetchone())[0]:
                    await cur.execute("SET LOCAL app.tenant_id = %s", [rows[0].tenant_id])
                await cur.executemany(SQL.UPSERT_FUNDAMENTALS, [SQL.fund_params(r) for r in rows])
                await c.commit()
                return cur.rowcount
        except Exception as e:
            raise map_db_error(e)

    async def upsert_news(self, rows: list[News]) -> int:
        if not rows:
            return 0
        try:
            async with self.pool.connection() as c, c.cursor() as cur:
                await self._apply_timeouts(c)
                await cur.execute("SELECT current_setting('app.tenant_id', true)")
                if not (await cur.fetchone())[0]:
                    await cur.execute("SET LOCAL app.tenant_id = %s", [rows[0].tenant_id])
                await cur.executemany(SQL.UPSERT_NEWS, [SQL.news_params(r) for r in rows])
                await c.commit()
                return cur.rowcount
        except Exception as e:
            raise map_db_error(e)

    async def upsert_options(self, rows: list[OptionSnap]) -> int:
        if not rows:
            return 0
        try:
            async with self.pool.connection() as c, c.cursor() as cur:
                await self._apply_timeouts(c)
                await cur.execute("SELECT current_setting('app.tenant_id', true)")
                if not (await cur.fetchone())[0]:
                    await cur.execute("SET LOCAL app.tenant_id = %s", [rows[0].tenant_id])
                await cur.executemany(SQL.UPSERT_OPTIONS, [SQL.opt_params(r) for r in rows])
                await c.commit()
                return cur.rowcount
        except Exception as e:
            raise map_db_error(e)

    # ---------- reads
    async def latest_prices(self, symbols: list[str], vendor: str) -> list[LatestPrice]:
        if not symbols:
            return []
        try:
            async with self.pool.connection() as c, c.cursor() as cur:
                await self._apply_timeouts(c)
                await cur.execute(SQL.LATEST_PRICES, (vendor, symbols))
                return [
                    LatestPrice(
                        tenant_id=r[0], vendor=r[1], symbol=r[2], price=r[3], price_timestamp=r[4]
                    )
                    for r in await cur.fetchall()
                ]
        except Exception as e:
            raise map_db_error(e)

    async def bars_window(self, symbol: str, timeframe: str, start, end, vendor: str) -> list[Bar]:
        try:
            async with self.pool.connection() as c, c.cursor() as cur:
                await self._apply_timeouts(c)
                # rely on DSN options for tenant; caller must ensure it
                await cur.execute("SELECT current_setting('app.tenant_id', true)")
                tenant = (await cur.fetchone())[0]
                await cur.execute(
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
                    for r in await cur.fetchall()
                ]
        except Exception as e:
            raise map_db_error(e)
