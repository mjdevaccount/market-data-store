from __future__ import annotations
from typing import TypedDict, Optional, List
from psycopg_pool import AsyncConnectionPool
from .models import Bar, Fundamentals, News, OptionSnap, LatestPrice
from .rls import ensure_tenant_in_dsn
from .errors import map_db_error
from .sql import SQL


class AMDSConfig(TypedDict, total=False):
    dsn: str
    tenant_id: str
    app_name: str
    statement_timeout_ms: int
    pool_min: int
    pool_max: int


class AMDS:
    def __init__(self, cfg: AMDSConfig):
        dsn = ensure_tenant_in_dsn(cfg["dsn"], cfg.get("tenant_id"))
        self._pool = AsyncConnectionPool(
            dsn,
            min_size=int(cfg.get("pool_min", 1)),
            max_size=int(cfg.get("pool_max", 10)),
            kwargs={"autocommit": False},
        )
        self._stmt_timeout_ms = int(cfg.get("statement_timeout_ms", 0))
        self._app_name = cfg.get("app_name", "mds_client")

    async def _conn(self):
        async with self._pool.connection() as conn:
            try:
                if self._stmt_timeout_ms:
                    await conn.execute(f"SET LOCAL statement_timeout = {self._stmt_timeout_ms}")
                if self._app_name:
                    await conn.execute("SET LOCAL application_name = %s", (self._app_name,))
                yield conn
                await conn.commit()
            except Exception as e:
                await conn.rollback()
                raise map_db_error(e)

    # ---------- Health / Meta
    async def health(self) -> bool:
        async with self._pool.connection() as c:
            try:
                return (await c.execute("SELECT 1")).fetchone() is not None
            except Exception as e:
                raise map_db_error(e)

    async def schema_version(self) -> Optional[str]:
        async with self._pool.connection() as c:
            try:
                cur = await c.execute("SELECT version_num FROM alembic_version LIMIT 1")
                row = cur.fetchone()
                return row[0] if row else None
            except Exception as e:
                raise map_db_error(e)

    # ---------- Writes
    async def upsert_bars(self, rows: List[Bar]) -> int:
        async with self._pool.connection() as c:
            try:
                await c.executemany(SQL.UPSERT_BARS, [SQL.bar_params(r) for r in rows])
                await c.commit()
                return len(rows)
            except Exception as e:
                await c.rollback()
                raise map_db_error(e)

    async def upsert_fundamentals(self, rows: List[Fundamentals]) -> int:
        async with self._pool.connection() as c:
            try:
                await c.executemany(SQL.UPSERT_FUNDAMENTALS, [SQL.fund_params(r) for r in rows])
                await c.commit()
                return len(rows)
            except Exception as e:
                await c.rollback()
                raise map_db_error(e)

    async def upsert_news(self, rows: List[News]) -> int:
        async with self._pool.connection() as c:
            try:
                await c.executemany(SQL.UPSERT_NEWS, [SQL.news_params(r) for r in rows])
                await c.commit()
                return len(rows)
            except Exception as e:
                await c.rollback()
                raise map_db_error(e)

    async def upsert_options(self, rows: List[OptionSnap]) -> int:
        async with self._pool.connection() as c:
            try:
                await c.executemany(SQL.UPSERT_OPTIONS, [SQL.opt_params(r) for r in rows])
                await c.commit()
                return len(rows)
            except Exception as e:
                await c.rollback()
                raise map_db_error(e)

    async def latest_prices(self, symbols: List[str], vendor: str) -> List[LatestPrice]:
        async with self._pool.connection() as c:
            try:
                cur = await c.execute(SQL.LATEST_PRICES, (vendor, symbols))
                return [LatestPrice(**dict(r)) for r in cur.fetchall()]
            except Exception as e:
                raise map_db_error(e)
