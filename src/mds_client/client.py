from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

import psycopg
from psycopg_pool import ConnectionPool

from .models import Bar, Fundamentals, News, OptionSnap, LatestPrice
from . import sql as q

try:
    from .errors import (
        MDSOperationalError,
        RetryableError,
        ConstraintViolation,
        RLSDenied,
        TimeoutExceeded,
    )
except Exception:  # minimal fallback

    class MDSOperationalError(Exception): ...

    class RetryableError(MDSOperationalError): ...

    class ConstraintViolation(MDSOperationalError): ...

    class RLSDenied(MDSOperationalError): ...

    class TimeoutExceeded(MDSOperationalError): ...


@dataclass
class _Cfg:
    dsn: str
    tenant_id: Optional[str] = None
    app_name: Optional[str] = "mds_client"
    connect_timeout: float = 10.0
    statement_timeout_ms: Optional[int] = None
    pool_min: int = 1
    pool_max: int = 10


class MDS:
    def __init__(self, config: dict):
        c = _Cfg(**config)
        self._cfg = c
        # You can pass options in DSN too; timeout controlled by server param/SET below
        self._pool = ConnectionPool(
            conninfo=c.dsn,
            min_size=c.pool_min,
            max_size=c.pool_max,
            timeout=c.connect_timeout,
            kwargs={},  # leave defaults (autocommit False)
        )

    def close(self) -> None:
        self._pool.close()

    # ---------- internal helpers ----------

    @contextmanager
    def _conn(self):
        with self._pool.connection() as conn:
            # Per-connection session config
            with conn.cursor() as cur:
                if self._cfg.app_name:
                    cur.execute("SET application_name = %s", (self._cfg.app_name,))
                if self._cfg.statement_timeout_ms is not None:
                    cur.execute(
                        "SET statement_timeout = %s", (f"{self._cfg.statement_timeout_ms}ms",)
                    )
                if self._cfg.tenant_id:
                    cur.execute("SET app.tenant_id = %s", (self._cfg.tenant_id,))
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @staticmethod
    def _dicts(rows: Iterable) -> list[dict]:
        # pydantic v2
        return [r.model_dump(mode="python") if hasattr(r, "model_dump") else r for r in rows]

    # ---------- admin / health ----------

    def health(self) -> bool:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(q.HEALTH)
            _ = cur.fetchone()
            return True

    def schema_version(self) -> Optional[str]:
        with self._conn() as conn, conn.cursor() as cur:
            try:
                cur.execute(q.SCHEMA_VERSION)
                row = cur.fetchone()
                return row[0] if row else None
            except psycopg.errors.UndefinedTable:
                return None

    # ---------- reads ----------

    def latest_prices(self, symbols: Sequence[str], vendor: str) -> list[LatestPrice]:
        syms = [s.upper() for s in symbols]
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(q.LATEST_PRICES, {"vendor": vendor, "symbols": syms})
            out: list[LatestPrice] = []
            for tenant_id, vendor, symbol, price, price_ts in cur.fetchall():
                out.append(
                    LatestPrice(
                        tenant_id=str(tenant_id),
                        vendor=vendor,
                        symbol=symbol,
                        price=float(price),
                        price_timestamp=price_ts,
                    )
                )
            return out

    def bars_window(self, symbol: str, timeframe: str, start, end, vendor: str):
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                q.BARS_WINDOW,
                {
                    "vendor": vendor,
                    "symbol": symbol.upper(),
                    "timeframe": timeframe,
                    "start": start,
                    "end": end,
                },
            )
            return cur.fetchall()

    # ---------- writes (UPSERTS) ----------

    def upsert_bars(self, rows: Sequence[Bar]) -> int:
        payload = self._dicts(rows)
        with self._conn() as conn, conn.cursor() as cur:
            cur.executemany(q.UPSERT_BARS, payload)
            return len(payload)

    def upsert_fundamentals(self, rows: Sequence[Fundamentals]) -> int:
        payload = self._dicts(rows)
        with self._conn() as conn, conn.cursor() as cur:
            cur.executemany(q.UPSERT_FUNDAMENTALS, payload)
            return len(payload)

    def upsert_news(self, rows: Sequence[News]) -> int:
        payload = self._dicts(rows)
        # ensure an id (PK requires it)
        for r in payload:
            if not r.get("id"):
                r["id"] = str(uuid.uuid4())
        with self._conn() as conn, conn.cursor() as cur:
            cur.executemany(q.UPSERT_NEWS, payload)
            return len(payload)

    def upsert_options(self, rows: Sequence[OptionSnap]) -> int:
        payload = self._dicts(rows)
        with self._conn() as conn, conn.cursor() as cur:
            cur.executemany(q.UPSERT_OPTIONS, payload)
            return len(payload)

    # ---------- jobs ----------

    def enqueue_job(
        self, *, idempotency_key: str, job_type: str, payload: dict, priority: str = "medium"
    ) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                q.ENQUEUE_JOB,
                {
                    "idempotency_key": idempotency_key,
                    "job_type": job_type,
                    "payload": payload,
                    "priority": priority,
                },
            )
