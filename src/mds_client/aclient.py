from __future__ import annotations

import asyncio
import csv
import gzip
import io
import sys
from typing import AsyncIterator, Iterable, Sequence, TypedDict

import psycopg
from psycopg import sql as psql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .sql import (
    TABLE_PRESETS,
)

_CHUNK = 1024 * 1024  # 1MB chunks for streaming


def _open_maybe_gz_write(path: str):
    """Return a binary file-like for writing (stdout if '-')."""
    if path == "-":
        # write to stdout (binary)
        return sys.stdout.buffer, False  # (fh, close_when_done)
    if path.endswith(".gz"):
        return gzip.open(path, "wb"), True
    return open(path, "wb"), True


def _open_maybe_gz_read_text(path: str):
    """Return a text file-like for reading CSV/NDJSON (stdin if '-')."""
    if path == "-":
        # don't close user's stdin
        return io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8"), False
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8"), True
    return open(path, "rt", encoding="utf-8"), True


async def _aiter_text_chunks(fh: io.TextIOBase, size: int = _CHUNK) -> AsyncIterator[str]:
    """Async generator yielding text chunks from a file-like using a thread offload."""
    while True:
        chunk = await asyncio.to_thread(fh.read, size)
        if not chunk:
            break
        yield chunk


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


class AMDSConfig(TypedDict, total=False):
    dsn: str
    tenant_id: str
    app_name: str
    statement_timeout_ms: int
    pool_max: int
    write_mode: str  # "auto" | "executemany" | "copy"   (async: no execute_values)
    copy_min_rows: int


DEFAULTS: AMDSConfig = {
    "pool_max": 10,
    "write_mode": "auto",
    "copy_min_rows": 5000,
}


