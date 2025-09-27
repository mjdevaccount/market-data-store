from __future__ import annotations

import csv
import gzip
import io
import os
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
    build_ndjson_select,
)


def _open_maybe_gz(path: str, mode: str):
    if path == "-":
        # stdin/stdout modes
        return (
            io.TextIOWrapper(os.fdopen(0, "rb"), encoding="utf-8")
            if "r" in mode
            else io.TextIOWrapper(os.fdopen(1, "wb"), encoding="utf-8")
        )
    if path.endswith(".gz"):
        return gzip.open(path, mode)  # text mode if "t" in mode
    return open(path, mode, encoding="utf-8")


def upsert_statement(
    table: str,
    cols: Sequence[str],
    conflict_cols: Sequence[str],
    update_cols: Sequence[str],
) -> psql.Composed:
    """INSERT ... ON CONFLICT ... DO UPDATE with named parameters (%(name)s)."""
    ins_cols = psql.SQL(", ").join(psql.Identifier(c) for c in cols)
    ins_vals = psql.SQL(", ").join(psql.Placeholder(c) for c in cols)
    conflict = psql.SQL(", ").join(psql.Identifier(c) for c in conflict_cols)
    setlist = psql.SQL(", ").join(
        psql.SQL("{} = EXCLUDED.{}").format(psql.Identifier(c), psql.Identifier(c))
        for c in update_cols
    )
    return psql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) DO UPDATE SET {}").format(
        psql.Identifier(table), ins_cols, ins_vals, conflict, setlist
    )


def latest_prices_select(symbols: Iterable[str], vendor: str, tenant_id: str) -> psql.Composed:
    # Uses your view latest_prices(tenant_id,vendor,symbol,price,price_timestamp)
    return psql.SQL(
        "SELECT vendor, symbol, price, price_timestamp "
        "FROM latest_prices WHERE tenant_id = {tid} AND vendor = {v} AND symbol = ANY({syms})"
    ).format(
        tid=psql.Literal(tenant_id),
        v=psql.Literal(vendor),
        syms=psql.Literal(list({s.upper() for s in symbols})),
    )


def bars_window_select(
    *, symbol: str, timeframe: str, start: str, end: str, vendor: str
) -> psql.Composed:
    return psql.SQL(
        "SELECT ts, tenant_id, vendor, symbol, timeframe, open_price, high_price, "
        "low_price, close_price, volume "
        "FROM bars "
        "WHERE vendor = {v} AND symbol = {s} AND timeframe = {tf} "
        "AND ts >= {start} AND ts < {end} "
        "ORDER BY ts"
    ).format(
        v=psql.Literal(vendor),
        s=psql.Literal(symbol.upper()),
        tf=psql.Literal(timeframe),
        start=psql.Literal(start),
        end=psql.Literal(end),
    )


def copy_to_stdout_ndjson(select_json_sql: psql.Composed) -> psql.Composed:
    # Expect a SELECT producing a single json/jsonb column per row.
    return psql.SQL("COPY ({}) TO STDOUT").format(select_json_sql)


def copy_to_stdout_csv(select_sql: psql.Composed) -> psql.Composed:
    return psql.SQL("COPY ({}) TO STDOUT WITH CSV HEADER").format(select_sql)


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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close the connection pool."""
        if hasattr(self, "pool") and self.pool:
            self.pool.close()

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
            # Note: app.tenant_id parameter not supported in this database
            # Tenant isolation is handled via RLS policies instead
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

    # ---------- generic upsert ----------

    def _coerce_rows(self, rows: Iterable[object]) -> list[dict]:
        out: list[dict] = []
        for r in rows:
            if r is None:
                continue
            if hasattr(r, "model_dump"):
                out.append(r.model_dump())
            elif isinstance(r, dict):
                out.append(r)
            else:
                # Fallback to __dict__
                out.append(vars(r))
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
        cols, conflict, update = preset.cols, preset.conflict, preset.update
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
        csv_has_header: bool = True,
        csv_delimiter: str = ",",
    ) -> int:
        """
        Restore CSV (optionally .gz) by staging into a TEMP table, then
        INSERT ... ON CONFLICT DO UPDATE. Returns affected row count.
        """
        col_idents = psql.SQL(", ").join(psql.Identifier(c) for c in cols)
        conflict_idents = psql.SQL(", ").join(psql.Identifier(c) for c in conflict_cols)
        set_list = psql.SQL(", ").join(
            psql.SQL("{c}=EXCLUDED.{c}").format(c=psql.Identifier(c)) for c in update_cols
        )

        # unique temp name per session
        tmp = psql.Identifier(f"_staging_{target}")

        with self.pool.connection() as conn:
            # RLS & timeouts should already be set in pool prepare hook.
            with conn.cursor() as cur:
                cur.execute(
                    psql.SQL("CREATE TEMP TABLE {tmp} (LIKE {t} INCLUDING DEFAULTS)").format(
                        tmp=tmp, t=psql.Identifier(target)
                    )
                )

                copy_sql = psql.SQL(
                    "COPY {tmp} ({cols}) FROM STDIN WITH (FORMAT csv, HEADER {hdr}, DELIMITER {delim})"
                ).format(
                    tmp=tmp,
                    cols=col_idents,
                    hdr=psql.Literal("true" if csv_has_header else "false"),
                    delim=psql.Literal(csv_delimiter),
                )

                # COPY into the staging table
                with _open_maybe_gz(src_path, "rt") as fh:
                    with cur.copy(copy_sql) as cp:
                        for chunk in iter(lambda: fh.read(1024 * 1024), ""):
                            if not chunk:
                                break
                            cp.write(chunk)

                # Upsert from staging
                insert_sql = (
                    psql.SQL("INSERT INTO {t} ({cols}) ")
                    + psql.SQL("SELECT {cols} FROM {tmp} ")
                    + psql.SQL("ON CONFLICT ({conflict}) DO UPDATE SET {set_list}")
                ).format(
                    t=psql.Identifier(target),
                    cols=col_idents,
                    tmp=tmp,
                    conflict=conflict_idents,
                    set_list=set_list,
                )

                cur.execute(insert_sql)
                affected = cur.rowcount or 0

                # Analyze improved plans after large loads
                cur.execute(psql.SQL("ANALYZE {t}").format(t=psql.Identifier(target)))

        return affected

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
            vendor=vendor,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            cols=preset.cols,
        )
