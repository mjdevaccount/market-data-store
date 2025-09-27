from __future__ import annotations

import csv
import gzip
import io
from typing import Iterable, Sequence, TypedDict

import psycopg
from psycopg import sql as psql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .sql import (
    TABLE_PRESETS,
)


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
        self.pool = AsyncConnectionPool(
            conninfo=self.cfg["dsn"],
            max_size=self.cfg["pool_max"],
            kwargs={"autocommit": False},
        )
        self.tenant_id = self.cfg.get("tenant_id")
        self.statement_timeout_ms = self.cfg.get("statement_timeout_ms")
        self.app_name = self.cfg.get("app_name")

    async def aclose(self) -> None:
        await self.pool.close()

    async def _conn(self):
        async with self.pool.connection() as conn:
            if self.app_name:
                await conn.execute(
                    psql.SQL("SET application_name = {}").format(psql.Literal(self.app_name))
                )
            if self.statement_timeout_ms:
                await conn.execute(
                    psql.SQL("SET statement_timeout = {}").format(
                        psql.Literal(int(self.statement_timeout_ms))
                    )
                )
            if self.tenant_id:
                await conn.execute(
                    psql.SQL("SET LOCAL app.tenant_id = {}").format(psql.Literal(self.tenant_id))
                )
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
        cols, conflict, update = preset["cols"], preset["conflict"], preset["update"]
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

    async def copy_out_ndjson(self, *, select_sql: psql.Composed, out_path: str) -> int:
        copy_sql = copy_to_stdout_ndjson(select_sql)
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
                        writer.write(b"\n")
                        n += len(chunk) + 1
                    return n
        finally:
            writer.close()
