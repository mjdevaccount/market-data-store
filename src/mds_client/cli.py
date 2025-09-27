from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Optional

import typer

from . import MDS, AMDS, BatchProcessor, AsyncBatchProcessor, BatchConfig
from .models import Bar, Fundamentals, News, OptionSnap
from .utils import iter_ndjson, coerce_model
from .client import TABLE_PRESETS
from psycopg import sql as psql
import sys
import re
from pathlib import Path

app = typer.Typer(help="mds_client operational CLI")

# ---------------------------
# Common options
# ---------------------------


def dsn_opt() -> str:
    return typer.Option(..., "--dsn", envvar="MDS_DSN", help="PostgreSQL DSN")


def tenant_opt() -> str:
    return typer.Option(..., "--tenant-id", envvar="MDS_TENANT_ID", help="Tenant UUID for RLS")


def vendor_opt() -> Optional[str]:
    return typer.Option(None, "--vendor", help="Data vendor (e.g. ibkr, reuters)")


def max_rows_opt(default=1000) -> int:
    return typer.Option(default, "--max-rows", help="Flush when pending rows reach this size")


def max_ms_opt(default=5000) -> int:
    return typer.Option(default, "--max-ms", help="Flush when this many ms elapse since last flush")


def max_bytes_opt(default=1_048_576) -> int:
    return typer.Option(default, "--max-bytes", help="Flush when pending bytes reach this size")


# ---------------------------
# Health / Schema / Reads
# ---------------------------


@app.command("ping")
def ping(dsn: str = dsn_opt(), tenant_id: str = tenant_opt()):
    mds = MDS({"dsn": dsn, "tenant_id": tenant_id})
    ok = mds.health()
    typer.echo(json.dumps({"ok": ok}, indent=2))


@app.command("schema-version")
def schema_version(dsn: str = dsn_opt(), tenant_id: str = tenant_opt()):
    mds = MDS({"dsn": dsn, "tenant_id": tenant_id})
    ver = mds.schema_version()
    typer.echo(json.dumps({"schema_version": ver}, indent=2))


@app.command("latest-prices")
def latest_prices(
    symbols: str = typer.Argument(..., help="Comma-separated symbols"),
    vendor: str = typer.Option(..., "--vendor", help="Data vendor"),
    dsn: str = dsn_opt(),
    tenant_id: str = tenant_opt(),
):
    mds = MDS({"dsn": dsn, "tenant_id": tenant_id})
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    rows = mds.latest_prices(syms, vendor=vendor)
    for r in rows:
        typer.echo(json.dumps(r.model_dump(), default=str))


# ---------------------------
# Write commands (sync)
# ---------------------------


@app.command("write-bar")
def write_bar(
    symbol: str = typer.Option(...),
    timeframe: str = typer.Option(...),
    ts: datetime = typer.Option(..., formats=["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"]),
    close_price: Optional[float] = typer.Option(None),
    open_price: Optional[float] = typer.Option(None),
    high_price: Optional[float] = typer.Option(None),
    low_price: Optional[float] = typer.Option(None),
    volume: Optional[int] = typer.Option(None),
    vendor: str = typer.Option(..., "--vendor"),
    dsn: str = dsn_opt(),
    tenant_id: str = tenant_opt(),
):
    mds = MDS({"dsn": dsn, "tenant_id": tenant_id})
    bar = Bar(
        tenant_id=tenant_id,
        vendor=vendor,
        symbol=symbol,
        timeframe=timeframe,
        ts=ts,
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        close_price=close_price,
        volume=volume,
    )
    mds.upsert_bars([bar])
    typer.echo("ok")


@app.command("write-fundamental")
def write_fundamental(
    symbol: str = typer.Option(...),
    asof: datetime = typer.Option(
        ..., formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"]
    ),
    total_assets: Optional[float] = typer.Option(None),
    total_liabilities: Optional[float] = typer.Option(None),
    net_income: Optional[float] = typer.Option(None),
    eps: Optional[float] = typer.Option(None),
    vendor: str = typer.Option(..., "--vendor"),
    dsn: str = dsn_opt(),
    tenant_id: str = tenant_opt(),
):
    mds = MDS({"dsn": dsn, "tenant_id": tenant_id})
    row = Fundamentals(
        tenant_id=tenant_id,
        vendor=vendor,
        symbol=symbol,
        asof=asof,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        net_income=net_income,
        eps=eps,
    )
    mds.upsert_fundamentals([row])
    typer.echo("ok")


