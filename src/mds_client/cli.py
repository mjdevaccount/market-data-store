from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from . import MDS, AMDS
from .batch import BatchProcessor, AsyncBatchProcessor, BatchConfig
from .models import Bar, Fundamentals, News, OptionSnap
from .utils import iter_ndjson, coerce_model
from .sql import TABLE_PRESETS
from .runtime import boot_event_loop, shutdown_with_timeout
from .health import (
    check_health,
    check_health_with_retry,
    get_prometheus_metrics,
    get_metrics_summary,
)

app = typer.Typer(help="mds_client operational CLI")

# ---------------------------
# Common options
# ---------------------------


def dsn_opt() -> str:
    return typer.Option(..., "--dsn", envvar="MDS_DSN", help="PostgreSQL DSN")


def tenant_opt() -> str:
    return typer.Option(
        ...,
        "--tenant-id",
        envvar="MDS_TENANT_ID",
        help="Tenant UUID for RLS (tenants.id, not tenants.tenant_id)",
    )


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


@app.command("health")
def health_check(
    dsn: str = dsn_opt(),
    tenant_id: str = tenant_opt(),
    retry: bool = typer.Option(False, "--retry", help="Use retry logic for health check"),
    format: str = typer.Option("json", "--format", help="Output format: json, prometheus"),
):
    """Comprehensive database health check with metrics."""

    async def _health_check():
        amds = AMDS({"dsn": dsn, "tenant_id": tenant_id, "pool_max": 5})
        try:
            await amds.aopen()

            if retry:
                result = await check_health_with_retry(amds)
            else:
                result = await check_health(amds)

            if format == "prometheus":
                metrics = get_prometheus_metrics()
                if metrics:
                    typer.echo(metrics)
                else:
                    typer.echo(
                        "# Prometheus metrics not available (prometheus_client not installed)"
                    )
            else:
                typer.echo(json.dumps(result, indent=2, default=str))

        finally:
            await amds.aclose()

    asyncio.run(_health_check())


@app.command("metrics")
def metrics(
    format: str = typer.Option("json", "--format", help="Output format: json, prometheus"),
):
    """Get current metrics summary."""
    if format == "prometheus":
        metrics = get_prometheus_metrics()
        if metrics:
            typer.echo(metrics)
        else:
            typer.echo("# Prometheus metrics not available (prometheus_client not installed)")
    else:
        summary = get_metrics_summary()
        typer.echo(json.dumps(summary, indent=2, default=str))


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
        typer.echo(json.dumps(r, default=str))


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

    try:
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
    finally:
        # Ensure proper cleanup
        await shutdown_with_timeout(amds.pool)


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
    sel = mds.build_ndjson_select(
        table, vendor=vendor, symbol=symbol, timeframe=timeframe, start=start, end=end
    )
    nbytes = mds.copy_out_csv(select_sql=sel, out_path=out_path)
    typer.echo(f"wrote {nbytes} bytes")


