from __future__ import annotations

import io
import csv
import uuid
import os
import gzip
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, BinaryIO

import psycopg
from psycopg import sql as psql
from psycopg_pool import ConnectionPool

# Optional, only used if write_mode == "values"
try:
    from psycopg.extras import execute_values  # psycopg3 extras

    _HAS_EXECUTE_VALUES = True
except Exception:
    _HAS_EXECUTE_VALUES = False

from .models import Bar, Fundamentals, News, OptionSnap, LatestPrice
from . import sql as q

# --- errors fallback ---
try:
    from .errors import (
        MDSOperationalError,
        RetryableError,
        ConstraintViolation,
        RLSDenied,
        TimeoutExceeded,
    )
except Exception:

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
    # ---- fast-path toggles ----
    # auto: choose COPY for very large sets, VALUES for mid-size (if available), else executemany
    # values: force execute_values (if available) else executemany
    # copy: force COPY path
    # executemany: always psycopg executemany
    write_mode: str = os.environ.get("MDS_WRITE_MODE", "auto")
    values_min_rows: int = int(os.environ.get("MDS_VALUES_MIN_ROWS", "500"))
    values_page_size: int = int(os.environ.get("MDS_VALUES_PAGE_SIZE", "1000"))
    copy_min_rows: int = int(os.environ.get("MDS_COPY_MIN_ROWS", "5000"))