@app.command("write-news")
def write_news(
    title: str = typer.Option(...),
    published_at: datetime = typer.Option(
        ..., formats=["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"]
    ),
    symbol: Optional[str] = typer.Option(None),
    url: Optional[str] = typer.Option(None),
    sentiment_score: Optional[float] = typer.Option(None),
    vendor: str = typer.Option(..., "--vendor"),
    dsn: str = dsn_opt(),
    tenant_id: str = tenant_opt(),
):
    mds = MDS({"dsn": dsn, "tenant_id": tenant_id})
    row = News(
        tenant_id=tenant_id,
        vendor=vendor,
        title=title,
        published_at=published_at,
        symbol=symbol,
        url=url,
        sentiment_score=sentiment_score,
    )
    mds.upsert_news([row])
    typer.echo("ok")


@app.command("write-option")
def write_option(
    symbol: str = typer.Option(...),
    expiry: str = typer.Option(..., help="YYYY-MM-DD"),
    option_type: str = typer.Option(..., help="'C' or 'P'"),
    strike: float = typer.Option(...),
    ts: datetime = typer.Option(..., formats=["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"]),
    iv: Optional[float] = typer.Option(None),
    delta: Optional[float] = typer.Option(None),
    gamma: Optional[float] = typer.Option(None),
    oi: Optional[int] = typer.Option(None),
    volume: Optional[int] = typer.Option(None),
    spot: Optional[float] = typer.Option(None),
    vendor: str = typer.Option(..., "--vendor"),
    dsn: str = dsn_opt(),
    tenant_id: str = tenant_opt(),
):
    from datetime import date

    y, m, d = [int(x) for x in expiry.split("-")]
    mds = MDS({"dsn": dsn, "tenant_id": tenant_id})
    row = OptionSnap(
        tenant_id=tenant_id,
        vendor=vendor,
        symbol=symbol,
        expiry=date(y, m, d),
        option_type=option_type,
        strike=strike,
        ts=ts,
        iv=iv,
        delta=delta,
        gamma=gamma,
        oi=oi,
        volume=volume,
        spot=spot,
    )
    mds.upsert_options([row])
    typer.echo("ok")


# ---------------------------
# NDJSON ingest
# ---------------------------


@app.command("ingest-ndjson")
def ingest_ndjson(
    kind: str = typer.Argument(..., help="bars|fundamentals|news|options"),
    path: str = typer.Argument(..., help="File path or '-' for stdin (.gz ok)"),
    dsn: str = dsn_opt(),
    tenant_id: str = tenant_opt(),
    max_rows: int = max_rows_opt(1000),
    max_ms: int = max_ms_opt(5000),
    max_bytes: int = max_bytes_opt(1_048_576),
):
    kind_l = kind.lower()
    if kind_l not in ("bars", "fundamentals", "news", "options"):
        raise typer.BadParameter("kind must be one of: bars, fundamentals, news, options")

    cfg = BatchConfig(max_rows=max_rows, max_ms=max_ms, max_bytes=max_bytes)
    mds = MDS({"dsn": dsn, "tenant_id": tenant_id})
    bp = BatchProcessor(mds, cfg)

    add_fn = {
        "bars": bp.add_bar,
        "fundamentals": bp.add_fundamental,
        "news": bp.add_news,
        "options": bp.add_option,
    }[kind_l]

    n = 0
    for obj in iter_ndjson(path):
        row = coerce_model(kind_l, obj)
        add_fn(row)
        n += 1

    counts = bp.flush()
    typer.echo(json.dumps({"ingested": n, "flushed": counts}, default=str, indent=2))


@app.command("ingest-ndjson-async")
def ingest_ndjson_async(
    kind: str = typer.Argument(..., help="bars|fundamentals|news|options"),
    path: str = typer.Argument(...),
    dsn: str = dsn_opt(),
    tenant_id: str = tenant_opt(),
    max_rows: int = max_rows_opt(1000),
    max_ms: int = max_ms_opt(5000),
    max_bytes: int = max_bytes_opt(1_048_576),
):
    asyncio.run(_ingest_ndjson_async(kind, path, dsn, tenant_id, max_rows, max_ms, max_bytes))


async def _ingest_ndjson_async(
    kind: str, path: str, dsn: str, tenant_id: str, max_rows: int, max_ms: int, max_bytes: int
):
    kind_l = kind.lower()
    if kind_l not in ("bars", "fundamentals", "news", "options"):
        raise typer.BadParameter("kind must be one of: bars, fundamentals, news, options")

    cfg = BatchConfig(max_rows=max_rows, max_ms=max_ms, max_bytes=max_bytes)
    amds = AMDS({"dsn": dsn, "tenant_id": tenant_id, "pool_max": 10})
    async with AsyncBatchProcessor(amds, cfg) as bp:
        add_fn = {
            "bars": bp.add_bar,
            "fundamentals": bp.add_fundamental,
            "news": bp.add_news,
            "options": bp.add_option,
        }[kind_l]
        n = 0
        for obj in iter_ndjson(path):
            await add_fn(coerce_model(kind_l, obj))
            n += 1
    # Auto-flush on exit
    typer.echo(json.dumps({"ingested": n, "flushed": "auto"}, default=str, indent=2))