@app.command("restore")
def restore(
    table: str = typer.Argument(..., help="bars|fundamentals|news|options_snap"),
    src_path: str = typer.Argument(..., help="Input file (.csv or .csv.gz)"),
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


# --- async restore CSV -------------------------------------------------------


async def _restore_csv_async_impl(
    table: str,
    src_path: Path,
    dsn: str,
    tenant_id: Optional[str],
    app_name: str,
    pool_max: int,
    delimiter: str,
    header: bool,
    null: str,
    temp_table_name: Optional[str],
) -> int:
    if table not in TABLE_PRESETS:
        typer.secho(
            f"Unknown table '{table}'. Valid: {', '.join(TABLE_PRESETS)}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)

    amds = AMDS(
        {
            "dsn": dsn,
            "tenant_id": tenant_id,
            "app_name": app_name,
            "pool_max": pool_max,
        }
    )
    preset = TABLE_PRESETS[table]
    try:
        n = await amds.copy_restore_csv_async(
            target=table,
            cols=preset.cols,
            conflict_cols=preset.conflict,
            update_cols=preset.update,
            src_path=str(src_path),
            csv_delimiter=delimiter,
            csv_has_header=header,
        )
        return n
    finally:
        await amds.aclose()


@app.command("restore-async")
def restore_async(
    table: str = typer.Argument(..., help="Target table: bars|fundamentals|news|options_snap"),
    src_path: Path = typer.Argument(
        ..., exists=True, readable=True, help="CSV or CSV.GZ to restore"
    ),
    dsn: str = typer.Option(None, "--dsn", envvar="MDS_DSN", help="PostgreSQL DSN"),
    tenant_id: Optional[str] = typer.Option(
        None, "--tenant-id", envvar="MDS_TENANT_ID", help="Tenant UUID for RLS"
    ),
    app_name: str = typer.Option("mds_client_async", "--app-name", help="application_name for pg"),
    pool_max: int = typer.Option(10, "--pool-max", min=1, help="Async pool max connections"),
    delimiter: str = typer.Option(",", "--delimiter", help="CSV delimiter"),
    header: bool = typer.Option(True, "--header/--no-header", help="CSV has header row"),
    null: str = typer.Option("\\N", "--null", help="NULL representation"),
    temp_table_name: Optional[str] = typer.Option(
        None, "--temp-table", help="Override temp staging table name"
    ),
):
    """
    Async CSV restore with idempotent upserts (COPY to staging → INSERT ... ON CONFLICT).
    """
    if not dsn:
        typer.secho("Missing DSN. Provide --dsn or set MDS_DSN.", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    n = asyncio.run(
        _restore_csv_async_impl(
            table=table,
            src_path=src_path,
            dsn=dsn,
            tenant_id=tenant_id,
            app_name=app_name,
            pool_max=pool_max,
            delimiter=delimiter,
            header=header,
            null=null,
            temp_table_name=temp_table_name,
        )
    )
    typer.secho(f"✅ restore-async complete: {n} rows upserted into {table}", fg=typer.colors.GREEN)


# Optional alias with a more explicit name
@app.command("restore-csv-async")
def restore_csv_async_alias(
    table: str = typer.Argument(...),
    src_path: Path = typer.Argument(...),
    dsn: str = typer.Option(None, "--dsn", envvar="MDS_DSN"),
    tenant_id: Optional[str] = typer.Option(None, "--tenant-id", envvar="MDS_TENANT_ID"),
    app_name: str = typer.Option("mds_client_async", "--app-name"),
    pool_max: int = typer.Option(10, "--pool-max", min=1),
    delimiter: str = typer.Option(",", "--delimiter"),
    header: bool = typer.Option(True, "--header/--no-header"),
    null: str = typer.Option("\\N", "--null"),
    temp_table_name: Optional[str] = typer.Option(None, "--temp-table"),
):
    """Alias of restore-async."""
    return restore_async(
        table=table,
        src_path=src_path,
        dsn=dsn,
        tenant_id=tenant_id,
        app_name=app_name,
        pool_max=pool_max,
        delimiter=delimiter,
        header=header,
        null=null,
        temp_table_name=temp_table_name,
    )


# --- async restore CSV from STDIN -------------------------------------------


@app.command("restore-async-stdin")
def restore_async_stdin(
    table: str = typer.Argument(..., help="Target table: bars|fundamentals|news|options_snap"),
    dsn: str = typer.Option(None, "--dsn", envvar="MDS_DSN", help="PostgreSQL DSN"),
    tenant_id: Optional[str] = typer.Option(
        None, "--tenant-id", envvar="MDS_TENANT_ID", help="Tenant UUID for RLS"
    ),
    app_name: str = typer.Option("mds_client_async", "--app-name", help="application_name for pg"),
    pool_max: int = typer.Option(10, "--pool-max", min=1, help="Async pool max connections"),
    delimiter: str = typer.Option(",", "--delimiter", help="CSV delimiter"),
    header: bool = typer.Option(True, "--header/--no-header", help="CSV has header row"),
    null: str = typer.Option("\\N", "--null", help="NULL representation"),
    temp_table_name: Optional[str] = typer.Option(
        None, "--temp-table", help="Override temp staging table name"
    ),
):
    """
    Async CSV restore from STDIN with idempotent upserts (COPY to staging → INSERT ... ON CONFLICT).
    Example:
      zcat bars.csv.gz | mds restore-async-stdin bars --dsn ... --tenant-id ...
    """
    if not dsn:
        typer.secho("Missing DSN. Provide --dsn or set MDS_DSN.", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    # stream stdin to a temp file on disk (works cross-platform)
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            buf = sys.stdin.buffer
            chunk = buf.read(1 << 20)  # 1 MiB chunks
            while chunk:
                tmp.write(chunk)
                chunk = buf.read(1 << 20)

        # reuse the existing async CSV restore impl (treat temp file as plain CSV)
        n = asyncio.run(
            _restore_csv_async_impl(
                table=table,
                src_path=tmp_path,
                dsn=dsn,
                tenant_id=tenant_id,
                app_name=app_name,
                pool_max=pool_max,
                delimiter=delimiter,
                header=header,
                null=null,
                temp_table_name=temp_table_name,
            )
        )
        typer.secho(
            f"✅ restore-async (stdin) complete: {n} rows upserted into {table}",
            fg=typer.colors.GREEN,
        )
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# --- NDJSON export commands (dump-ndjson*) -----------------------------------

# ---------- small helpers ----------


def _env(k: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(k)
    return v if v not in (None, "") else default


def _cfg(dsn: Optional[str], tenant_id: Optional[str], *, async_mode: bool = False):
    dsn = dsn or _env("MDS_DSN")
    tenant_id = tenant_id or _env("MDS_TENANT_ID")
    if not dsn:
        raise typer.BadParameter("Missing DSN. Provide --dsn or set MDS_DSN.")
    if not tenant_id:
        raise typer.BadParameter("Missing tenant id. Provide --tenant-id or set MDS_TENANT_ID.")
    base = {
        "dsn": dsn,
        "tenant_id": tenant_id,
        "app_name": "mds_client_async" if async_mode else "mds_client",
    }
    return base


def _ensure_parent(path: Path) -> None:
    if path != Path("-"):
        path.parent.mkdir(parents=True, exist_ok=True)


def _slug(v: Optional[str], fallback: str) -> str:
    if not v:
        return fallback
    return str(v).replace(":", "").replace("/", "_").replace("\\", "_").replace(" ", "")


def _format_template(
    template: str,
    *,
    table: str,
    vendor: Optional[str],
    symbol: Optional[str],
    timeframe: Optional[str],
    start: Optional[str],
    end: Optional[str],
) -> str:
    return template.format(
        table=table,
        vendor=_slug(vendor, "ALL"),
        symbol=_slug(symbol, "ALL"),
        timeframe=_slug(timeframe, "ALL"),
        start=_slug(start, "MIN"),
        end=_slug(end, "MAX"),
    )


# ---------- single-table sync ----------


@app.command("dump-ndjson")
def dump_ndjson(
    table: str = typer.Argument(..., help=f"Table name ({', '.join(TABLE_PRESETS.keys())})"),
    out_path: Path = typer.Argument(..., help="Output file path (.ndjson or .ndjson.gz)"),
    dsn: Optional[str] = typer.Option(None, help="PostgreSQL DSN (or set MDS_DSN)"),
    tenant_id: Optional[str] = typer.Option(
        None, "--tenant-id", help="Tenant UUID (or set MDS_TENANT_ID)"
    ),
    vendor: Optional[str] = typer.Option(None, help="Filter: vendor"),
    symbol: Optional[str] = typer.Option(None, help="Filter: symbol"),
    timeframe: Optional[str] = typer.Option(None, help="Filter: timeframe"),
    start: Optional[str] = typer.Option(None, help="Filter: start timestamp (ISO-8601)"),
    end: Optional[str] = typer.Option(None, help="Filter: end timestamp (ISO-8601)"),
):
    """
    Export a table to NDJSON using COPY (round-trips with ingest-ndjson).
    """
    if table not in TABLE_PRESETS:
        raise typer.BadParameter(
            f"Unknown table '{table}'. Valid: {', '.join(TABLE_PRESETS.keys())}"
        )

    cfg = _cfg(dsn, tenant_id, async_mode=False)
    mds = MDS(cfg)
    try:
        sel = mds.build_ndjson_select(
            table,
            vendor=vendor,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
        )
        _ensure_parent(out_path)
        nbytes = mds.copy_out_ndjson(select_sql=sel, out_path=str(out_path))
        typer.echo(f"Wrote {nbytes} bytes → {out_path}")
    finally:
        mds.close()


# ---------- single-table async ----------


@app.command("dump-ndjson-async")
def dump_ndjson_async(
    table: str = typer.Argument(..., help=f"Table name ({', '.join(TABLE_PRESETS.keys())})"),
    out_path: Path = typer.Argument(..., help="Output file path (.ndjson or .ndjson.gz)"),
    dsn: Optional[str] = typer.Option(None, help="PostgreSQL DSN (or set MDS_DSN)"),
    tenant_id: Optional[str] = typer.Option(
        None, "--tenant-id", help="Tenant UUID (or set MDS_TENANT_ID)"
    ),
    vendor: Optional[str] = typer.Option(None, help="Filter: vendor"),
    symbol: Optional[str] = typer.Option(None, help="Filter: symbol"),
    timeframe: Optional[str] = typer.Option(None, help="Filter: timeframe"),
    start: Optional[str] = typer.Option(None, help="Filter: start timestamp (ISO-8601)"),
    end: Optional[str] = typer.Option(None, help="Filter: end timestamp (ISO-8601)"),
):
    """
    Async export of a table to NDJSON using COPY.
    """
    if table not in TABLE_PRESETS:
        raise typer.BadParameter(
            f"Unknown table '{table}'. Valid: {', '.join(TABLE_PRESETS.keys())}"
        )

    async def _run():
        cfg = _cfg(dsn, tenant_id, async_mode=True)
        amds = AMDS(cfg)
        try:
            from .sql import build_ndjson_select as _build

            preset = TABLE_PRESETS[table]
            sel = _build(
                table,
                preset["cols"],
                vendor=vendor,
                symbol=(symbol.upper() if symbol else None),
                timeframe=timeframe,
                start=start,
                end=end,
            )
            _ensure_parent(out_path)
            nbytes = await amds.copy_out_ndjson_async(select_sql=sel, out_path=str(out_path))
            typer.echo(f"Wrote {nbytes} bytes → {out_path}")
        finally:
            await amds.aclose()

    asyncio.run(_run())


# ---------- multi-table sync ----------


@app.command("dump-ndjson-all")
def dump_ndjson_all(
    template: str = typer.Argument(
        "{table}-{vendor}-{symbol}-{start}-{end}.ndjson.gz",
        help="Output name template with placeholders: {table},{vendor},{symbol},{timeframe},{start},{end}",
    ),
    dsn: Optional[str] = typer.Option(None, help="PostgreSQL DSN (or set MDS_DSN)"),
    tenant_id: Optional[str] = typer.Option(
        None, "--tenant-id", help="Tenant UUID (or set MDS_TENANT_ID)"
    ),
    vendor: Optional[str] = typer.Option(None, help="Filter: vendor"),
    symbol: Optional[str] = typer.Option(None, help="Filter: symbol"),
    timeframe: Optional[str] = typer.Option(None, help="Filter: timeframe"),
    start: Optional[str] = typer.Option(None, help="Filter: start timestamp (ISO-8601)"),
    end: Optional[str] = typer.Option(None, help="Filter: end timestamp (ISO-8601)"),
):
    """
    Export ALL known tables to NDJSON files using a naming template.
    """
    cfg = _cfg(dsn, tenant_id, async_mode=False)
    mds = MDS(cfg)
    try:
        for table in TABLE_PRESETS.keys():
            sel = mds.build_ndjson_select(
                table,
                vendor=vendor,
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
            )
            out_name = _format_template(
                template,
                table=table,
                vendor=vendor,
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
            )
            out_path = Path(out_name)
            _ensure_parent(out_path)
            nbytes = mds.copy_out_ndjson(select_sql=sel, out_path=str(out_path))
            typer.echo(f"[{table}] wrote {nbytes} bytes → {out_path}")
    finally:
        mds.close()


# ---------- multi-table async ----------


@app.command("dump-ndjson-async-all")
def dump_ndjson_async_all(
    template: str = typer.Argument(
        "{table}-{vendor}-{symbol}-{start}-{end}.ndjson.gz",
        help="Output name template with placeholders: {table},{vendor},{symbol},{timeframe},{start},{end}",
    ),
    dsn: Optional[str] = typer.Option(None, help="PostgreSQL DSN (or set MDS_DSN)"),
    tenant_id: Optional[str] = typer.Option(
        None, "--tenant-id", help="Tenant UUID (or set MDS_TENANT_ID)"
    ),
    vendor: Optional[str] = typer.Option(None, help="Filter: vendor"),
    symbol: Optional[str] = typer.Option(None, help="Filter: symbol"),
    timeframe: Optional[str] = typer.Option(None, help="Filter: timeframe"),
    start: Optional[str] = typer.Option(None, help="Filter: start timestamp (ISO-8601)"),
    end: Optional[str] = typer.Option(None, help="Filter: end timestamp (ISO-8601)"),
):
    """
    Async export of ALL tables to NDJSON files using a naming template.
    """

    async def _run():
        cfg = _cfg(dsn, tenant_id, async_mode=True)
        amds = AMDS(cfg)
        try:
            for table in TABLE_PRESETS.keys():
                # Use the shared builder from sql.py directly to avoid any attribute coupling
                from .sql import build_ndjson_select as _build

                preset = TABLE_PRESETS[table]
                sel = _build(
                    table,
                    preset["cols"],
                    vendor=vendor,
                    symbol=(symbol.upper() if symbol else None),
                    timeframe=timeframe,
                    start=start,
                    end=end,
                )
                out_name = _format_template(
                    template,
                    table=table,
                    vendor=vendor,
                    symbol=symbol,
                    timeframe=timeframe,
                    start=start,
                    end=end,
                )
                out_path = Path(out_name)
                _ensure_parent(out_path)
                nbytes = await amds.copy_out_ndjson_async(select_sql=sel, out_path=str(out_path))
                typer.echo(f"[{table}] wrote {nbytes} bytes → {out_path}")
        finally:
            await amds.aclose()

    asyncio.run(_run())


# Configure event loop on module import
boot_event_loop()

# If this module is run directly:
if __name__ == "__main__":  # pragma: no cover
    app()
