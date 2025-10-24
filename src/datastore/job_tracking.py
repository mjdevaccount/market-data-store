"""
JobRunTracker - Audit-grade job execution tracking with heartbeats.

Provides full lifecycle tracking for pipeline/coordinator jobs:
- Start run with config fingerprint
- Update progress with heartbeats
- Complete run with status
- Query recent runs
- Cleanup old runs

Features:
- Heartbeat mechanism via JSONB metadata for stuck job detection
- Config fingerprinting for reproducibility (SHA-256)
- Pipeline version tracking
- Min/max timestamp tracking
- Derived elapsed_ms column for Grafana dashboards
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import hashlib
import json
import psycopg
from psycopg.rows import dict_row
from loguru import logger


class JobRunTracker:
    """
    Track pipeline job executions with full audit trail.

    Usage:
        tracker = JobRunTracker(db_uri)
        run_id = tracker.start_run("live_us_equities", ...)
        tracker.update_progress(run_id, rows_written=1000, heartbeat=True)
        tracker.complete_run(run_id, status="success")
    """

    def __init__(self, uri: str):
        """
        Initialize JobRunTracker.

        Args:
            uri: PostgreSQL connection URI
        """
        self._uri = uri

    def start_run(
        self,
        job_name: str,
        dataset_name: Optional[str] = None,
        provider: Optional[str] = None,
        mode: str = "live",
        config_fingerprint: Optional[str] = None,
        pipeline_version: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Start a job run and return run_id.

        Args:
            job_name: Name of the job (e.g., "live_us_equities_5min")
            dataset_name: Optional dataset name from config
            provider: Provider name (e.g., "ibkr_primary")
            mode: Job mode ("live" or "backfill")
            config_fingerprint: SHA-256 hash of config for reproducibility
            pipeline_version: Pipeline version (git hash, semver, etc.)
            metadata: Optional metadata dict (git hash, container id, etc.)

        Returns:
            run_id: Unique identifier for this job run

        Raises:
            psycopg.Error: On database errors
        """
        with psycopg.connect(self._uri) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO job_runs (
                        job_name, dataset_name, provider, mode,
                        config_fingerprint, pipeline_version, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        job_name,
                        dataset_name,
                        provider,
                        mode,
                        config_fingerprint,
                        pipeline_version,
                        json.dumps(metadata or {}),
                    ),
                )
                run_id = cur.fetchone()[0]
                conn.commit()
                logger.info(
                    f"Started job run {run_id}: {job_name} ({mode}) "
                    f"provider={provider} fingerprint={config_fingerprint}"
                )
                return run_id

    def update_progress(
        self,
        run_id: int,
        rows_written: int = 0,
        rows_failed: int = 0,
        symbols: Optional[List[str]] = None,
        min_ts: Optional[datetime] = None,
        max_ts: Optional[datetime] = None,
        heartbeat: bool = True,
    ) -> None:
        """
        Update job run progress with optional heartbeat.

        This method is designed to be called periodically during job execution
        to track progress and signal liveness (heartbeat).

        Args:
            run_id: Job run identifier from start_run()
            rows_written: Number of rows successfully written (incremental)
            rows_failed: Number of rows that failed (incremental)
            symbols: List of symbols being processed (overwrites existing)
            min_ts: Minimum timestamp in this batch
            max_ts: Maximum timestamp in this batch
            heartbeat: If True, update last_heartbeat in metadata for monitoring

        Raises:
            psycopg.Error: On database errors
        """
        with psycopg.connect(self._uri) as conn:
            with conn.cursor() as cur:
                # Update counters and time window
                cur.execute(
                    """
                    UPDATE job_runs SET
                        rows_written = rows_written + %s,
                        rows_failed = rows_failed + %s,
                        symbols = CASE WHEN %s::text[] IS NOT NULL THEN %s ELSE symbols END,
                        min_ts = CASE WHEN %s IS NOT NULL
                                 THEN LEAST(COALESCE(min_ts, %s), %s)
                                 ELSE min_ts END,
                        max_ts = CASE WHEN %s IS NOT NULL
                                 THEN GREATEST(COALESCE(max_ts, %s), %s)
                                 ELSE max_ts END,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        rows_written,
                        rows_failed,
                        symbols,
                        symbols,
                        min_ts,
                        min_ts,
                        min_ts,
                        max_ts,
                        max_ts,
                        max_ts,
                        run_id,
                    ),
                )

                # Add heartbeat timestamp to metadata for stuck job detection
                if heartbeat:
                    cur.execute(
                        """
                        UPDATE job_runs SET
                            metadata = jsonb_set(
                                COALESCE(metadata, '{}'::jsonb),
                                '{last_heartbeat}',
                                to_jsonb(NOW())
                            )
                        WHERE id = %s
                        """,
                        (run_id,),
                    )

                conn.commit()
                logger.debug(
                    f"Updated progress for run {run_id}: "
                    f"+{rows_written} written, +{rows_failed} failed"
                )

    def complete_run(
        self,
        run_id: int,
        status: str = "success",
        error_message: Optional[str] = None,
    ) -> None:
        """
        Mark job run as completed.

        Args:
            run_id: Job run identifier from start_run()
            status: Final status ("success", "failure", or "cancelled")
            error_message: Optional error message if status is "failure"

        Raises:
            ValueError: If status is not valid
            psycopg.Error: On database errors
        """
        valid_statuses = {"success", "failure", "cancelled"}
        if status not in valid_statuses:
            raise ValueError(f"Invalid status '{status}'. Must be one of: {valid_statuses}")

        with psycopg.connect(self._uri) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE job_runs SET
                        status = %s,
                        error_message = %s,
                        completed_at = NOW()
                    WHERE id = %s
                    """,
                    (status, error_message, run_id),
                )
                conn.commit()

                # Fetch elapsed time for logging
                cur.execute("SELECT elapsed_ms FROM job_runs WHERE id = %s", (run_id,))
                row = cur.fetchone()
                elapsed = row[0] if row else None

                logger.info(
                    f"Completed job run {run_id}: {status} " f"(elapsed: {elapsed}ms)"
                    if elapsed
                    else "(elapsed: N/A)"
                )

    def get_recent_runs(
        self, limit: int = 50, job_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent job runs.

        Args:
            limit: Maximum number of runs to return
            job_name: Optional filter by job name

        Returns:
            List of job run dictionaries (most recent first)

        Raises:
            psycopg.Error: On database errors
        """
        with psycopg.connect(self._uri) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if job_name:
                    cur.execute(
                        """
                        SELECT * FROM job_runs
                        WHERE job_name = %s
                        ORDER BY started_at DESC
                        LIMIT %s
                        """,
                        (job_name, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM job_runs
                        ORDER BY started_at DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                return list(cur.fetchall())

    def get_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific job run by ID.

        Args:
            run_id: Job run identifier

        Returns:
            Job run dictionary or None if not found

        Raises:
            psycopg.Error: On database errors
        """
        with psycopg.connect(self._uri) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM job_runs WHERE id = %s", (run_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def get_stuck_runs(self, heartbeat_timeout_minutes: int = 15) -> List[Dict[str, Any]]:
        """
        Find job runs that are still 'running' but haven't sent a heartbeat recently.

        Useful for detecting stuck/crashed jobs that need intervention.

        Args:
            heartbeat_timeout_minutes: Consider runs stuck if no heartbeat for N minutes

        Returns:
            List of stuck job run dictionaries

        Raises:
            psycopg.Error: On database errors
        """
        with psycopg.connect(self._uri) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT * FROM job_runs
                    WHERE status = 'running'
                      AND (
                        metadata->>'last_heartbeat' IS NULL
                        OR (metadata->>'last_heartbeat')::timestamptz < NOW() - INTERVAL '%s minutes'
                      )
                    ORDER BY started_at DESC
                    """,
                    (heartbeat_timeout_minutes,),
                )
                return list(cur.fetchall())

    def cleanup_old_runs(self, days: int = 90) -> int:
        """
        Delete completed job runs older than N days.

        Args:
            days: Delete runs older than this many days

        Returns:
            Number of runs deleted

        Raises:
            psycopg.Error: On database errors
        """
        with psycopg.connect(self._uri) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM job_runs
                    WHERE completed_at < NOW() - INTERVAL '%s days'
                    RETURNING id
                    """,
                    (days,),
                )
                deleted_ids = cur.fetchall()
                deleted = len(deleted_ids)
                conn.commit()
                logger.info(f"Cleaned up {deleted} job runs older than {days} days")
                return deleted

    def get_summary(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get job runs summary from the job_runs_summary view.

        Args:
            hours: Look back this many hours (default 24)

        Returns:
            List of summary dictionaries with aggregated stats

        Raises:
            psycopg.Error: On database errors
        """
        with psycopg.connect(self._uri) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Note: The view filters to 24h by default, so we just query it
                cur.execute("SELECT * FROM job_runs_summary")
                return list(cur.fetchall())


def compute_config_fingerprint(config_dict: Dict[str, Any]) -> str:
    """
    Compute SHA-256 fingerprint of config for reproducibility.

    Useful for tracking which exact config was used for a job run,
    enabling debugging and reproducibility.

    Args:
        config_dict: Configuration dictionary (nested dicts/lists supported)

    Returns:
        16-character hex string (first 16 chars of SHA-256)

    Example:
        >>> cfg = {"providers": {"ibkr": {"port": 7497}}, "datasets": [...]}
        >>> fingerprint = compute_config_fingerprint(cfg)
        >>> print(fingerprint)
        'a3f5c8e2d9b1f6a4'
    """
    # Canonical JSON representation (sorted keys, deterministic serialization)
    canonical = json.dumps(config_dict, sort_keys=True, default=str)
    # SHA-256 hash, truncate to 16 chars for readability
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
