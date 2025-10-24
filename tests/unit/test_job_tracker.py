"""
Unit tests for JobRunTracker.

Tests:
- Job run lifecycle (start, update, complete)
- Heartbeat mechanism
- Config fingerprinting
- Query methods (recent, stuck, summary)
- Cleanup operations
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from datastore.job_tracking import JobRunTracker, compute_config_fingerprint


class TestJobRunLifecycle:
    """Test complete job run lifecycle."""

    @patch("datastore.job_tracking.psycopg.connect")
    def test_start_run_returns_id(self, mock_connect):
        """start_run should insert row and return run_id."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (123,)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        tracker = JobRunTracker("postgresql://test")
        run_id = tracker.start_run(
            job_name="test_job",
            provider="ibkr",
            mode="live",
            config_fingerprint="abc123",
        )

        assert run_id == 123
        mock_cursor.execute.assert_called_once()
        assert "INSERT INTO job_runs" in mock_cursor.execute.call_args[0][0]
        mock_conn.commit.assert_called_once()

    @patch("datastore.job_tracking.psycopg.connect")
    def test_complete_run_updates_status(self, mock_connect):
        """complete_run should update status and completed_at."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Now returns (job_name, provider, mode, elapsed_ms) for metrics
        mock_cursor.fetchone.return_value = ("test_job", "ibkr", "live", 5000)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        tracker = JobRunTracker("postgresql://test")
        tracker.complete_run(run_id=123, status="success")

        # Should have two execute calls (UPDATE and SELECT elapsed_ms)
        assert mock_cursor.execute.call_count == 2
        update_call = mock_cursor.execute.call_args_list[0]
        assert "UPDATE job_runs" in update_call[0][0]
        assert "success" in update_call[0][1]
        mock_conn.commit.assert_called_once()

    @patch("datastore.job_tracking.psycopg.connect")
    def test_complete_run_validates_status(self, mock_connect):
        """complete_run should reject invalid status values."""
        tracker = JobRunTracker("postgresql://test")

        with pytest.raises(ValueError, match="Invalid status"):
            tracker.complete_run(run_id=123, status="invalid_status")


class TestUpdateProgress:
    """Test progress update with heartbeats."""

    @patch("datastore.job_tracking.psycopg.connect")
    def test_update_progress_increments_counters(self, mock_connect):
        """update_progress should increment rows_written and rows_failed."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        tracker = JobRunTracker("postgresql://test")
        tracker.update_progress(run_id=123, rows_written=1000, rows_failed=5, heartbeat=False)

        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        assert "rows_written = rows_written +" in sql
        assert "rows_failed = rows_failed +" in sql
        mock_conn.commit.assert_called_once()

    @patch("datastore.job_tracking.psycopg.connect")
    def test_update_progress_with_heartbeat(self, mock_connect):
        """update_progress with heartbeat should update metadata."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        tracker = JobRunTracker("postgresql://test")
        tracker.update_progress(run_id=123, rows_written=100, heartbeat=True)

        # Should have two execute calls (UPDATE counters, UPDATE metadata)
        assert mock_cursor.execute.call_count == 2
        heartbeat_call = mock_cursor.execute.call_args_list[1]
        assert "jsonb_set" in heartbeat_call[0][0]
        assert "last_heartbeat" in heartbeat_call[0][0]

    @patch("datastore.job_tracking.psycopg.connect")
    def test_update_progress_updates_time_window(self, mock_connect):
        """update_progress should track min/max timestamps."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        min_ts = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
        max_ts = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)

        tracker = JobRunTracker("postgresql://test")
        tracker.update_progress(
            run_id=123, rows_written=100, min_ts=min_ts, max_ts=max_ts, heartbeat=False
        )

        sql = mock_cursor.execute.call_args[0][0]
        assert "min_ts" in sql
        assert "max_ts" in sql
        assert "LEAST" in sql
        assert "GREATEST" in sql