# ---------------------------
# Jobs outbox (simple helper)
# ---------------------------


@app.command("enqueue-job")
def enqueue_job(
    idempotency_key: str = typer.Option(..., "--idempotency-key"),
    job_type: str = typer.Option(..., "--job-type"),
    payload: str = typer.Option(..., "--payload", help="JSON string"),
    priority: str = typer.Option("medium", "--priority"),
    dsn: str = dsn_opt(),
    tenant_id: str = tenant_opt(),
):
    """Minimal helper that inserts into jobs_outbox with conflict-free idempotency."""
    mds = MDS({"dsn": dsn, "tenant_id": tenant_id})
    mds.enqueue_job(
        idempotency_key=idempotency_key,
        job_type=job_type,
        payload=json.loads(payload),
        priority=priority,
    )
    typer.echo("ok")


# ---------------------------
# Backup/Export/Import commands
# ---------------------------


@app.command("dump")
def dump(
    table: str = typer.Argument(..., help="bars|fundamentals|news|options_snap"),
    out_path: str = typer.Argument(..., help="Output file (.csv or .csv.gz) or '-' for stdout"),
    dsn: str = dsn_opt(),
    tenant_id: str = tenant_opt(),
    vendor: str = typer.Option(None, "--vendor", help="Filter by vendor"),
    symbol: str = typer.Option(None, "--symbol", help="Filter by symbol"),
    timeframe: str = typer.Option(None, "--timeframe", help="Filter by timeframe"),
    start: str = typer.Option(None, "--start", help="Start time (ISO format)"),
    end: str = typer.Option(None, "--end", help="End time (ISO format)"),
):
    """Export table data to CSV with optional filters."""
    if table not in TABLE_PRESETS:
        raise typer.BadParameter(f"table must be one of: {', '.join(TABLE_PRESETS.keys())}")

    mds = MDS({"dsn": dsn, "tenant_id": tenant_id})
    cols = TABLE_PRESETS[table]["cols"]
    parts = [
        psql.SQL("SELECT {} FROM {}").format(
            psql.SQL(", ").join(psql.Identifier(c) for c in cols),
            psql.Identifier(table),
        )
    ]
    wh = []
    if vendor:
        wh.append(psql.SQL("vendor = {}").format(psql.Literal(vendor)))
    if symbol:
        wh.append(psql.SQL("symbol = {}").format(psql.Literal(symbol.upper())))
    if timeframe and "timeframe" in cols:
        wh.append(psql.SQL("timeframe = {}").format(psql.Literal(timeframe)))
    # time col name varies per table
    tcol = "ts" if "ts" in cols else ("asof" if "asof" in cols else "published_at")
    if start:
        wh.append(psql.SQL("{} >= {}").format(psql.Identifier(tcol), psql.Literal(start)))
    if end:
        wh.append(psql.SQL("{} < {}").format(psql.Identifier(tcol), psql.Literal(end)))
    if wh:
        parts.append(psql.SQL("WHERE ") + psql.SQL(" AND ").join(wh))
    parts.append(psql.SQL("ORDER BY {}").format(psql.Identifier(tcol)))
    sel = psql.SQL(" ").join(parts)

    if out_path == "-":
        import sys

        mds.copy_out_csv(select_sql=sel, out=sys.stdout.buffer)
    else:
        mds.copy_out_csv(select_sql=sel, out_path=out_path)
    typer.echo("ok")


@app.command("restore")
def restore(
    table: str = typer.Argument(..., help="bars|fundamentals|news|options_snap"),
    src_path: str = typer.Argument(..., help="Input .csv or .csv.gz (must have HEADER)"),
    dsn: str = dsn_opt(),
    tenant_id: str = tenant_opt(),
):
    """Import table data from CSV with upsert semantics."""
    if table not in TABLE_PRESETS:
        raise typer.BadParameter(f"table must be one of: {', '.join(TABLE_PRESETS.keys())}")

    mds = MDS({"dsn": dsn, "tenant_id": tenant_id})
    p = TABLE_PRESETS[table]
    n = mds.copy_restore_csv(
        target=table,
        cols=p["cols"],
        conflict_cols=p["conflict"],
        update_cols=p["update"],
        src_path=src_path,
    )
    typer.echo(f"upserted {n} rows")


