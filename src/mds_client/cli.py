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


if __name__ == "__main__":
    app()
