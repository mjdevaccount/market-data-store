"""
Command Line Interface for Market Data Store Client.

Provides operational commands for testing, debugging, and data management.
"""

import typer
from typing import Optional
from datetime import datetime
from .client import MDS, MDSConfig
from .models import Bar, Fundamentals, News, OptionSnap

app = typer.Typer(name="mds", help="Market Data Store Client CLI", add_completion=False)


@app.command()
def ping(
    dsn: str = typer.Option(..., help="PostgreSQL connection string"),
    tenant_id: Optional[str] = typer.Option(None, help="Tenant UUID for RLS"),
):
    """Check database connectivity and health."""
    try:
        config = MDSConfig(dsn=dsn, tenant_id=tenant_id)
        mds = MDS(config)
        health = mds.health()
        typer.echo(f"✅ Health check passed: {health}")
    except Exception as e:
        typer.echo(f"❌ Health check failed: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def schema_version(
    dsn: str = typer.Option(..., help="PostgreSQL connection string"),
    tenant_id: Optional[str] = typer.Option(None, help="Tenant UUID for RLS"),
):
    """Get current schema version."""
    try:
        config = MDSConfig(dsn=dsn, tenant_id=tenant_id)
        mds = MDS(config)
        version = mds.schema_version()
        typer.echo(f"Schema version: {version}")
    except Exception as e:
        typer.echo(f"❌ Failed to get schema version: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def write_bar(
    dsn: str = typer.Option(..., help="PostgreSQL connection string"),
    tenant_id: str = typer.Option(..., help="Tenant UUID for RLS"),
    vendor: str = typer.Option(..., help="Data vendor"),
    symbol: str = typer.Option(..., help="Symbol (e.g., AAPL)"),
    timeframe: str = typer.Option("1m", help="Timeframe (1m, 5m, 1h, 1d)"),
    ts: str = typer.Option(..., help="Timestamp (ISO format)"),
    open_price: Optional[float] = typer.Option(None, help="Open price"),
    high_price: Optional[float] = typer.Option(None, help="High price"),
    low_price: Optional[float] = typer.Option(None, help="Low price"),
    close_price: Optional[float] = typer.Option(None, help="Close price"),
    volume: Optional[int] = typer.Option(None, help="Volume"),
):
    """Write a single bar record."""
    try:
        config = MDSConfig(dsn=dsn, tenant_id=tenant_id)
        mds = MDS(config)

        bar = Bar(
            tenant_id=tenant_id,
            vendor=vendor,
            symbol=symbol,
            timeframe=timeframe,
            ts=datetime.fromisoformat(ts),
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            volume=volume,
        )

        count = mds.upsert_bars([bar])
        typer.echo(f"✅ Inserted {count} bar record(s)")
    except Exception as e:
        typer.echo(f"❌ Failed to write bar: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def write_fundamental(
    dsn: str = typer.Option(..., help="PostgreSQL connection string"),
    tenant_id: str = typer.Option(..., help="Tenant UUID for RLS"),
    vendor: str = typer.Option(..., help="Data vendor"),
    symbol: str = typer.Option(..., help="Symbol (e.g., AAPL)"),
    asof: str = typer.Option(..., help="As-of date (ISO format)"),
    total_assets: Optional[float] = typer.Option(None, help="Total assets"),
    total_liabilities: Optional[float] = typer.Option(None, help="Total liabilities"),
    net_income: Optional[float] = typer.Option(None, help="Net income"),
    eps: Optional[float] = typer.Option(None, help="Earnings per share"),
):
    """Write a single fundamentals record."""
    try:
        config = MDSConfig(dsn=dsn, tenant_id=tenant_id)
        mds = MDS(config)

        fundamental = Fundamentals(
            tenant_id=tenant_id,
            vendor=vendor,
            symbol=symbol,
            asof=datetime.fromisoformat(asof),
            total_assets=total_assets,
            total_liabilities=total_liabilities,
            net_income=net_income,
            eps=eps,
        )

        count = mds.upsert_fundamentals([fundamental])
        typer.echo(f"✅ Inserted {count} fundamental record(s)")
    except Exception as e:
        typer.echo(f"❌ Failed to write fundamental: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def write_news(
    dsn: str = typer.Option(..., help="PostgreSQL connection string"),
    tenant_id: str = typer.Option(..., help="Tenant UUID for RLS"),
    vendor: str = typer.Option(..., help="Data vendor"),
    title: str = typer.Option(..., help="News title"),
    published_at: str = typer.Option(..., help="Published timestamp (ISO format)"),
    symbol: Optional[str] = typer.Option(None, help="Related symbol"),
    url: Optional[str] = typer.Option(None, help="News URL"),
    sentiment_score: Optional[float] = typer.Option(None, help="Sentiment score (-1.0 to 1.0)"),
):
    """Write a single news record."""
    try:
        config = MDSConfig(dsn=dsn, tenant_id=tenant_id)
        mds = MDS(config)

        news = News(
            tenant_id=tenant_id,
            vendor=vendor,
            title=title,
            published_at=datetime.fromisoformat(published_at),
            symbol=symbol,
            url=url,
            sentiment_score=sentiment_score,
        )

        count = mds.upsert_news([news])
        typer.echo(f"✅ Inserted {count} news record(s)")
    except Exception as e:
        typer.echo(f"❌ Failed to write news: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def write_option(
    dsn: str = typer.Option(..., help="PostgreSQL connection string"),
    tenant_id: str = typer.Option(..., help="Tenant UUID for RLS"),
    vendor: str = typer.Option(..., help="Data vendor"),
    symbol: str = typer.Option(..., help="Underlying symbol"),
    expiry: str = typer.Option(..., help="Expiry date (YYYY-MM-DD)"),
    option_type: str = typer.Option(..., help="Option type (C or P)"),
    strike: float = typer.Option(..., help="Strike price"),
    ts: str = typer.Option(..., help="Snapshot timestamp (ISO format)"),
    iv: Optional[float] = typer.Option(None, help="Implied volatility"),
    delta: Optional[float] = typer.Option(None, help="Delta"),
    gamma: Optional[float] = typer.Option(None, help="Gamma"),
    oi: Optional[int] = typer.Option(None, help="Open interest"),
    volume: Optional[int] = typer.Option(None, help="Volume"),
    spot: Optional[float] = typer.Option(None, help="Spot price"),
):
    """Write a single options snapshot record."""
    try:
        config = MDSConfig(dsn=dsn, tenant_id=tenant_id)
        mds = MDS(config)

        option = OptionSnap(
            tenant_id=tenant_id,
            vendor=vendor,
            symbol=symbol,
            expiry=datetime.fromisoformat(expiry).date(),
            option_type=option_type,
            strike=strike,
            ts=datetime.fromisoformat(ts),
            iv=iv,
            delta=delta,
            gamma=gamma,
            oi=oi,
            volume=volume,
            spot=spot,
        )

        count = mds.upsert_options([option])
        typer.echo(f"✅ Inserted {count} option record(s)")
    except Exception as e:
        typer.echo(f"❌ Failed to write option: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def latest_prices(
    dsn: str = typer.Option(..., help="PostgreSQL connection string"),
    tenant_id: Optional[str] = typer.Option(None, help="Tenant UUID for RLS"),
    vendor: str = typer.Option(..., help="Data vendor"),
    symbols: str = typer.Option(..., help="Comma-separated symbols (e.g., AAPL,MSFT)"),
):
    """Get latest prices for symbols."""
    try:
        config = MDSConfig(dsn=dsn, tenant_id=tenant_id)
        mds = MDS(config)

        symbol_list = [s.strip() for s in symbols.split(",")]
        prices = mds.latest_prices(symbol_list, vendor)

        if not prices:
            typer.echo("No prices found")
            return

        typer.echo(f"Latest prices from {vendor}:")
        for price in prices:
            typer.echo(f"  {price.symbol}: ${price.price:.2f} @ {price.price_timestamp}")
    except Exception as e:
        typer.echo(f"❌ Failed to get latest prices: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def enqueue_job(
    dsn: str = typer.Option(..., help="PostgreSQL connection string"),
    tenant_id: str = typer.Option(..., help="Tenant UUID for RLS"),
    idempotency_key: str = typer.Option(..., help="Unique job identifier"),
    job_type: str = typer.Option(..., help="Job type"),
    payload: str = typer.Option(..., help="Job payload (JSON string)"),
    priority: str = typer.Option("medium", help="Job priority (low, medium, high, urgent)"),
):
    """Enqueue a job in the outbox."""
    try:
        import json

        config = MDSConfig(dsn=dsn, tenant_id=tenant_id)
        mds = MDS(config)

        payload_dict = json.loads(payload)
        job_id = mds.enqueue_job(idempotency_key, job_type, payload_dict, priority)

        if job_id:
            typer.echo(f"✅ Enqueued job {job_id}")
        else:
            typer.echo("Job already exists (idempotent)")
    except Exception as e:
        typer.echo(f"❌ Failed to enqueue job: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
