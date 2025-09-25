import typer
from loguru import logger

app = typer.Typer(help="Data-store CLI (migrations, policies, seeds)")


@app.command()
def migrate(target: str = "head"):
    # Later: shell out to alembic or call programmatically
    logger.info(f"Apply migrations to {target}")


@app.command()
def seed():
    logger.info("Seed data (placeholder)")


@app.command()
def policies():
    logger.info("Apply timescale retention/compression policies (placeholder)")


if __name__ == "__main__":
    app()