class MDS:
    def __init__(self, config: dict):
        c = _Cfg(**config)
        self._cfg = c
        self._pool = ConnectionPool(
            conninfo=c.dsn,
            min_size=c.pool_min,
            max_size=c.pool_max,
            timeout=c.connect_timeout,
            kwargs={},  # defaults
        )

    def close(self) -> None:
        self._pool.close()

    # ---------- internal helpers ----------

    @contextmanager
    def _conn(self):
        with self._pool.connection() as conn:
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
        return [r.model_dump(mode="python") if hasattr(r, "model_dump") else r for r in rows]

    def _choose_mode(self, nrows: int) -> str:
        mode = (self._cfg.write_mode or "auto").lower()
        if mode == "auto":
            if nrows >= self._cfg.copy_min_rows:
                return "copy"
            if _HAS_EXECUTE_VALUES and nrows >= self._cfg.values_min_rows:
                return "values"
            return "executemany"
        if mode == "values" and not _HAS_EXECUTE_VALUES:
            return "executemany"
        return mode

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

    # ---------- generic fast paths ----------

    @staticmethod
    def _csv_bytes(rows: list[dict], cols: list[str]) -> bytes:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        for r in rows:
            w.writerow([r.get(c) if r.get(c) is not None else r.get(c) for c in cols])
        return buf.getvalue().encode()

    def _copy_upsert(
        self,
        conn: psycopg.Connection,
        *,
        target: str,
        cols: list[str],
        conflict_cols: list[str],
        update_cols: list[str],
    ) -> int:
        tmp = f"tmp_{target}_{uuid.uuid4().hex[:8]}"
        with conn.cursor() as cur:
            # temp table mirrors target (safe and future-proof)
            cur.execute(
                psql.SQL("CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS)").format(
                    psql.Identifier(tmp), psql.Identifier(target)
                )
            )
            # COPY into temp (only the needed cols)
            copy_sql = psql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv)").format(
                psql.Identifier(tmp),
                psql.SQL(", ").join(psql.Identifier(c) for c in cols),
            )
            data = self._csv_bytes(self._pending_rows, cols)  # filled by caller
            with cur.copy(copy_sql) as cp:
                cp.write(data)

            # Upsert from temp
            insert_sql = psql.SQL(
                """
                INSERT INTO {} ({cols})
                SELECT {cols} FROM {}
                ON CONFLICT ({conflict}) DO UPDATE
                SET {updates}, updated_at = NOW()
            """
            ).format(
                psql.Identifier(target),
                psql.Identifier(tmp),
                cols=psql.SQL(", ").join(psql.Identifier(c) for c in cols),
                conflict=psql.SQL(", ").join(psql.Identifier(c) for c in conflict_cols),
                updates=psql.SQL(", ").join(
                    psql.SQL("{} = EXCLUDED.{}").format(psql.Identifier(c), psql.Identifier(c))
                    for c in update_cols
                ),
            )
            cur.execute(insert_sql)
            # ON COMMIT DROP cleans temp
            return cur.rowcount

    def _values_upsert(
        self,
        cur: psycopg.Cursor,
        *,
        target: str,
        cols: list[str],
        conflict_cols: list[str],
        update_cols: list[str],
        rows: list[dict],
        page_size: int,
    ) -> int:
        # Build "INSERT ... VALUES %s ON CONFLICT (...) DO UPDATE SET ..."
        base_sql = psql.SQL(
            "INSERT INTO {} ({}) VALUES %s ON CONFLICT ({}) DO UPDATE SET {} , updated_at = NOW()"
        ).format(
            psql.Identifier(target),
            psql.SQL(", ").join(psql.Identifier(c) for c in cols),
            psql.SQL(", ").join(psql.Identifier(c) for c in conflict_cols),
            psql.SQL(", ").join(
                psql.SQL("{} = EXCLUDED.{}").format(psql.Identifier(c), psql.Identifier(c))
                for c in update_cols
            ),
        )
        # execute_values needs a list of tuples in column order
        tuples = [tuple(r.get(c) for c in cols) for r in rows]
        execute_values(cur, base_sql.as_string(cur), tuples, page_size=page_size)
        return len(tuples)

    # ---------- writes (UPSERTS) ----------

    def upsert_bars(self, rows: Sequence[Bar]) -> int:
        payload = self._dicts(rows)
        if not payload:
            return 0
        for r in payload:
            r["symbol"] = r["symbol"].upper()

        mode = self._choose_mode(len(payload))
        with self._conn() as conn, conn.cursor() as cur:
            if mode == "copy":
                self._pending_rows = payload
                return self._copy_upsert(
                    conn,
                    target="bars",
                    cols=[
                        "ts",
                        "tenant_id",
                        "vendor",
                        "symbol",
                        "timeframe",
                        "open_price",
                        "high_price",
                        "low_price",
                        "close_price",
                        "volume",
                    ],
                    conflict_cols=["ts", "tenant_id", "vendor", "symbol", "timeframe"],
                    update_cols=["open_price", "high_price", "low_price", "close_price", "volume"],
                )
            if mode == "values":
                return self._values_upsert(
                    cur,
                    target="bars",
                    cols=[
                        "ts",
                        "tenant_id",
                        "vendor",
                        "symbol",
                        "timeframe",
                        "open_price",
                        "high_price",
                        "low_price",
                        "close_price",
                        "volume",
                    ],
                    conflict_cols=["ts", "tenant_id", "vendor", "symbol", "timeframe"],
                    update_cols=["open_price", "high_price", "low_price", "close_price", "volume"],
                    rows=payload,
                    page_size=self._cfg.values_page_size,
                )
            # default executemany
            cur.executemany(q.UPSERT_BARS, payload)
            return len(payload)

    def upsert_fundamentals(self, rows: Sequence[Fundamentals]) -> int:
        payload = self._dicts(rows)
        if not payload:
            return 0
        for r in payload:
            r["symbol"] = r["symbol"].upper()
        mode = self._choose_mode(len(payload))
        with self._conn() as conn, conn.cursor() as cur:
            if mode == "copy":
                self._pending_rows = payload
                return self._copy_upsert(
                    conn,
                    target="fundamentals",
                    cols=[
                        "asof",
                        "tenant_id",
                        "vendor",
                        "symbol",
                        "total_assets",
                        "total_liabilities",
                        "net_income",
                        "eps",
                    ],
                    conflict_cols=["asof", "tenant_id", "vendor", "symbol"],
                    update_cols=["total_assets", "total_liabilities", "net_income", "eps"],
                )
            if mode == "values":
                return self._values_upsert(
                    cur,
                    target="fundamentals",
                    cols=[
                        "asof",
                        "tenant_id",
                        "vendor",
                        "symbol",
                        "total_assets",
                        "total_liabilities",
                        "net_income",
                        "eps",
                    ],
                    conflict_cols=["asof", "tenant_id", "vendor", "symbol"],
                    update_cols=["total_assets", "total_liabilities", "net_income", "eps"],
                    rows=payload,
                    page_size=self._cfg.values_page_size,
                )
            cur.executemany(q.UPSERT_FUNDAMENTALS, payload)
            return len(payload)

    def upsert_news(self, rows: Sequence[News]) -> int:
        payload = self._dicts(rows)
        if not payload:
            return 0
        for r in payload:
            if not r.get("id"):
                r["id"] = str(uuid.uuid4())
            # title/url/symbol may be None; ok
        mode = self._choose_mode(len(payload))
        with self._conn() as conn, conn.cursor() as cur:
            if mode == "copy":
                self._pending_rows = payload
                return self._copy_upsert(
                    conn,
                    target="news",
                    cols=[
                        "published_at",
                        "tenant_id",
                        "vendor",
                        "id",
                        "symbol",
                        "title",
                        "url",
                        "sentiment_score",
                    ],
                    conflict_cols=["published_at", "tenant_id", "vendor", "id"],
                    update_cols=["symbol", "title", "url", "sentiment_score"],
                )
            if mode == "values":
                return self._values_upsert(
                    cur,
                    target="news",
                    cols=[
                        "published_at",
                        "tenant_id",
                        "vendor",
                        "id",
                        "symbol",
                        "title",
                        "url",
                        "sentiment_score",
                    ],
                    conflict_cols=["published_at", "tenant_id", "vendor", "id"],
                    update_cols=["symbol", "title", "url", "sentiment_score"],
                    rows=payload,
                    page_size=self._cfg.values_page_size,
                )
            cur.executemany(q.UPSERT_NEWS, payload)
            return len(payload)

    def upsert_options(self, rows: Sequence[OptionSnap]) -> int:
        payload = self._dicts(rows)
        if not payload:
            return 0
        for r in payload:
            r["symbol"] = r["symbol"].upper()
        mode = self._choose_mode(len(payload))
        with self._conn() as conn, conn.cursor() as cur:
            if mode == "copy":
                self._pending_rows = payload
                return self._copy_upsert(
                    conn,
                    target="options_snap",
                    cols=[
                        "ts",
                        "tenant_id",
                        "vendor",
                        "symbol",
                        "expiry",
                        "option_type",
                        "strike",
                        "iv",
                        "delta",
                        "gamma",
                        "oi",
                        "volume",
                        "spot",
                    ],
                    conflict_cols=[
                        "ts",
                        "tenant_id",
                        "vendor",
                        "symbol",
                        "expiry",
                        "option_type",
                        "strike",
                    ],
                    update_cols=["iv", "delta", "gamma", "oi", "volume", "spot"],
                )
            if mode == "values":
                return self._values_upsert(
                    cur,
                    target="options_snap",
                    cols=[
                        "ts",
                        "tenant_id",
                        "vendor",
                        "symbol",
                        "expiry",
                        "option_type",
                        "strike",
                        "iv",
                        "delta",
                        "gamma",
                        "oi",
                        "volume",
                        "spot",
                    ],
                    conflict_cols=[
                        "ts",
                        "tenant_id",
                        "vendor",
                        "symbol",
                        "expiry",
                        "option_type",
                        "strike",
                    ],
                    update_cols=["iv", "delta", "gamma", "oi", "volume", "spot"],
                    rows=payload,
                    page_size=self._cfg.values_page_size,
                )
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

    # ---------- backup/export/import helpers ----------

    def copy_out_csv(
        self,
        *,
        select_sql: psql.Composed,
        params: dict | None = None,
        out: BinaryIO | None = None,
        out_path: str | None = None,
        gzip_level: int = 6,
    ) -> int:
        """
        COPY (SELECT ...) TO STDOUT WITH CSV HEADER.
        Returns total bytes written. RLS is enforced (tenant set on connection).
        Use either `out` (open binary handle) or `out_path`; if out_path endswith .gz -> gzip.
        """
        if (out is None) == (out_path is None):
            raise ValueError("Provide exactly one of `out` or `out_path`")

        total = 0
        with self._conn() as conn, conn.cursor() as cur:
            # ensure params is dict, even if None
            params = params or {}
            copy_sql = psql.SQL("COPY ({}) TO STDOUT WITH (FORMAT csv, HEADER true)").format(
                select_sql
            )
            # open sink
            f = out
            if out_path is not None:
                f = (
                    gzip.open(out_path, "wb", gzip_level)
                    if out_path.endswith(".gz")
                    else open(out_path, "wb")
                )
            try:
                with cur.copy(copy_sql) as cp:
                    # psycopg3: cp.read() -> bytes until b"" on completion
                    while True:
                        chunk = cp.read()
                        if not chunk:
                            break
                        if params:
                            # For COPY (SELECT $1) you can't pass params here; params must be inlined.
                            # So we only use params to format literals into `select_sql` above.
                            pass
                        f.write(chunk)
                        total += len(chunk)
            finally:
                if out_path is not None and f is not None:
                    f.close()
        return total

    def copy_restore_csv(
        self,
        *,
        target: str,
        cols: list[str],
        conflict_cols: list[str],
        update_cols: list[str],
        src: BinaryIO | None = None,
        src_path: str | None = None,
    ) -> int:
        """
        COPY CSV (HEADER) from file/stdin into a TEMP table, then UPSERT into `target`.
        Returns affected rowcount from the final INSERT .. ON CONFLICT.
        """
        if (src is None) == (src_path is None):
            raise ValueError("Provide exactly one of `src` or `src_path`")
        with self._conn() as conn, conn.cursor() as cur:
            tmp = f"tmp_{target}_restore"
            cur.execute(
                psql.SQL("CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS)").format(
                    psql.Identifier(tmp), psql.Identifier(target)
                )
            )
            copy_in_sql = psql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv, HEADER true)").format(
                psql.Identifier(tmp),
                psql.SQL(", ").join(psql.Identifier(c) for c in cols),
            )
            f = src
            if src_path is not None:
                f = gzip.open(src_path, "rb") if src_path.endswith(".gz") else open(src_path, "rb")
            try:
                with cur.copy(copy_in_sql) as cp:
                    while True:
                        chunk = f.read(1 << 20)
                        if not chunk:
                            break
                        cp.write(chunk)
            finally:
                if src_path is not None and f is not None:
                    f.close()

            insert_sql = psql.SQL(
                """
                INSERT INTO {} ({cols})
                SELECT {cols} FROM {}
                ON CONFLICT ({conflict}) DO UPDATE
                SET {updates}, updated_at = NOW()
            """
            ).format(
                psql.Identifier(target),
                psql.Identifier(tmp),
                cols=psql.SQL(", ").join(psql.Identifier(c) for c in cols),
                conflict=psql.SQL(", ").join(psql.Identifier(c) for c in conflict_cols),
                updates=psql.SQL(", ").join(
                    psql.SQL("{} = EXCLUDED.{}").format(psql.Identifier(c), psql.Identifier(c))
                    for c in update_cols
                ),
            )
            cur.execute(insert_sql)
            return cur.rowcount

    def copy_out_ndjson(
        self,
        *,
        select_sql: psql.Composed,
        out: BinaryIO | None = None,
        out_path: str | None = None,
        gzip_level: int = 6,
    ) -> int:
        """
        Stream NDJSON using COPY (SELECT to_jsonb(t) FROM (<select_sql>) t) TO STDOUT.
        Each row is a single JSON object per line. Returns total bytes written.
        RLS is enforced by the connection's tenant context.
        """
        if (out is None) == (out_path is None):
            raise ValueError("Provide exactly one of `out` or `out_path`")

        total = 0
        with self._conn() as conn, conn.cursor() as cur:
            # Wrap the caller's SELECT as a derived table 't' and jsonify it row-by-row
            copy_sql = psql.SQL("COPY (SELECT to_jsonb(t) FROM ({}) t) TO STDOUT").format(
                select_sql
            )

            sink = out
            if out_path is not None:
                sink = (
                    gzip.open(out_path, "wb", gzip_level)
                    if out_path.endswith(".gz")
                    else open(out_path, "wb")
                )

            try:
                with cur.copy(copy_sql) as cp:
                    while True:
                        chunk = cp.read()
                        if not chunk:
                            break
                        sink.write(chunk)
                        total += len(chunk)
            finally:
                if out_path is not None and sink is not None:
                    sink.close()
        return total