class TestQueryMethods:
    """Test query methods for job runs."""

    @patch("datastore.job_tracking.psycopg.connect")
    def test_get_recent_runs(self, mock_connect):
        """get_recent_runs should return list of recent runs."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"id": 1, "job_name": "job1"},
            {"id": 2, "job_name": "job2"},
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        tracker = JobRunTracker("postgresql://test")
        runs = tracker.get_recent_runs(limit=10)

        assert len(runs) == 2
        assert runs[0]["id"] == 1
        sql = mock_cursor.execute.call_args[0][0]
        assert "ORDER BY started_at DESC" in sql
        assert "LIMIT" in sql

    @patch("datastore.job_tracking.psycopg.connect")
    def test_get_recent_runs_with_filter(self, mock_connect):
        """get_recent_runs should support job_name filter."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        tracker = JobRunTracker("postgresql://test")
        tracker.get_recent_runs(limit=10, job_name="specific_job")

        sql = mock_cursor.execute.call_args[0][0]
        assert "WHERE job_name" in sql

    @patch("datastore.job_tracking.psycopg.connect")
    def test_get_run(self, mock_connect):
        """get_run should return specific run by ID."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"id": 123, "job_name": "test"}
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        tracker = JobRunTracker("postgresql://test")
        run = tracker.get_run(123)

        assert run is not None
        assert run["id"] == 123
        sql = mock_cursor.execute.call_args[0][0]
        assert "WHERE id" in sql

    @patch("datastore.job_tracking.psycopg.connect")
    def test_get_run_not_found(self, mock_connect):
        """get_run should return None if run doesn't exist."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        tracker = JobRunTracker("postgresql://test")
        run = tracker.get_run(999)

        assert run is None


class TestStuckRunDetection:
    """Test stuck run detection via heartbeat timeout."""

    @patch("datastore.job_tracking.psycopg.connect")
    def test_get_stuck_runs(self, mock_connect):
        """get_stuck_runs should find runs with stale heartbeats."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {"id": 1, "job_name": "stuck_job", "status": "running"}
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        tracker = JobRunTracker("postgresql://test")
        stuck = tracker.get_stuck_runs(heartbeat_timeout_minutes=15)

        assert len(stuck) == 1
        assert stuck[0]["job_name"] == "stuck_job"
        sql = mock_cursor.execute.call_args[0][0]
        assert "status = 'running'" in sql
        assert "last_heartbeat" in sql
        assert "15" in str(mock_cursor.execute.call_args[0][1])


class TestCleanup:
    """Test cleanup operations."""

    @patch("datastore.job_tracking.psycopg.connect")
    def test_cleanup_old_runs(self, mock_connect):
        """cleanup_old_runs should delete old completed runs."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [(1,), (2,), (3,)]  # 3 deleted IDs
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        tracker = JobRunTracker("postgresql://test")
        deleted = tracker.cleanup_old_runs(days=90)

        assert deleted == 3
        sql = mock_cursor.execute.call_args[0][0]
        assert "DELETE FROM job_runs" in sql
        assert "completed_at" in sql
        assert "90" in str(mock_cursor.execute.call_args[0][1])
        mock_conn.commit.assert_called_once()


class TestSummaryView:
    """Test job_runs_summary view query."""

    @patch("datastore.job_tracking.psycopg.connect")
    def test_get_summary(self, mock_connect):
        """get_summary should query job_runs_summary view."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                "job_name": "job1",
                "provider": "ibkr",
                "status": "success",
                "run_count": 10,
                "avg_duration_ms": 5000,
            }
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        tracker = JobRunTracker("postgresql://test")
        summary = tracker.get_summary()

        assert len(summary) == 1
        assert summary[0]["job_name"] == "job1"
        sql = mock_cursor.execute.call_args[0][0]
        assert "job_runs_summary" in sql


class TestConfigFingerprint:
    """Test config fingerprinting for reproducibility."""

    def test_compute_config_fingerprint_deterministic(self):
        """Same config should produce same fingerprint."""
        config = {"provider": "ibkr", "symbols": ["SPY", "AAPL"], "interval": "5min"}

        fp1 = compute_config_fingerprint(config)
        fp2 = compute_config_fingerprint(config)

        assert fp1 == fp2
        assert isinstance(fp1, str)
        assert len(fp1) == 16  # truncated SHA-256

    def test_compute_config_fingerprint_key_order_irrelevant(self):
        """Key order shouldn't affect fingerprint (sorted internally)."""
        config1 = {"a": 1, "b": 2, "c": 3}
        config2 = {"c": 3, "a": 1, "b": 2}

        fp1 = compute_config_fingerprint(config1)
        fp2 = compute_config_fingerprint(config2)

        assert fp1 == fp2

    def test_compute_config_fingerprint_different_configs(self):
        """Different configs should produce different fingerprints."""
        config1 = {"provider": "ibkr", "symbols": ["SPY"]}
        config2 = {"provider": "polygon", "symbols": ["SPY"]}

        fp1 = compute_config_fingerprint(config1)
        fp2 = compute_config_fingerprint(config2)

        assert fp1 != fp2

    def test_compute_config_fingerprint_nested(self):
        """Nested dicts should be handled correctly."""
        config = {
            "providers": {"ibkr": {"port": 7497, "paper": True}},
            "datasets": [{"name": "us_equities", "symbols": ["SPY"]}],
        }

        fp = compute_config_fingerprint(config)

        assert isinstance(fp, str)
        assert len(fp) == 16


