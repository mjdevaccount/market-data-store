import asyncio
import gzip
import sys
import typer
from datetime import datetime, date
from typing import Optional

from .client import MDS
from .aclient import AMDS
from .batch import BatchProcessor, BatchConfig
from .abatch import AsyncBatchProcessor
from .models import Bar, Fundamentals, News, OptionSnap

app = typer.Typer(help="Market Data Store operational CLI")

# ---------- helpers


def _mk_mds(dsn: str, tenant_id: Optional[str]) -> MDS:
    return MDS({"dsn": dsn, "tenant_id": tenant_id})


def _mk_amds(dsn: str, tenant_id: Optional[str]) -> AMDS:
    return AMDS({"dsn": dsn, "tenant_id": tenant_id, "pool_max": 10})


# ---------- health/schema


@app.command("ping")
def ping(dsn: str, tenant_id: Optional[str] = None):
    mds = _mk_mds(dsn, tenant_id)
    ok = mds.health()
    typer.echo("ok" if ok else "not-ok")


@app.command("schema-version")
def schema_version(dsn: str):
    mds = _mk_mds(dsn, None)
    typer.echo(mds.schema_version())


# ---------- writes (single-row convenience)


@app.command("write-bar")
def write_bar(
    dsn: str,
    tenant_id: str,
    vendor: str,
    symbol: str,
    timeframe: str,
    ts: datetime,
    open_price: Optional[float] = None,
    high_price: Optional[float] = None,
    low_price: Optional[float] = None,
    close_price: Optional[float] = None,
    volume: Optional[int] = None,
):
    mds = _mk_mds(dsn, tenant_id)
    row = Bar(
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
    n = mds.upsert_bars([row])
    typer.echo(n)


@app.command("write-fundamental")
def write_fundamental(
    dsn: str,
    tenant_id: str,
    vendor: str,
    symbol: str,
    asof: datetime,
    total_assets: Optional[float] = None,
    total_liabilities: Optional[float] = None,
    net_income: Optional[float] = None,
    eps: Optional[float] = None,
):
    mds = _mk_mds(dsn, tenant_id)
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
    n = mds.upsert_fundamentals([row])
    typer.echo(n)


@app.command("write-news")
def write_news(
    dsn: str,
    tenant_id: str,
    vendor: str,
    title: str,
    published_at: datetime,
    symbol: Optional[str] = None,
    url: Optional[str] = None,
    sentiment_score: Optional[float] = None,
):
    mds = _mk_mds(dsn, tenant_id)
    row = News(
        tenant_id=tenant_id,
        vendor=vendor,
        title=title,
        published_at=published_at,
        symbol=symbol,
        url=url,
        sentiment_score=sentiment_score,
    )
    n = mds.upsert_news([row])
    typer.echo(n)


@app.command("write-option")
def write_option(
    dsn: str,
    tenant_id: str,
    vendor: str,
    symbol: str,
    expiry: str,
    option_type: str,
    strike: float,
    ts: datetime,
    iv: Optional[float] = None,
    delta: Optional[float] = None,
    gamma: Optional[float] = None,
    oi: Optional[int] = None,
    volume: Optional[int] = None,
    spot: Optional[float] = None,
):
    mds = _mk_mds(dsn, tenant_id)
    expiry_date = date.fromisoformat(expiry)
    row = OptionSnap(
        tenant_id=tenant_id,
        vendor=vendor,
        symbol=symbol,
        expiry=expiry_date,
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
    n = mds.upsert_options([row])
    typer.echo(n)


# ---------- NDJSON ingest (sync and async)


@app.command("ingest-ndjson")
def ingest_ndjson(
    dsn: str,
    tenant_id: str,
    kind: str = typer.Argument(..., help="one of: bars|fundamentals|news|options"),
    path: str = typer.Argument(..., help="NDJSON file path (or '-' for stdin; .gz supported)"),
    max_rows: int = 1000,
    max_ms: int = 5000,
    max_bytes: int = 1_048_576,
):
    """
    Synchronous NDJSON ingest using MDS + BatchProcessor.

    Reads line-delimited JSON objects and batches by size/time/bytes.
    """
    mds = _mk_mds(dsn, tenant_id)
    cfg = BatchConfig(max_rows=max_rows, max_ms=max_ms, max_bytes=max_bytes)
    bp = BatchProcessor(mds, cfg)

    factory_map = {
        "bars": Bar,
        "fundamentals": Fundamentals,
        "news": News,
        "options": OptionSnap,
    }
    factory = factory_map.get(kind.lower())
    if not factory:
        raise typer.BadParameter("kind must be one of: bars|fundamentals|news|options")

    # open file/stream
    if path == "-":
        fh = sys.stdin
        close_needed = False
    elif path.endswith(".gz"):
        fh = gzip.open(path, "rt", encoding="utf-8")
        close_needed = True
    else:
        fh = open(path, "r", encoding="utf-8")
        close_needed = True

    count = 0
    try:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = factory.model_validate_json(line)

            if kind == "bars":
                bp.add_bar(obj)  # type: ignore[arg-type]
            elif kind == "fundamentals":
                bp.add_fundamental(obj)  # type: ignore[arg-type]
            elif kind == "news":
                bp.add_news(obj)  # type: ignore[arg-type]
            else:
                bp.add_option(obj)  # type: ignore[arg-type]

            count += 1

        # final flush
        bp.flush()
    finally:
        if close_needed:
            fh.close()

    typer.echo(count)


@app.command("ingest-ndjson-async")
def ingest_ndjson_async(
    dsn: str,
    tenant_id: str,
    kind: str = typer.Argument(..., help="one of: bars|fundamentals|news|options"),
    path: str = typer.Argument(..., help="NDJSON file path"),
    max_rows: int = 1000,
    max_ms: int = 5000,
    max_bytes: int = 1_048_576,
):
    async def _run():
        amds = _mk_amds(dsn, tenant_id)
        factory_map = {
            "bars": Bar,
            "fundamentals": Fundamentals,
            "news": News,
            "options": OptionSnap,
        }
        factory = factory_map.get(kind.lower())
        if not factory:
            raise typer.BadParameter("kind must be one of: bars|fundamentals|news|options")

        count = 0
        cfg = BatchConfig(max_rows=max_rows, max_ms=max_ms, max_bytes=max_bytes)
        async with AsyncBatchProcessor(amds, cfg) as bp:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    obj = factory.model_validate_json(line)

                    if kind == "bars":
                        await bp.add_bar(obj)  # type: ignore[arg-type]
                    elif kind == "fundamentals":
                        await bp.add_fundamental(obj)  # type: ignore[arg-type]
                    elif kind == "news":
                        await bp.add_news(obj)  # type: ignore[arg-type]
                    else:
                        await bp.add_option(obj)  # type: ignore[arg-type]
                    count += 1

        typer.echo(count)

    asyncio.run(_run())
