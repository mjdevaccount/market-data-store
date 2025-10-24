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


# =====================================================================
# Job Runs Management
# =====================================================================


@app.command()
def job_runs_list(
    limit: int = typer.Option(50, help="Maximum number of runs to show"),
    job_name: str = typer.Option(None, help="Filter by job name"),
) -> None:
    """List recent job runs with status and metrics."""
    from .job_tracking import JobRunTracker

    settings = get_settings()
    if not settings.JOB_TRACKING_ENABLED:
        logger.warning("JOB_TRACKING_ENABLED is False, skipping")
        raise typer.Exit(code=0)

    tracker = JobRunTracker(settings.DATABASE_URL)
    runs = tracker.get_recent_runs(limit=limit, job_name=job_name)

    if not runs:
        logger.info("No job runs found")
        return

    typer.echo(
        f"\n{'ID':<8} {'Job Name':<30} {'Status':<10} {'Rows':<12} {'Elapsed (ms)':<15} {'Started':<20}"
    )
    typer.echo("-" * 100)

    for run in runs:
        run_id = run["id"]
        name = (run["job_name"] or "")[:28]
        status = run["status"] or "unknown"
        rows = run["rows_written"] or 0
        elapsed = run["elapsed_ms"] or 0 if run["completed_at"] else "running"
        started = run["started_at"].strftime("%Y-%m-%d %H:%M:%S") if run["started_at"] else ""

        typer.echo(f"{run_id:<8} {name:<30} {status:<10} {rows:<12} {elapsed!s:<15} {started:<20}")

    typer.echo(f"\nTotal runs: {len(runs)}")


@app.command()
def job_runs_inspect(run_id: int = typer.Argument(..., help="Job run ID to inspect")) -> None:
    """Inspect a specific job run with full details."""
    from .job_tracking import JobRunTracker
    import json

    settings = get_settings()
    if not settings.JOB_TRACKING_ENABLED:
        logger.warning("JOB_TRACKING_ENABLED is False, skipping")
        raise typer.Exit(code=0)

    tracker = JobRunTracker(settings.DATABASE_URL)
    run = tracker.get_run(run_id)

    if not run:
        logger.error(f"Job run {run_id} not found")
        raise typer.Exit(code=1)

    typer.echo("\n" + "=" * 80)
    typer.echo(f"Job Run #{run['id']}")
    typer.echo("=" * 80)
    typer.echo(f"Job Name:          {run['job_name']}")
    typer.echo(f"Dataset:           {run['dataset_name'] or 'N/A'}")
    typer.echo(f"Provider:          {run['provider'] or 'N/A'}")
    typer.echo(f"Mode:              {run['mode']}")
    typer.echo(f"Status:            {run['status']}")
    typer.echo(f"Config Fingerprint: {run['config_fingerprint'] or 'N/A'}")
    typer.echo(f"Pipeline Version:  {run['pipeline_version'] or 'N/A'}")
    typer.echo(f"Rows Written:      {run['rows_written']}")
    typer.echo(f"Rows Failed:       {run['rows_failed']}")
    typer.echo(f"Symbols:           {', '.join(run['symbols']) if run['symbols'] else 'N/A'}")
    typer.echo(f"Min Timestamp:     {run['min_ts'] or 'N/A'}")
    typer.echo(f"Max Timestamp:     {run['max_ts'] or 'N/A'}")
    typer.echo(f"Started:           {run['started_at']}")
    typer.echo(f"Completed:         {run['completed_at'] or 'N/A'}")
    typer.echo(f"Elapsed (ms):      {run['elapsed_ms'] or 'N/A'}")

    if run["error_message"]:
        typer.echo(f"\nError Message:\n{run['error_message']}")

    if run["metadata"]:
        typer.echo(f"\nMetadata:\n{json.dumps(run['metadata'], indent=2, default=str)}")

    typer.echo("=" * 80 + "\n")


