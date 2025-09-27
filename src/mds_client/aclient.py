from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, List

import psycopg
from psycopg_pool import AsyncConnectionPool

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
    app_name: Optional[str] = "mds_client_async"
    connect_timeout: float = 10.0
    statement_timeout_ms: Optional[int] = None
    pool_min: int = 1
    pool_max: int = 10


class AMDS:
    def __init__(self, config: dict):
        c = _Cfg(**config)
        self._cfg = c
        self._pool = AsyncConnectionPool(
            conninfo=c.dsn,
            min_size=c.pool_min,
            max_size=c.pool_max,
            timeout=c.connect_timeout,
            kwargs={},  # defaults
        )

    async def aclose(self) -> None:
        await self._pool.close()

    # ---------- internal helpers ----------

    async def _prepare_conn(self, conn: psycopg.AsyncConnection) -> None:
        async with conn.cursor() as cur:
            if self._cfg.app_name:
                await cur.execute("SET application_name = %s", (self._cfg.app_name,))
            if self._cfg.statement_timeout_ms is not None:
                await cur.execute(
                    "SET statement_timeout = %s", (f"{self._cfg.statement_timeout_ms}ms",)
                )
            if self._cfg.tenant_id:
                await cur.execute("SET app.tenant_id = %s", (self._cfg.tenant_id,))

    async def _get_conn(self) -> psycopg.AsyncConnection:
        conn = await self._pool.getconn()
        try:
            await self._prepare_conn(conn)
        except Exception:
            await self._pool.putconn(conn, close=True)
            raise
        return conn

    async def _put_conn_ok(self, conn: psycopg.AsyncConnection) -> None:
        await self._pool.putconn(conn)

    async def _put_conn_bad(self, conn: psycopg.AsyncConnection) -> None:
        await self._pool.putconn(conn, close=True)

    @staticmethod
    def _dicts(rows: Iterable) -> list[dict]:
        return [r.model_dump(mode="python") if hasattr(r, "model_dump") else r for r in rows]

    # ---------- admin / health ----------

    async def health(self) -> bool:
        conn = await self._get_conn()
        try:
            async with conn.cursor() as cur:
                await cur.execute(q.HEALTH)
                await cur.fetchone()
                await conn.commit()
                return True
        except Exception:
            await conn.rollback()
            raise
        finally:
            await self._put_conn_ok(conn)

    async def schema_version(self) -> Optional[str]:
        conn = await self._get_conn()
        try:
            async with conn.cursor() as cur:
                try:
                    await cur.execute(q.SCHEMA_VERSION)
                    row = await cur.fetchone()
                    await conn.commit()
                    return row[0] if row else None
                except psycopg.errors.UndefinedTable:
                    await conn.commit()
                    return None
        except Exception:
            await conn.rollback()
            raise
        finally:
            await self._put_conn_ok(conn)

    # ---------- reads ----------

    async def latest_prices(self, symbols: Sequence[str], vendor: str) -> List[LatestPrice]:
        syms = [s.upper() for s in symbols]
        conn = await self._get_conn()
        try:
            async with conn.cursor() as cur:
                await cur.execute(q.LATEST_PRICES, {"vendor": vendor, "symbols": syms})
                rows = await cur.fetchall()
                await conn.commit()
                out: list[LatestPrice] = []
                for tenant_id, vendor, symbol, price, price_ts in rows:
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
        except Exception:
            await conn.rollback()
            raise
        finally:
            await self._put_conn_ok(conn)

    async def bars_window(self, symbol: str, timeframe: str, start, end, vendor: str):
        conn = await self._get_conn()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    q.BARS_WINDOW,
                    {
                        "vendor": vendor,
                        "symbol": symbol.upper(),
                        "timeframe": timeframe,
                        "start": start,
                        "end": end,
                    },
                )
                rows = await cur.fetchall()
                await conn.commit()
                return rows
        except Exception:
            await conn.rollback()
            raise
        finally:
            await self._put_conn_ok(conn)

    # ---------- writes (UPSERTS) ----------

    async def upsert_bars(self, rows: Sequence[Bar]) -> int:
        payload = self._dicts(rows)
        conn = await self._get_conn()
        try:
            async with conn.cursor() as cur:
                await cur.executemany(q.UPSERT_BARS, payload)
            await conn.commit()
            return len(payload)
        except Exception:
            await conn.rollback()
            raise
        finally:
            await self._put_conn_ok(conn)

    async def upsert_fundamentals(self, rows: Sequence[Fundamentals]) -> int:
        payload = self._dicts(rows)
        conn = await self._get_conn()
        try:
            async with conn.cursor() as cur:
                await cur.executemany(q.UPSERT_FUNDAMENTALS, payload)
            await conn.commit()
            return len(payload)
        except Exception:
            await conn.rollback()
            raise
        finally:
            await self._put_conn_ok(conn)

    async def upsert_news(self, rows: Sequence[News]) -> int:
        payload = self._dicts(rows)
        for r in payload:
            if not r.get("id"):
                r["id"] = str(uuid.uuid4())
        conn = await self._get_conn()
        try:
            async with conn.cursor() as cur:
                await cur.executemany(q.UPSERT_NEWS, payload)
            await conn.commit()
            return len(payload)
        except Exception:
            await conn.rollback()
            raise
        finally:
            await self._put_conn_ok(conn)

    async def upsert_options(self, rows: Sequence[OptionSnap]) -> int:
        payload = self._dicts(rows)
        conn = await self._get_conn()
        try:
            async with conn.cursor() as cur:
                await cur.executemany(q.UPSERT_OPTIONS, payload)
            await conn.commit()
            return len(payload)
        except Exception:
            await conn.rollback()
            raise
        finally:
            await self._put_conn_ok(conn)

    # ---------- jobs ----------

    async def enqueue_job(
        self, *, idempotency_key: str, job_type: str, payload: dict, priority: str = "medium"
    ) -> None:
        conn = await self._get_conn()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    q.ENQUEUE_JOB,
                    {
                        "idempotency_key": idempotency_key,
                        "job_type": job_type,
                        "payload": payload,
                        "priority": priority,
                    },
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        finally:
            await self._put_conn_ok(conn)
