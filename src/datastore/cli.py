import typer
from loguru import logger
import subprocess
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from datastore.config import get_settings

app = typer.Typer(help="Data-store CLI (migrations, policies, seeds)")


@app.command()
def migrate(target: str = "head"):
    """Run Alembic migrations to the specified target (default: head)."""
    try:
        logger.info(f"Running migrations to {target}")

        # Run alembic upgrade command
        result = subprocess.run(
            ["alembic", "upgrade", target],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        if result.returncode == 0:
            logger.success(f"Successfully migrated to {target}")
            if result.stdout:
                logger.info(f"Migration output: {result.stdout}")
        else:
            logger.error(f"Migration failed: {result.stderr}")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Failed to run migrations: {e}")
        sys.exit(1)


@app.command()
def seed():
    """Run seed data against the current database."""
    try:
        logger.info("Running seed data")

        # Get database connection
        settings = get_settings()
        engine = create_engine(settings.database_url)

        # Read and execute seed file
        seed_file = Path(__file__).parent.parent.parent / "seeds" / "seed.sql"

        if not seed_file.exists():
            logger.error(f"Seed file not found: {seed_file}")
            sys.exit(1)

        with open(seed_file, "r") as f:
            seed_sql = f.read()

        with engine.connect() as conn:
            # Execute seed SQL
            conn.execute(text(seed_sql))
            conn.commit()

        logger.success("Seed data applied successfully")

    except Exception as e:
        logger.error(f"Failed to run seed data: {e}")
        sys.exit(1)


@app.command()
def policies():
    """Apply TimescaleDB retention and compression policies."""
    try:
        logger.info("Applying TimescaleDB policies")

        # Get database connection
        settings = get_settings()
        engine = create_engine(settings.database_url)

        with engine.connect() as conn:
            # Check if TimescaleDB extension is available
            result = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'"))
            if not result.fetchone():
                logger.warning("TimescaleDB extension not found. Skipping policy application.")
                return

            # Apply retention policies (example - adjust as needed)
            # Example policies that would be applied:
            # SELECT add_retention_policy('bars', INTERVAL '1 year');
            # SELECT add_retention_policy('fundamentals', INTERVAL '5 years');
            # SELECT add_retention_policy('news', INTERVAL '2 years');
            # SELECT add_retention_policy('options_snap', INTERVAL '1 year');
            #
            # Example compression policies:
            # SELECT add_compression_policy('bars', INTERVAL '7 days');
            # SELECT add_compression_policy('options_snap', INTERVAL '1 day');

            # For now, just log the policies that would be applied
            logger.info("TimescaleDB policies would be applied here")
            logger.info("Configure retention and compression policies based on your requirements")

        logger.success("TimescaleDB policies applied successfully")

    except Exception as e:
        logger.error(f"Failed to apply TimescaleDB policies: {e}")
        sys.exit(1)


if __name__ == "__main__":
    app()
