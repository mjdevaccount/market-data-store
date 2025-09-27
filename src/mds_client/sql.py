from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping, Optional

from psycopg import sql as psql


@dataclass(frozen=True)
class TablePreset:
    # Column order for SELECT/COPY/INSERT (no "id" to keep round-trips stable)
    cols: tuple[str, ...]
    # Conflict columns must match the table PK (time-first)
    conflict: tuple[str, ...]
    # Updatable (non-PK) columns for ON CONFLICT DO UPDATE
    update: tuple[str, ...]
    # Name of the time column for filters and ORDER BY
    time_col: str
    # Optional filterable columns present in this table
    filter_cols: tuple[str, ...] = ()


TABLE_PRESETS: dict[str, TablePreset] = {
    "bars": TablePreset(
        cols=(
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
        ),
        conflict=("ts", "tenant_id", "vendor", "symbol", "timeframe"),
        update=("open_price", "high_price", "low_price", "close_price", "volume"),
        time_col="ts",
        filter_cols=("vendor", "symbol", "timeframe"),
    ),
    "fundamentals": TablePreset(
        cols=(
            "asof",
            "tenant_id",
            "vendor",
            "symbol",
            "total_assets",
            "total_liabilities",
            "net_income",
            "eps",
        ),
        conflict=("asof", "tenant_id", "vendor", "symbol"),
        update=("total_assets", "total_liabilities", "net_income", "eps"),
        time_col="asof",
        filter_cols=("vendor", "symbol"),
    ),
    "news": TablePreset(
        cols=(
            "published_at",
            "tenant_id",
            "vendor",
            "symbol",
            "title",
            "url",
            "sentiment_score",
        ),
        # NOTE: PK = (published_at, tenant_id, vendor, id). We omit "id" from exports for stable round-trips.
        conflict=("published_at", "tenant_id", "vendor", "id"),
        update=("symbol", "title", "url", "sentiment_score"),
        time_col="published_at",
        filter_cols=("vendor", "symbol"),
    ),
    "options_snap": TablePreset(
        cols=(
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
        ),
        conflict=("ts", "tenant_id", "vendor", "symbol", "expiry", "option_type", "strike"),
        update=("iv", "delta", "gamma", "oi", "volume", "spot"),
        time_col="ts",
        filter_cols=("vendor", "symbol"),
    ),
}


def _lit(v) -> psql.SQL:
    """Safely literalize a value for SQL composition."""
    return psql.Literal(v)


def _ident(n: str) -> psql.Identifier:
    return psql.Identifier(n)


def build_ndjson_select(
    table: str,
    *,
    vendor: Optional[str] = None,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    start: Optional[datetime | str] = None,
    end: Optional[datetime | str] = None,
    cols: Optional[Iterable[str]] = None,
    extra_where: Optional[Mapping[str, object]] = None,
) -> psql.SQL:
    """
    Build a safe SELECT that emits one JSON doc per row via to_jsonb().
    Intended to be wrapped by COPY (...) TO STDOUT in dump-ndjson paths.

    Returns a psycopg.sql.Composed object (safe, quoted).
    """
    if table not in TABLE_PRESETS:
        raise ValueError(f"unknown table: {table}")

    preset = TABLE_PRESETS[table]
    use_cols = tuple(cols or preset.cols)

    # SELECT list
    sel_cols = psql.SQL(", ").join(_ident(c) for c in use_cols)

    # WHERE clauses
    wheres: list[psql.SQL] = [psql.SQL("1=1")]

    # Optional standard filters
    if vendor and "vendor" in preset.filter_cols:
        wheres.append(psql.SQL("{col} = {val}").format(col=_ident("vendor"), val=_lit(vendor)))
    if symbol and "symbol" in preset.filter_cols:
        wheres.append(psql.SQL("{col} = {val}").format(col=_ident("symbol"), val=_lit(symbol)))
    if timeframe and "timeframe" in preset.filter_cols:
        wheres.append(
            psql.SQL("{col} = {val}").format(col=_ident("timeframe"), val=_lit(timeframe))
        )

    # Time window
    ts = _ident(preset.time_col)
    if start is not None:
        wheres.append(psql.SQL("{ts} >= {v}").format(ts=ts, v=_lit(start)))
    if end is not None:
        wheres.append(psql.SQL("{ts} < {v}").format(ts=ts, v=_lit(end)))

    # Extra equality filters by name (if provided)
    if extra_where:
        for k, v in extra_where.items():
            wheres.append(psql.SQL("{col} = {val}").format(col=_ident(str(k)), val=_lit(v)))

    where_sql = psql.SQL(" AND ").join(wheres)

    # SELECT-to-JSON wrapper
    inner = psql.SQL("SELECT {cols} FROM {tbl} WHERE {where} ORDER BY {ts}").format(
        cols=sel_cols, tbl=_ident(table), where=where_sql, ts=ts
    )
    outer = psql.SQL("SELECT to_jsonb(t) FROM ({inner}) t").format(inner=inner)
    return outer
