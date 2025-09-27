import sys
import subprocess
from pathlib import Path

import typer
from loguru import logger
from sqlalchemy import create_engine, text

from .config import get_settings
from .timescale_policies import apply_all as apply_timescale_policies
from .aggregates import create_continuous_aggregates

app = typer.Typer(help="Datastore control-plane CLI")


def _engine():
    settings = get_settings()
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True)


@app.command()
def migrate() -> None:
    """Run Alembic upgrade head."""
    settings = get_settings()
    ini = settings.ALEMBIC_INI
    logger.info(f"Running alembic upgrade head using {ini}")
    try:
        subprocess.check_call(["alembic", "-c", ini, "upgrade", "head"])
    except subprocess.CalledProcessError as e:
        logger.error(f"Alembic migration failed: {e}")
        sys.exit(e.returncode)


@app.command()
def seed(file: str = typer.Option("seeds/seed.sql", help="Seed SQL file")) -> None:
    """Apply seed data (idempotent)."""
    p = Path(file)
    if not p.exists():
        logger.error(f"Seed file not found: {p}")
        raise typer.Exit(code=1)
    sql = p.read_text(encoding="utf-8")
    eng = _engine()
    with eng.begin() as conn:
        logger.info(f"Applying seeds from {p}")
        conn.execute(text(sql))
    logger.success("Seeds applied.")


@app.command()
def policies() -> None:
    """Apply Timescale hypertables/compression and (optional) aggregates."""
    eng = _engine()
    apply_timescale_policies(eng)
    create_continuous_aggregates(eng)
    logger.success("Policies (and aggregates) applied.")


@app.command()
def stamp_head() -> None:
    """Stamp Alembic head (for fresh initdb bootstrap)."""
    settings = get_settings()
    ini = settings.ALEMBIC_INI
    logger.info(f"Stamping alembic head using {ini}")
    try:
        subprocess.check_call(["alembic", "-c", ini, "stamp", "head"])
        logger.success("Alembic head stamped successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Alembic stamp failed: {e}")
        sys.exit(e.returncode)


if __name__ == "__main__":
    app()