@app.command()
def job_runs_cleanup(
    older_than_days: int = typer.Option(90, help="Delete completed runs older than N days"),
    confirm: bool = typer.Option(False, "--confirm", help="Skip confirmation prompt"),
) -> None:
    """Cleanup old completed job runs."""
    from .job_tracking import JobRunTracker

    settings = get_settings()
    if not settings.JOB_TRACKING_ENABLED:
        logger.warning("JOB_TRACKING_ENABLED is False, skipping")
        raise typer.Exit(code=0)

    if not confirm:
        proceed = typer.confirm(f"Delete job runs older than {older_than_days} days?", abort=True)
        if not proceed:
            raise typer.Exit(code=0)

    tracker = JobRunTracker(settings.DATABASE_URL)
    deleted = tracker.cleanup_old_runs(days=older_than_days)

    logger.success(f"Deleted {deleted} job runs older than {older_than_days} days")


@app.command()
def job_runs_stuck(
    timeout_minutes: int = typer.Option(
        15, help="Consider runs stuck after N minutes without heartbeat"
    )
) -> None:
    """Find stuck job runs (no heartbeat for N minutes)."""
    from .job_tracking import JobRunTracker

    settings = get_settings()
    if not settings.JOB_TRACKING_ENABLED:
        logger.warning("JOB_TRACKING_ENABLED is False, skipping")
        raise typer.Exit(code=0)

    tracker = JobRunTracker(settings.DATABASE_URL)
    stuck = tracker.get_stuck_runs(heartbeat_timeout_minutes=timeout_minutes)

    if not stuck:
        logger.info(f"No stuck runs found (timeout: {timeout_minutes}m)")
        return

    typer.echo(
        f"\n⚠️  Found {len(stuck)} stuck job run(s) (no heartbeat for >{timeout_minutes}m):\n"
    )
    typer.echo(f"{'ID':<8} {'Job Name':<30} {'Started':<20} {'Last Heartbeat':<20}")
    typer.echo("-" * 80)

    for run in stuck:
        run_id = run["id"]
        name = (run["job_name"] or "")[:28]
        started = run["started_at"].strftime("%Y-%m-%d %H:%M:%S") if run["started_at"] else ""
        heartbeat = run["metadata"].get("last_heartbeat", "never") if run["metadata"] else "never"

        typer.echo(f"{run_id:<8} {name:<30} {started:<20} {heartbeat!s:<20}")

    typer.echo("\nConsider investigating these runs or marking them as failed/cancelled.\n")


@app.command()
def job_runs_summary() -> None:
    """Show job runs summary (last 24h aggregated stats)."""
    from .job_tracking import JobRunTracker

    settings = get_settings()
    if not settings.JOB_TRACKING_ENABLED:
        logger.warning("JOB_TRACKING_ENABLED is False, skipping")
        raise typer.Exit(code=0)

    tracker = JobRunTracker(settings.DATABASE_URL)
    summary = tracker.get_summary()

    if not summary:
        logger.info("No job runs in the last 24 hours")
        return

    typer.echo("\n📊 Job Runs Summary (Last 24h):\n")
    typer.echo(
        f"{'Job Name':<30} {'Provider':<15} {'Status':<10} {'Runs':<8} {'Avg Duration (ms)':<18} {'Total Rows':<12} {'Failures':<10}"
    )
    typer.echo("-" * 110)

    for s in summary:
        job = (s["job_name"] or "")[:28]
        provider = (s["provider"] or "N/A")[:13]
        status = s["status"] or "unknown"
        runs = s["run_count"] or 0
        avg_dur = int(s["avg_duration_ms"] or 0)
        total = s["total_rows"] or 0
        failures = s["failure_count"] or 0

        typer.echo(
            f"{job:<30} {provider:<15} {status:<10} {runs:<8} {avg_dur:<18} {total:<12} {failures:<10}"
        )

    typer.echo()


if __name__ == "__main__":
    app()
