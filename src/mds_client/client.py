from __future__ import annotations

import csv
import gzip
import io
from contextlib import contextmanager
from typing import Iterable, Sequence, TypedDict

import psycopg
from psycopg import sql as psql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

# Optional, only used if write_mode == "values"
try:
    from psycopg.extras import execute_values

    _HAS_EXECUTE_VALUES = True
except ImportError:
    _HAS_EXECUTE_VALUES = False

from .sql import (
    TABLE_PRESETS,
    upsert_statement,
    latest_prices_select,
    bars_window_select,
    build_ndjson_select,
    copy_to_stdout_ndjson,
    copy_to_stdout_csv,
)


class MDSConfig(TypedDict, total=False):
    dsn: str
    tenant_id: str
    app_name: str
    connect_timeout: float
    statement_timeout_ms: int
    pool_min: int
    pool_max: int
    write_mode: str  # "auto" | "executemany" | "values" | "copy"
    values_min_rows: int
    values_page_size: int
    copy_min_rows: int


DEFAULTS: MDSConfig = {
    "pool_min": 1,
    "pool_max": 10,
    "write_mode": "auto",
    "values_min_rows": 500,
    "values_page_size": 1000,
    "copy_min_rows": 5000,
}


class MDS:
    def __init__(self, cfg: MDSConfig):
        self.cfg: MDSConfig = {**DEFAULTS, **(cfg or {})}
        if "dsn" not in self.cfg:
            raise ValueError("dsn required")
        self.pool = ConnectionPool(
            conninfo=self.cfg["dsn"],
            min_size=self.cfg["pool_min"],
            max_size=self.cfg["pool_max"],
            kwargs={"autocommit": False},
        )
        self.tenant_id = self.cfg.get("tenant_id")
        self.statement_timeout_ms = self.cfg.get("statement_timeout_ms")
        self.app_name = self.cfg.get("app_name")

    # ---------- context / setup ----------

    @contextmanager
    def _conn(self):
        with self.pool.connection() as conn:
            if self.app_name:
                conn.execute(
                    psql.SQL("SET application_name = {}").format(psql.Literal(self.app_name))
                )
            if self.statement_timeout_ms:
                conn.execute(
                    psql.SQL("SET statement_timeout = {}").format(
                        psql.Literal(int(self.statement_timeout_ms))
                    )
                )
            if self.tenant_id:
                conn.execute(
                    psql.SQL("SET LOCAL app.tenant_id = {}").format(psql.Literal(self.tenant_id))
                )
            yield conn

    # ---------- health / meta ----------

    def health(self) -> bool:
        with self._conn() as c:
            c.execute("SELECT 1")
            return True

    def schema_version(self) -> str | None:
        with self._conn() as c:
            # Alembic stamp target (optional). Return NULL if not present.
            try:
                cur = c.execute("SELECT version_num FROM alembic_version LIMIT 1")
                row = cur.fetchone()
                return row[0] if row else None
            except psycopg.errors.UndefinedTable:
                return None

    def close(self) -> None:
        self.pool.close()

    # ---------- generic upsert ----------

    def _coerce_rows(self, rows: Iterable[object]) -> list[dict]:
        out: list[dict] = []
        for r in rows:
            if r is None:
                continue
            if hasattr(r, "model_dump"):
                out.append(r.model_dump(exclude_none=True))
            elif isinstance(r, dict):
                out.append({k: v for k, v in r.items() if v is not None})
            else:
                # Fallback to __dict__
                out.append({k: v for k, v in vars(r).items() if v is not None})
        return out

    def _write_mode(self, nrows: int) -> str:
        mode = (self.cfg.get("write_mode") or "auto").lower()
        if mode != "auto":
            return mode
        if nrows >= int(self.cfg["copy_min_rows"]):
            return "copy"
        if nrows >= int(self.cfg["values_min_rows"]):
            return "values"
        return "executemany"

    def _copy_from_memory_csv(
        self, conn: psycopg.Connection, table: str, cols: Sequence[str], rows: Sequence[dict]
    ):
        sio = io.StringIO()
        writer = csv.DictWriter(sio, fieldnames=list(cols))
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r.get(c) for c in cols})
        sio.seek(0)
        with (
            conn.cursor() as cur,
            cur.copy(
                psql.SQL("COPY {} ({}) FROM STDIN WITH CSV HEADER").format(
                    psql.Identifier(table),
                    psql.SQL(", ").join(psql.Identifier(c) for c in cols),
                )
            ) as cp,
        ):
            cp.write(sio.read())

    def _upsert(
        self,
        table: str,
        rows: Iterable[object],
    ) -> int:
        preset = TABLE_PRESETS[table]
        cols, conflict, update = preset["cols"], preset["conflict"], preset["update"]
        sql_stmt = upsert_statement(table, cols, conflict, update)
        data = self._coerce_rows(rows)
        if not data:
            return 0

        with self._conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                mode = self._write_mode(len(data))
                if mode == "executemany":
                    cur.executemany(sql_stmt, data)
                elif mode == "values":
                    if not _HAS_EXECUTE_VALUES:
                        # Fallback to executemany if execute_values not available
                        cur.executemany(sql_stmt, data)
                    else:
                        # Build VALUES template like (%(col)s, %(col2)s, ...)
                        tpl = "(" + ", ".join(f"%({c})s" for c in cols) + ")"
                        execute_values(
                            cur,
                            sql_stmt.as_string(conn),
                            data,
                            template=tpl,
                            page_size=self.cfg["values_page_size"],
                        )
                elif mode == "copy":
                    # COPY into temp then upsert from temp for idempotency
                    temp = psql.Identifier(f"tmp_{table}_copy")
                    cur.execute(
                        psql.SQL(
                            "CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS) ON COMMIT DROP"
                        ).format(temp, psql.Identifier(table))
                    )
                    self._copy_from_memory_csv(conn, temp.string, cols, data)
                    ins = psql.SQL(
                        "INSERT INTO {} ({cols}) SELECT {cols} FROM {} "
                        "ON CONFLICT ({conf}) DO UPDATE SET {upd}"
                    ).format(
                        psql.Identifier(table),
                        temp,
                        cols=psql.SQL(", ").join(psql.Identifier(c) for c in cols),
                        conf=psql.SQL(", ").join(psql.Identifier(c) for c in conflict),
                        upd=psql.SQL(", ").join(
                            psql.SQL("{} = EXCLUDED.{}").format(
                                psql.Identifier(c), psql.Identifier(c)
                            )
                            for c in preset["update"]
                        ),
                    )
                    cur.execute(ins)
                else:
                    raise ValueError(f"unknown write_mode {mode}")
            conn.commit()
        return len(data)

    # ---------- typed upserts ----------

    def upsert_bars(self, rows: Sequence[object]) -> int:
        return self._upsert("bars", rows)

    def upsert_fundamentals(self, rows: Sequence[object]) -> int:
        return self._upsert("fundamentals", rows)

    def upsert_news(self, rows: Sequence[object]) -> int:
        # ensure id exists if provided rows omit it; DB default gen_random_uuid() is not PK here
        # but leaving None is okay because we conflict on (published_at, tenant_id, vendor, id)
        return self._upsert("news", rows)

    def upsert_options(self, rows: Sequence[object]) -> int:
        return self._upsert("options_snap", rows)

    # ---------- reads ----------

    def latest_prices(self, symbols: Iterable[str], vendor: str) -> list[dict]:
        if not self.tenant_id:
            raise ValueError("tenant_id required for latest_prices()")
        q = latest_prices_select(symbols, vendor, self.tenant_id)
        with self._conn() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q)
            return list(cur.fetchall())

    def bars_window(
        self, *, symbol: str, timeframe: str, start: str, end: str, vendor: str
    ) -> list[dict]:
        q = bars_window_select(
            symbol=symbol, timeframe=timeframe, start=start, end=end, vendor=vendor
        )
        with self._conn() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(q)
            return list(cur.fetchall())

    # ---------- COPY export (CSV / NDJSON) ----------

    def copy_out_csv(self, *, select_sql: psql.Composed, out_path: str) -> int:
        copy_sql = copy_to_stdout_csv(select_sql)
        writer = gzip.open(out_path, "wb") if out_path.endswith(".gz") else open(out_path, "wb")
        try:
            with self._conn() as conn, conn.cursor() as cur, cur.copy(copy_sql) as cp:
                n = 0
                while True:
                    chunk = cp.read()
                    if not chunk:
                        break
                    writer.write(chunk)
                    n += len(chunk)
                return n
        finally:
            writer.close()

    def copy_out_ndjson(self, *, select_sql: psql.Composed, out_path: str) -> int:
        # select_sql must be SELECT to_jsonb(...) ...
        copy_sql = copy_to_stdout_ndjson(select_sql)
        writer = gzip.open(out_path, "wb") if out_path.endswith(".gz") else open(out_path, "wb")
        try:
            with self._conn() as conn, conn.cursor() as cur, cur.copy(copy_sql) as cp:
                n = 0
                while True:
                    chunk = cp.read()
                    if not chunk:
                        break
                    writer.write(chunk)
                    writer.write(b"\n")
                    n += len(chunk) + 1
                return n
        finally:
            writer.close()

    # ---------- CSV restore via temp + upsert ----------

    def copy_restore_csv(
        self,
        *,
        target: str,
        cols: Sequence[str],
        conflict_cols: Sequence[str],
        update_cols: Sequence[str],
        src_path: str,
    ) -> int:
        temp = f"tmp_{target}_restore"
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                psql.SQL("CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS) ON COMMIT DROP").format(
                    psql.Identifier(temp), psql.Identifier(target)
                )
            )
            copy_in = psql.SQL("COPY {} ({}) FROM STDIN WITH CSV HEADER").format(
                psql.Identifier(temp), psql.SQL(", ").join(psql.Identifier(c) for c in cols)
            )
            reader = gzip.open(src_path, "rb") if src_path.endswith(".gz") else open(src_path, "rb")
            try:
                with cur.copy(copy_in) as cp:
                    while True:
                        chunk = reader.read(1 << 20)
                        if not chunk:
                            break
                        cp.write(chunk)
            finally:
                reader.close()

            ins = psql.SQL(
                "INSERT INTO {} ({cols}) SELECT {cols} FROM {} "
                "ON CONFLICT ({conf}) DO UPDATE SET {upd}"
            ).format(
                psql.Identifier(target),
                psql.Identifier(temp),
                cols=psql.SQL(", ").join(psql.Identifier(c) for c in cols),
                conf=psql.SQL(", ").join(psql.Identifier(c) for c in conflict_cols),
                upd=psql.SQL(", ").join(
                    psql.SQL("{} = EXCLUDED.{}").format(psql.Identifier(c), psql.Identifier(c))
                    for c in update_cols
                ),
            )
            cur.execute(ins)
            conn.commit()
            return cur.rowcount

    # ---------- helpers exposed to CLI ----------

    def build_ndjson_select(
        self,
        table: str,
        *,
        vendor: str | None,
        symbol: str | None,
        timeframe: str | None,
        start: str | None,
        end: str | None,
    ) -> psql.Composed:
        preset = TABLE_PRESETS[table]
        return build_ndjson_select(
            table,
            preset["cols"],
            vendor=vendor,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
        )