# ---------------------------
# NDJSON dump helpers
# ---------------------------

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe(val: str | None, default: str) -> str:
    if not val:
        return default
    return _SAFE.sub("_", val)


def _render_template(
    template: str,
    *,
    table: str,
    vendor: str | None,
    symbol: str | None,
    timeframe: str | None,
    start: str | None,
    end: str | None,
) -> str:
    """Render filename template and ensure .ndjson.gz suffix."""
    # Prepare safe mapping
    mapping = {
        "table": _safe(table, "table"),
        "vendor": _safe(vendor, "ALL"),
        "symbol": _safe(symbol.upper() if symbol else None, "ALL"),
        "timeframe": _safe(timeframe, "ALL"),
        "start": _safe(start, "MIN"),
        "end": _safe(end, "MAX"),
    }
    path = template.format(**mapping)
    if not (path.endswith(".ndjson") or path.endswith(".ndjson.gz")):
        path += ".ndjson.gz"
    # Ensure parent dir exists
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return path


def _build_ndjson_select(
    table: str,
    cols: list[str],
    vendor: str | None,
    symbol: str | None,
    timeframe: str | None,
    start: str | None,
    end: str | None,
) -> psql.Composed:
    parts: list[psql.Composed] = [
        psql.SQL("SELECT {} FROM {}").format(
            psql.SQL(", ").join(psql.Identifier(c) for c in cols),
            psql.Identifier(table),
        )
    ]
    wh: list[psql.Composed] = []
    if vendor:
        wh.append(psql.SQL("vendor = {}").format(psql.Literal(vendor)))
    if symbol and "symbol" in cols:
        wh.append(psql.SQL("symbol = {}").format(psql.Literal(symbol.upper())))
    if timeframe and "timeframe" in cols:
        wh.append(psql.SQL("timeframe = {}").format(psql.Literal(timeframe)))

    # time column per table
    tcol = "ts" if "ts" in cols else ("asof" if "asof" in cols else "published_at")
    if start:
        wh.append(psql.SQL("{} >= {}").format(psql.Identifier(tcol), psql.Literal(start)))
    if end:
        wh.append(psql.SQL("{} < {}").format(psql.Identifier(tcol), psql.Literal(end)))

    if wh:
        parts.append(psql.SQL("WHERE ") + psql.SQL(" AND ").join(wh))
    parts.append(psql.SQL("ORDER BY {}").format(psql.Identifier(tcol)))
    return psql.SQL(" ").join(parts)


@app.command("dump-ndjson")
def dump_ndjson(
    table: str = typer.Argument(..., help="bars|fundamentals|news|options_snap"),
    out_path: str = typer.Argument(
        ..., help="Output file (.ndjson or .ndjson.gz) or '-' for stdout"
    ),
    dsn: str = dsn_opt(),
    tenant_id: str = tenant_opt(),
    vendor: str = typer.Option(None, "--vendor", help="Filter by vendor"),
    symbol: str = typer.Option(None, "--symbol", help="Filter by symbol"),
    timeframe: str = typer.Option(None, "--timeframe", help="Filter by timeframe"),
    start: str = typer.Option(None, "--start", help="ISO start (inclusive)"),
    end: str = typer.Option(None, "--end", help="ISO end (exclusive)"),
):
    """
    Stream NDJSON (one JSON object per line) for the selected rows.
    Round-trips with `mds ingest-ndjson`.
    """
    if table not in TABLE_PRESETS:
        raise typer.BadParameter(f"table must be one of: {', '.join(TABLE_PRESETS.keys())}")

    presets = TABLE_PRESETS[table]  # reuse same column set used by ingest
    sel = _build_ndjson_select(table, presets["cols"], vendor, symbol, timeframe, start, end)

    mds = MDS({"dsn": dsn, "tenant_id": tenant_id})
    if out_path == "-":
        bytes_written = mds.copy_out_ndjson(select_sql=sel, out=sys.stdout.buffer)
    else:
        bytes_written = mds.copy_out_ndjson(select_sql=sel, out_path=out_path)
    typer.echo(f"wrote {bytes_written} bytes")