class TestMetadata:
    """Test metadata handling (JSONB field)."""

    @patch("datastore.job_tracking.psycopg.connect")
    def test_start_run_with_metadata(self, mock_connect):
        """start_run should accept and store metadata dict."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (123,)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        tracker = JobRunTracker("postgresql://test")
        metadata = {"git_hash": "abc123", "container_id": "xyz"}
        run_id = tracker.start_run(job_name="test", mode="live", metadata=metadata)

        assert run_id == 123
        # Metadata should be JSON-serialized in the call
        call_args = mock_cursor.execute.call_args[0][1]
        assert '{"git_hash": "abc123"' in str(call_args)


class TestJobRunMetrics:
    """Test Prometheus metrics integration."""

    @patch("datastore.job_tracking.psycopg.connect")
    @patch("datastore.job_tracking.JOB_RUNS_TOTAL")
    def test_start_run_increments_started_metric(self, mock_metric, mock_connect):
        """start_run should increment JOB_RUNS_TOTAL with status='started'."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (123,)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        mock_labels = MagicMock()
        mock_metric.labels.return_value = mock_labels

        tracker = JobRunTracker("postgresql://test")
        tracker.start_run(job_name="test_job", provider="ibkr", mode="live")

        mock_metric.labels.assert_called_once_with(
            job_name="test_job", provider="ibkr", mode="live", status="started"
        )
        mock_labels.inc.assert_called_once()

    @patch("datastore.job_tracking.psycopg.connect")
    @patch("datastore.job_tracking.JOB_RUNS_TOTAL")
    @patch("datastore.job_tracking.JOB_RUNS_DURATION")
    def test_complete_run_records_metrics(self, mock_duration, mock_total, mock_connect):
        """complete_run should record status metric and duration histogram."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # First call (UPDATE), second call (SELECT for metrics)
        mock_cursor.fetchone.return_value = ("test_job", "ibkr", "live", 5000)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        mock_total_labels = MagicMock()
        mock_total.labels.return_value = mock_total_labels
        mock_duration_labels = MagicMock()
        mock_duration.labels.return_value = mock_duration_labels

        tracker = JobRunTracker("postgresql://test")
        tracker.complete_run(run_id=123, status="success")

        # Should record total with final status
        mock_total.labels.assert_called_once_with(
            job_name="test_job", provider="ibkr", mode="live", status="success"
        )
        mock_total_labels.inc.assert_called_once()

        # Should record duration histogram (5000ms = 5.0s)
        mock_duration.labels.assert_called_once_with(
            job_name="test_job", provider="ibkr", mode="live", status="success"
        )
        mock_duration_labels.observe.assert_called_once_with(5.0)

    @patch("datastore.job_tracking.psycopg.connect")
    @patch("datastore.job_tracking.JOB_RUNS_TOTAL")
    def test_complete_run_handles_missing_provider(self, mock_metric, mock_connect):
        """complete_run should use 'unknown' for missing provider."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("test_job", None, "live", None)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_connect.return_value.__enter__.return_value = mock_conn

        mock_labels = MagicMock()
        mock_metric.labels.return_value = mock_labels

        tracker = JobRunTracker("postgresql://test")
        tracker.complete_run(run_id=123, status="failure")

        mock_metric.labels.assert_called_once_with(
            job_name="test_job", provider="unknown", mode="live", status="failure"
        )
        mock_labels.inc.assert_called_once()
