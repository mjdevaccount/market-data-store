from __future__ import annotations

import asyncio
import gzip
import json
import sys
from datetime import datetime
from typing import Optional

import typer

from .client import MDS
from .aclient import AMDS
from .batch import BatchProcessor, AsyncBatchProcessor, BatchConfig
from .models import Bar, Fundamentals, News, OptionSnap

app = typer.Typer(help="Market Data Store (mds_client) operational CLI")


# ---------- helpers ----------


def _mk_mds(dsn: str, tenant_id: Optional[str]) -> MDS:
    cfg: dict = {"dsn": dsn}
    if tenant_id:
        cfg["tenant_id"] = tenant_id
    return MDS(cfg)


def _mk_amds(dsn: str, tenant_id: Optional[str], pool_max: int) -> AMDS:
    cfg: dict = {"dsn": dsn, "pool_max": pool_max}
    if tenant_id:
        cfg["tenant_id"] = tenant_id
    return AMDS(cfg)


def _parse_csv(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def _echo(obj) -> None:
    typer.echo(json.dumps(obj, default=str))


# ---------- connectivity ----------


@app.command("ping")
def ping(dsn: str, tenant_id: Optional[str] = typer.Option(None)):
    mds = _mk_mds(dsn, tenant_id)
    ok = mds.health()
    _echo({"ok": ok})


@app.command("schema-version")
def schema_version(dsn: str):
    mds = _mk_mds(dsn, None)
    _echo({"schema_version": mds.schema_version()})


# ---------- writes (sync) ----------


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
    mds.upsert_bars([row])
    _echo({"upserted": 1})


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
    mds.upsert_fundamentals([row])
    _echo({"upserted": 1})


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
    mds.upsert_news([row])
    _echo({"upserted": 1})


@app.command("write-option")
def write_option(
    dsn: str,
    tenant_id: str,
    vendor: str,
    symbol: str,
    expiry: datetime,  # you can change to date in typer if you prefer
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
    row = OptionSnap(
        tenant_id=tenant_id,
        vendor=vendor,
        symbol=symbol,
        expiry=expiry.date(),
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
    _echo({"upserted": 1})


# ---------- reads (sync) ----------


@app.command("latest-prices")
def latest_prices(
    dsn: str,
    vendor: str,
    symbols: str = typer.Argument(..., help="CSV list: e.g. AAPL,MSFT,SPY"),
    tenant_id: Optional[str] = typer.Option(None),
):
    mds = _mk_mds(dsn, tenant_id)
    rows = mds.latest_prices(_parse_csv(symbols), vendor=vendor)
    _echo([r.model_dump() for r in rows])


# ---------- ingest NDJSON (sync) ----------


@app.command("ingest-ndjson")
def ingest_ndjson(
    kind: str = typer.Argument(..., help="one of: bars|fundamentals|news|options"),
    path: str = typer.Argument(..., help="NDJSON file path or '-' for stdin (.gz supported)"),
    dsn: str = typer.Option(..., help="PostgreSQL DSN"),
    tenant_id: str = typer.Option(..., help="Tenant UUID"),
    max_rows: int = 1000,
    max_ms: int = 5000,
    max_bytes: int = 1_048_576,
):
    mds = _mk_mds(dsn, tenant_id)
    cfg = BatchConfig(max_rows=max_rows, max_ms=max_ms, max_bytes=max_bytes)
    bp = BatchProcessor(mds, cfg)

    model_map = {
        "bars": Bar,
        "fundamentals": Fundamentals,
        "news": News,
        "options": OptionSnap,
    }
    factory = model_map.get(kind.lower())
    if not factory:
        raise typer.BadParameter("kind must be one of: bars|fundamentals|news|options")

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
            s = line.strip()
            if not s:
                continue
            obj = factory.model_validate_json(s)
            if kind == "bars":
                bp.add_bar(obj)  # type: ignore[arg-type]
            elif kind == "fundamentals":
                bp.add_fundamental(obj)  # type: ignore[arg-type]
            elif kind == "news":
                bp.add_news(obj)  # type: ignore[arg-type]
            else:
                bp.add_option(obj)  # type: ignore[arg-type]
            count += 1
        bp.flush()
    finally:
        if close_needed:
            fh.close()

    _echo({"ingested": count})


# ---------- ingest NDJSON (async) ----------


async def _ingest_ndjson_async_impl(
    kind: str,
    path: str,
    amds: AMDS,
    cfg: BatchConfig,
) -> int:
    model_map = {
        "bars": Bar,
        "fundamentals": Fundamentals,
        "news": News,
        "options": OptionSnap,
    }
    factory = model_map.get(kind.lower())
    if not factory:
        raise typer.BadParameter("kind must be one of: bars|fundamentals|news|options")

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
        async with AsyncBatchProcessor(amds, cfg) as bp:
            for line in fh:
                s = line.strip()
                if not s:
                    continue
                obj = factory.model_validate_json(s)
                if kind == "bars":
                    await bp.add_bar(obj)  # type: ignore[arg-type]
                elif kind == "fundamentals":
                    await bp.add_fundamental(obj)  # type: ignore[arg-type]
                elif kind == "news":
                    await bp.add_news(obj)  # type: ignore[arg-type]
                else:
                    await bp.add_option(obj)  # type: ignore[arg-type]
                count += 1
    finally:
        if close_needed:
            fh.close()

    return count


@app.command("ingest-ndjson-async")
def ingest_ndjson_async(
    kind: str = typer.Argument(..., help="one of: bars|fundamentals|news|options"),
    path: str = typer.Argument(..., help="NDJSON file path or '-' for stdin (.gz supported)"),
    dsn: str = typer.Option(..., help="PostgreSQL DSN"),
    tenant_id: str = typer.Option(..., help="Tenant UUID"),
    pool_max: int = 10,
    max_rows: int = 1000,
    max_ms: int = 5000,
    max_bytes: int = 1_048_576,
):
    amds = _mk_amds(dsn, tenant_id, pool_max=pool_max)
    cfg = BatchConfig(max_rows=max_rows, max_ms=max_ms, max_bytes=max_bytes)
    total = asyncio.run(_ingest_ndjson_async_impl(kind, path, amds, cfg))
    _echo({"ingested": total})


# ---------- entry ----------


def main():
    app()


if __name__ == "__main__":
    main()