# Convenience: table presets (so CLI can call by name)
TABLE_PRESETS: dict[str, dict[str, list[str]]] = {
    "bars": {
        "cols": [
            "ts",
            "tenant_id",
            "vendor",
            "symbol",
            "timeframe",
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "volume",
        ],
        "conflict": ["ts", "tenant_id", "vendor", "symbol", "timeframe"],
        "update": ["open_price", "high_price", "low_price", "close_price", "volume"],
    },
    "fundamentals": {
        "cols": [
            "asof",
            "tenant_id",
            "vendor",
            "symbol",
            "total_assets",
            "total_liabilities",
            "net_income",
            "eps",
        ],
        "conflict": ["asof", "tenant_id", "vendor", "symbol"],
        "update": ["total_assets", "total_liabilities", "net_income", "eps"],
    },
    "news": {
        "cols": [
            "published_at",
            "tenant_id",
            "vendor",
            "id",
            "symbol",
            "title",
            "url",
            "sentiment_score",
        ],
        "conflict": ["published_at", "tenant_id", "vendor", "id"],
        "update": ["symbol", "title", "url", "sentiment_score"],
    },
    "options_snap": {
        "cols": [
            "ts",
            "tenant_id",
            "vendor",
            "symbol",
            "expiry",
            "option_type",
            "strike",
            "iv",
            "delta",
            "gamma",
            "oi",
            "volume",
            "spot",
        ],
        "conflict": [
            "ts",
            "tenant_id",
            "vendor",
            "symbol",
            "expiry",
            "option_type",
            "strike",
        ],
        "update": ["iv", "delta", "gamma", "oi", "volume", "spot"],
    },
}
