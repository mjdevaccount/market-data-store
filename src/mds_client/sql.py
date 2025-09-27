from __future__ import annotations

from typing import Iterable, Sequence
from psycopg import sql as psql

# Canonical column sets + conflict/update specs (match your Timescale schema)
TABLE_PRESETS: dict[str, dict] = {
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
        "time_col": "ts",
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
        "time_col": "asof",
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
        "time_col": "published_at",
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
        "conflict": ["ts", "tenant_id", "vendor", "symbol", "expiry", "option_type", "strike"],
        "update": ["iv", "delta", "gamma", "oi", "volume", "spot"],
        "time_col": "ts",
    },
}


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


def build_ndjson_select(
    table: str,
    cols: Sequence[str],
    *,
    vendor: str | None,
    symbol: str | None,
    timeframe: str | None,
    start: str | None,
    end: str | None,
) -> psql.Composed:
    """
    Build: SELECT to_jsonb(t) FROM (SELECT <cols> FROM table WHERE ... ORDER BY <time>) t
    All filters are optional; symbol uppercased if provided.
    """
    preset = TABLE_PRESETS[table]
    time_col = preset["time_col"]

    base_cols = psql.SQL(", ").join(psql.Identifier(c) for c in cols)
    q = psql.SQL("SELECT {} FROM {}").format(base_cols, psql.Identifier(table))

    wheres: list[psql.Composed] = []
    if vendor:
        wheres.append(psql.SQL("vendor = {}").format(psql.Literal(vendor)))
    if symbol and "symbol" in cols:
        wheres.append(psql.SQL("symbol = {}").format(psql.Literal(symbol.upper())))
    if timeframe and "timeframe" in cols:
        wheres.append(psql.SQL("timeframe = {}").format(psql.Literal(timeframe)))
    if start:
        wheres.append(psql.SQL("{} >= {}").format(psql.Identifier(time_col), psql.Literal(start)))
    if end:
        wheres.append(psql.SQL("{} < {}").format(psql.Identifier(time_col), psql.Literal(end)))

    if wheres:
        q = psql.SQL("{} WHERE {}").format(q, psql.SQL(" AND ").join(wheres))

    q = psql.SQL("{} ORDER BY {}").format(q, psql.Identifier(time_col))
    wrapped = psql.SQL("SELECT to_jsonb(t) FROM ({}) t").format(q)
    return wrapped


def copy_to_stdout_ndjson(select_json_sql: psql.Composed) -> psql.Composed:
    # Expect a SELECT producing a single json/jsonb column per row.
    return psql.SQL("COPY ({}) TO STDOUT").format(select_json_sql)


def copy_to_stdout_csv(select_sql: psql.Composed) -> psql.Composed:
    return psql.SQL("COPY ({}) TO STDOUT WITH CSV HEADER").format(select_sql)
