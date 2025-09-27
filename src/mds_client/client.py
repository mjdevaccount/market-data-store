from __future__ import annotations
from typing import Iterable, TypedDict, Optional, List
from contextlib import contextmanager
from psycopg_pool import ConnectionPool
from .models import Bar, Fundamentals, News, OptionSnap, LatestPrice
from .rls import ensure_tenant_in_dsn
from .errors import map_db_error
from .sql import SQL


class MDSConfig(TypedDict, total=False):
    dsn: str
    tenant_id: str
    app_name: str
    connect_timeout: float
    statement_timeout_ms: int
    pool_min: int
    pool_max: int


class MDS:
    def __init__(self, cfg: MDSConfig):
        dsn = cfg["dsn"]
        dsn = ensure_tenant_in_dsn(dsn, cfg.get("tenant_id"))
        self._pool = ConnectionPool(
            dsn,
            min_size=int(cfg.get("pool_min", 1)),
            max_size=int(cfg.get("pool_max", 10)),
            kwargs={"autocommit": False},
        )
        self._stmt_timeout_ms = int(cfg.get("statement_timeout_ms", 0))
        self._app_name = cfg.get("app_name", "mds_client")

    @contextmanager
    def _conn(self):
        with self._pool.connection() as conn:
            try:
                if self._stmt_timeout_ms:
                    conn.execute(f"SET LOCAL statement_timeout = {self._stmt_timeout_ms}")
                if self._app_name:
                    conn.execute("SET LOCAL application_name = %s", (self._app_name,))
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise map_db_error(e)

    # ---------- Health / Meta
    def health(self) -> bool:
        with self._conn() as c:
            return c.execute("SELECT 1").fetchone() is not None

    def schema_version(self) -> Optional[str]:
        with self._conn() as c:
            cur = c.execute("SELECT version_num FROM alembic_version LIMIT 1")
            row = cur.fetchone()
            return row[0] if row else None

    # ---------- Writes (executemany)
    def _execmany(self, q: str, params: Iterable[tuple]) -> int:
        with self._conn() as c:
            cur = c.cursor()
            cur.executemany(q, params)
            # rowcount unreliable for upserts; return count we attempted
            return cur.rowcount if cur.rowcount >= 0 else 0

    def upsert_bars(self, rows: List[Bar]) -> int:
        return self._execmany(SQL.UPSERT_BARS, (SQL.bar_params(r) for r in rows))

    def upsert_fundamentals(self, rows: List[Fundamentals]) -> int:
        return self._execmany(SQL.UPSERT_FUNDAMENTALS, (SQL.fund_params(r) for r in rows))

    def upsert_news(self, rows: List[News]) -> int:
        return self._execmany(SQL.UPSERT_NEWS, (SQL.news_params(r) for r in rows))

    def upsert_options(self, rows: List[OptionSnap]) -> int:
        return self._execmany(SQL.UPSERT_OPTIONS, (SQL.opt_params(r) for r in rows))

    def enqueue_job(
        self,
        *,
        tenant_id: str,
        idempotency_key: str,
        job_type: str,
        payload: dict,
        priority: str = "medium",
        status: str = "queued",
    ) -> Optional[int]:
        with self._conn() as c:
            cur = c.execute(
                SQL.ENQUEUE_JOB, (tenant_id, idempotency_key, job_type, payload, status, priority)
            )
            row = cur.fetchone()
            return row[0] if row else None

    # ---------- Reads
    def latest_prices(self, symbols: List[str], vendor: str) -> List[LatestPrice]:
        with self._conn() as c:
            cur = c.execute(SQL.LATEST_PRICES, (vendor, symbols))
            return [LatestPrice(**dict(row)) for row in cur.fetchall()]

    def bars_window(
        self, symbol: str, timeframe: str, start, end, vendor: str, tenant_id: str
    ) -> List[Bar]:
        with self._conn() as c:
            cur = c.execute(
                SQL.BARS_WINDOW, (tenant_id, vendor, symbol.upper(), timeframe, start, end)
            )
            return [Bar(**dict(row)) for row in cur.fetchall()]