class AMDS:
    def __init__(self, cfg: AMDSConfig):
        self.cfg: AMDSConfig = {**DEFAULTS, **(cfg or {})}
        if "dsn" not in self.cfg:
            raise ValueError("dsn required")
        # Create pool without auto-opening (fixes deprecation warning)
        self.pool = AsyncConnectionPool(
            conninfo=self.cfg["dsn"],
            max_size=self.cfg["pool_max"],
            kwargs={"autocommit": False},
            open=False,  # Never auto-open in constructor
        )
        self._connection_preparator = self._prepare_async_conn
        self.tenant_id = self.cfg.get("tenant_id")
        self.statement_timeout_ms = self.cfg.get("statement_timeout_ms")
        self.app_name = self.cfg.get("app_name")
        self._pool_opened = False

    async def __aenter__(self):
        await self.aopen()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.aclose()

    async def aopen(self) -> None:
        """Explicitly open the connection pool."""
        if not self._pool_opened:
            await self.pool.open(wait=True, timeout=5.0)
            self._pool_opened = True

    async def aclose(self) -> None:
        """Close the connection pool with proper cleanup."""
        if self._pool_opened:
            from .runtime import shutdown_with_timeout

            await shutdown_with_timeout(self.pool, timeout=1.0)
            self._pool_opened = False

    async def _prepare_async_conn(self, conn):
        """Prepare connection with app name and timeouts."""
        # Note: app.tenant_id parameter not supported in this database
        # Tenant isolation is handled via RLS policies instead
        if self.app_name:
            await conn.execute("SET application_name = %s", (self.app_name,))
        if self.statement_timeout_ms:
            await conn.execute("SET statement_timeout = %s", (self.statement_timeout_ms,))

    async def _conn(self):
        """Get connection with pre-configured tenant, app name, and timeouts."""
        # Ensure pool is opened
        await self.aopen()

        async with self.pool.connection() as conn:
            # Apply connection preparation
            await self._prepare_async_conn(conn)
            yield conn

    # ---------- health / meta ----------

    async def health(self) -> bool:
        async for conn in self._conn():
            await conn.execute("SELECT 1")
            return True

    async def schema_version(self) -> str | None:
        async for conn in self._conn():
            try:
                cur = await conn.execute("SELECT version_num FROM alembic_version LIMIT 1")
                row = await cur.fetchone()
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
                out.append(r.model_dump(exclude_none=True))
            elif isinstance(r, dict):
                out.append({k: v for k, v in r.items() if v is not None})
            else:
                out.append({k: v for k, v in vars(r).items() if v is not None})
        return out

    def _write_mode(self, nrows: int) -> str:
        mode = (self.cfg.get("write_mode") or "auto").lower()
        if mode != "auto":
            return mode
        if nrows >= int(self.cfg["copy_min_rows"]):
            return "copy"
        return "executemany"

    async def _copy_from_memory_csv(
        self, conn: psycopg.AsyncConnection, table: str, cols: Sequence[str], rows: Sequence[dict]
    ):
        sio = io.StringIO()
        writer = csv.DictWriter(sio, fieldnames=list(cols))
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r.get(c) for c in cols})
        sio.seek(0)
        async with (
            conn.cursor() as cur,
            cur.copy(
                psql.SQL("COPY {} ({}) FROM STDIN WITH CSV HEADER").format(
                    psql.Identifier(table),
                    psql.SQL(", ").join(psql.Identifier(c) for c in cols),
                )
            ) as cp,
        ):
            await cp.write(sio.read())

    async def _upsert(self, table: str, rows: Iterable[object]) -> int:
        preset = TABLE_PRESETS[table]
        cols, conflict, update = preset.cols, preset.conflict, preset.update
        sql_stmt = upsert_statement(table, cols, conflict, update)
        data = self._coerce_rows(rows)
        if not data:
            return 0

        async for conn in self._conn():
            async with conn.cursor(row_factory=dict_row) as cur:
                mode = self._write_mode(len(data))
                if mode == "executemany":
                    await cur.executemany(sql_stmt, data)
                elif mode == "copy":
                    temp = psql.Identifier(f"tmp_{table}_copy")
                    await cur.execute(
                        psql.SQL(
                            "CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS) ON COMMIT DROP"
                        ).format(temp, psql.Identifier(table))
                    )
                    await self._copy_from_memory_csv(conn, temp.string, cols, data)
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
                            for c in update
                        ),
                    )
                    await cur.execute(ins)
                else:
                    raise ValueError(f"unknown write_mode {mode}")
            await conn.commit()
        return len(data)

    # ---------- typed upserts ----------

    async def upsert_bars(self, rows: Sequence[object]) -> int:
        return await self._upsert("bars", rows)

    async def upsert_fundamentals(self, rows: Sequence[object]) -> int:
        return await self._upsert("fundamentals", rows)

    async def upsert_news(self, rows: Sequence[object]) -> int:
        return await self._upsert("news", rows)

    async def upsert_options(self, rows: Sequence[object]) -> int:
        return await self._upsert("options_snap", rows)

    # ---------- reads ----------

    async def latest_prices(self, symbols: Iterable[str], vendor: str) -> list[dict]:
        if not self.tenant_id:
            raise ValueError("tenant_id required for latest_prices()")
        q = latest_prices_select(symbols, vendor, self.tenant_id)
        async for conn in self._conn():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(q)
                return list(await cur.fetchall())

    async def bars_window(
        self, *, symbol: str, timeframe: str, start: str, end: str, vendor: str
    ) -> list[dict]:
        q = bars_window_select(
            symbol=symbol, timeframe=timeframe, start=start, end=end, vendor=vendor
        )
        async for conn in self._conn():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(q)
                return list(await cur.fetchall())

    # ---------- COPY export (CSV / NDJSON) ----------

    async def copy_out_csv(self, *, select_sql: psql.Composed, out_path: str) -> int:
        copy_sql = copy_to_stdout_csv(select_sql)
        writer = gzip.open(out_path, "wb") if out_path.endswith(".gz") else open(out_path, "wb")
        try:
            async for conn in self._conn():
                async with conn.cursor() as cur, cur.copy(copy_sql) as cp:
                    n = 0
                    while True:
                        chunk = await cp.read()
                        if not chunk:
                            break
                        writer.write(chunk)
                        n += len(chunk)
                    return n
        finally:
            writer.close()

    async def copy_out_ndjson_async(self, *, select_sql: psql.SQL, out_path: str) -> int:
        """
        COPY (SELECT to_jsonb(...)) TO STDOUT into NDJSON file (or stdout if '-').
        Returns the total bytes written. Gzip supported via *.gz.
        """
        total = 0
        fh, should_close = _open_maybe_gz_write(out_path)
        try:
            async with self.pool.connection() as conn:
                async with conn.cursor() as cur:
                    copy_sql = psql.SQL("COPY ({sel}) TO STDOUT").format(sel=select_sql)
                    async with cur.copy(copy_sql) as cp:
                        # cp.read() yields bytes (server text stream)
                        while True:
                            data = await cp.read()
                            if not data:
                                break
                            # write bytes without decoding
                            await asyncio.to_thread(fh.write, data)
                            total += len(data)
            # flush to disk if needed
            await asyncio.to_thread(fh.flush)
        finally:
            if should_close:
                try:
                    fh.close()
                except Exception:
                    pass
        return total

    async def copy_restore_csv_async(
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
        Restore CSV (optionally .gz or stdin '-') using a TEMP staging table,
        then INSERT ... ON CONFLICT DO UPDATE into {target}.
        Returns affected row count.
        """
        col_idents = psql.SQL(", ").join(psql.Identifier(c) for c in cols)
        conflict_idents = psql.SQL(", ").join(psql.Identifier(c) for c in conflict_cols)
        set_list = psql.SQL(", ").join(
            psql.SQL("{c}=EXCLUDED.{c}").format(c=psql.Identifier(c)) for c in update_cols
        )
        tmp = psql.Identifier(f"_staging_{target}")

        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                # Create staging table (inherits defaults for consistent types)
                await cur.execute(
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

                fh, should_close = _open_maybe_gz_read_text(src_path)
                try:
                    async with cur.copy(copy_sql) as cp:
                        async for chunk in _aiter_text_chunks(fh):
                            await cp.write(chunk)
                finally:
                    if should_close:
                        try:
                            fh.close()
                        except Exception:
                            pass

                # Upsert from staging into target
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

                await cur.execute(insert_sql)
                affected = cur.rowcount or 0

                # Keep planner fresh after heavy loads
                await cur.execute(psql.SQL("ANALYZE {t}").format(t=psql.Identifier(target)))

        return affected