@app.command("dump-ndjson-async")
def dump_ndjson_async(
    table: str = typer.Argument(..., help="bars|fundamentals|news|options_snap"),
    out_path: str = typer.Argument(
        ..., help="Output file (.ndjson or .ndjson.gz) or '-' for stdout"
    ),
    dsn: str = dsn_opt(),
    tenant_id: str = tenant_opt(),
    vendor: str = typer.Option(None, "--vendor", help="Filter by vendor"),
    symbol: str = typer.Option(None, "--symbol", help="Filter by symbol"),
    timeframe: str = typer.Option(None, "--timeframe", help="Filter by timeframe"),
    start: str = typer.Option(None, "--start", help="ISO start (inclusive)"),
    end: str = typer.Option(None, "--end", help="ISO end (exclusive)"),
):
    """
    Async NDJSON dump (uses AMDS). Good for very large exports where you want async I/O.
    """
    import asyncio

    if table not in TABLE_PRESETS:
        raise typer.BadParameter(f"table must be one of: {', '.join(TABLE_PRESETS.keys())}")

    presets = TABLE_PRESETS[table]
    sel = _build_ndjson_select(table, presets["cols"], vendor, symbol, timeframe, start, end)

    async def _run():
        amds = AMDS({"dsn": dsn, "tenant_id": tenant_id})
        if out_path == "-":
            bytes_written = await amds.copy_out_ndjson(select_sql=sel, out=sys.stdout.buffer)
        else:
            bytes_written = await amds.copy_out_ndjson(select_sql=sel, out_path=out_path)
        typer.echo(f"wrote {bytes_written} bytes")

    asyncio.run(_run())


@app.command("dump-ndjson-all")
def dump_ndjson_all(
    out_template: str = typer.Argument(
        "./{table}-{symbol}-{start}-{end}.ndjson.gz",
        help="Naming template. Vars: {table},{vendor},{symbol},{timeframe},{start},{end}",
    ),
    dsn: str = dsn_opt(),
    tenant_id: str = tenant_opt(),
    vendor: str | None = typer.Option(None, help="Filter vendor"),
    symbol: str | None = typer.Option(None, help="Filter symbol"),
    timeframe: str | None = typer.Option(None, help="Filter timeframe (for bars only)"),
    start: str | None = typer.Option(None, help="ISO start (inclusive)"),
    end: str | None = typer.Option(None, help="ISO end (exclusive)"),
):
    """
    Dump NDJSON for ALL tables (bars, fundamentals, news, options_snap) to multiple files.
    Files are named using the provided template and gzip-compressed by default.
    """
    tables = ["bars", "fundamentals", "news", "options_snap"]
    mds = MDS({"dsn": dsn, "tenant_id": tenant_id})

    total = 0
    for tbl in tables:
        presets = TABLE_PRESETS[tbl]
        sel = _build_ndjson_select(tbl, presets["cols"], vendor, symbol, timeframe, start, end)
        out_path = _render_template(
            out_template,
            table=tbl,
            vendor=vendor,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
        )
        bytes_written = mds.copy_out_ndjson(select_sql=sel, out_path=out_path)
        total += bytes_written
        typer.echo(f"{tbl}: wrote {bytes_written} bytes → {out_path}")
    typer.echo(f"TOTAL: {total} bytes")


@app.command("dump-ndjson-async-all")
def dump_ndjson_async_all(
    out_template: str = typer.Argument(
        "./{table}-{symbol}-{start}-{end}.ndjson.gz",
        help="Naming template. Vars: {table},{vendor},{symbol},{timeframe},{start},{end}",
    ),
    dsn: str = dsn_opt(),
    tenant_id: str = tenant_opt(),
    vendor: str | None = typer.Option(None, help="Filter vendor"),
    symbol: str | None = typer.Option(None, help="Filter symbol"),
    timeframe: str | None = typer.Option(None, help="Filter timeframe (for bars only)"),
    start: str | None = typer.Option(None, help="ISO start (inclusive)"),
    end: str | None = typer.Option(None, help="ISO end (exclusive)"),
):
    """
    Async version: dump NDJSON for ALL tables using AMDS (good for very large exports).
    """
    import asyncio

    async def _run():
        tables = ["bars", "fundamentals", "news", "options_snap"]
        amds = AMDS({"dsn": dsn, "tenant_id": tenant_id})
        total = 0
        for tbl in tables:
            presets = TABLE_PRESETS[tbl]
            sel = _build_ndjson_select(tbl, presets["cols"], vendor, symbol, timeframe, start, end)
            out_path = _render_template(
                out_template,
                table=tbl,
                vendor=vendor,
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
            )
            bytes_written = await amds.copy_out_ndjson(select_sql=sel, out_path=out_path)
            total += bytes_written
            typer.echo(f"{tbl}: wrote {bytes_written} bytes → {out_path}")
        typer.echo(f"TOTAL: {total} bytes")

    asyncio.run(_run())


if __name__ == "__main__":
    app()
