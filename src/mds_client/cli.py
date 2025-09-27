import asyncio
import json
import typer
from typing import Optional
from datetime import datetime, date

from .client import MDS
from .models import Bar, Fundamentals, News, OptionSnap

app = typer.Typer(help="MDS operational CLI")


def _mds(dsn: str, tenant_id: Optional[str]) -> MDS:
    return MDS({"dsn": dsn, "tenant_id": tenant_id, "pool_max": 2})


# ------------------------- health/meta


@app.command()
def ping(dsn: str, tenant_id: Optional[str] = None):
    ok = _mds(dsn, tenant_id).health()
    typer.echo("ok" if ok else "fail")


@app.command("schema-version")
def schema_version(dsn: str, tenant_id: Optional[str] = None):
    v = _mds(dsn, tenant_id).schema_version()
    typer.echo(v or "unknown")


# ------------------------- writes (single-row convenience)


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
    n = _mds(dsn, tenant_id).upsert_bars([row])
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
    n = _mds(dsn, tenant_id).upsert_fundamentals([row])
    typer.echo(n)


@app.command("write-news")
def write_news(
    dsn: str,
    tenant_id: str,
    vendor: str,
    published_at: datetime,
    title: str,
    symbol: Optional[str] = None,
    url: Optional[str] = None,
    sentiment_score: Optional[float] = None,
    id: Optional[str] = None,
):
    row = News(
        tenant_id=tenant_id,
        vendor=vendor,
        published_at=published_at,
        title=title,
        symbol=symbol,
        url=url,
        sentiment_score=sentiment_score,
        id=id,
    )
    n = _mds(dsn, tenant_id).upsert_news([row])
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
    n = _mds(dsn, tenant_id).upsert_options([row])
    typer.echo(n)


# ------------------------- reads


@app.command("latest-prices")
def latest_prices(
    dsn: str,
    vendor: str,
    symbols: str,
    tenant_id: Optional[str] = None,
):
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    res = _mds(dsn, tenant_id).latest_prices(syms, vendor)
    typer.echo(json.dumps([r.model_dump() for r in res], default=str))


# ------------------------- jobs


@app.command("enqueue-job")
def enqueue_job(
    dsn: str,
    tenant_id: str,
    idempotency_key: str,
    job_type: str,
    payload: str,
    priority: str = "medium",
):
    mds = _mds(dsn, tenant_id)
    job_id = mds.enqueue_job(
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        job_type=job_type,
        payload=json.loads(payload),
        priority=priority,
    )
    typer.echo(job_id or "")


# ------------------------- batch ingest


@app.command("ingest-ndjson")
def ingest_ndjson(
    dsn: str,
    tenant_id: str,
    kind: str = typer.Argument(..., help="one of: bars|fundamentals|news|options"),
    file: typer.FileText = typer.Argument(..., help="path to NDJSON file with records"),
    max_rows: int = 1000,
    max_ms: int = 5000,
    max_bytes: int = 1_048_576,
):
    from .batch import BatchProcessor, BatchConfig

    bp = BatchProcessor(
        _mds(dsn, tenant_id), BatchConfig(max_rows=max_rows, max_ms=max_ms, max_bytes=max_bytes)
    )

    factory = {
        "bars": Bar,
        "fundamentals": Fundamentals,
        "news": News,
        "options": OptionSnap,
    }.get(kind.lower())
    if not factory:
        raise typer.BadParameter("kind must be one of: bars|fundamentals|news|options")

    added = 0
    for line in file:
        if not line.strip():
            continue
        obj = factory.model_validate_json(line)
        if factory is Bar:
            bp.add_bar(obj)  # type: ignore[arg-type]
        elif factory is Fundamentals:
            bp.add_fundamental(obj)  # type: ignore[arg-type]
        elif factory is News:
            bp.add_news(obj)  # type: ignore[arg-type]
        else:
            bp.add_option(obj)  # type: ignore[arg-type]
        added += 1

    bp.close()
    typer.echo(added)


@app.command("ingest-ndjson-async")
def ingest_ndjson_async(
    dsn: str,
    tenant_id: str,
    kind: str = typer.Argument(..., help="one of: bars|fundamentals|news|options"),
    file: typer.FileText = typer.Argument(..., help="NDJSON file"),
    max_rows: int = 1000,
    max_ms: int = 5000,
    max_bytes: int = 1_048_576,
):
    async def _run():
        from .abatch import AsyncBatchProcessor
        from .batch import BatchConfig
        from .aclient import AMDS

        amds = AMDS({"dsn": dsn, "tenant_id": tenant_id, "pool_max": 10})
        factory = {
            "bars": Bar,
            "fundamentals": Fundamentals,
            "news": News,
            "options": OptionSnap,
        }.get(kind.lower())
        if not factory:
            raise typer.BadParameter("kind must be one of: bars|fundamentals|news|options")

        count = 0
        async with AsyncBatchProcessor(
            amds, BatchConfig(max_rows=max_rows, max_ms=max_ms, max_bytes=max_bytes)
        ) as bp:
            for line in file:
                if not line.strip():
                    continue
                obj = factory.model_validate_json(line)
                if kind.lower() == "bars":
                    await bp.add_bar(obj)  # type: ignore[arg-type]
                elif kind.lower() == "fundamentals":
                    await bp.add_fundamental(obj)  # type: ignore[arg-type]
                elif kind.lower() == "news":
                    await bp.add_news(obj)  # type: ignore[arg-type]
                else:
                    await bp.add_option(obj)  # type: ignore[arg-type]
                count += 1
        typer.echo(count)

    asyncio.run(_run())
