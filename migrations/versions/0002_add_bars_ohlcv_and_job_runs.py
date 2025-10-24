"""Add bars_ohlcv and job_runs tables for config-driven pipeline

Revision ID: 0002_add_bars_ohlcv_and_job_runs
Revises: 0001_initial
Create Date: 2025-10-24

Adds:
- bars_ohlcv: Provider-based OHLCV storage with TimescaleDB compression
- job_runs: Audit-grade job execution tracking with heartbeats and derived columns
- job_runs_summary: Monitoring view for dashboards
"""

from alembic import op

# revision identifiers, used by Alembic
revision = "0002_add_bars_ohlcv_and_job_runs"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =====================================================================
    # bars_ohlcv: Provider-based OHLCV storage (non-tenant, no RLS)
    # =====================================================================
    op.execute(
        """
        CREATE TABLE bars_ohlcv (
            provider   TEXT NOT NULL,
            symbol     TEXT NOT NULL CHECK (symbol = UPPER(symbol)),
            interval   TEXT NOT NULL,
            ts         TIMESTAMPTZ NOT NULL,
            open       DOUBLE PRECISION NOT NULL,
            high       DOUBLE PRECISION NOT NULL,
            low        DOUBLE PRECISION NOT NULL,
            close      DOUBLE PRECISION NOT NULL,
            volume     DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT bars_ohlcv_pk PRIMARY KEY (provider, symbol, interval, ts)
        );
    """
    )

    # Convert to TimescaleDB hypertable with 7-day chunks
    op.execute(
        """
        SELECT create_hypertable(
            'bars_ohlcv',
            'ts',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
    """
    )

    # Index for common query patterns (provider, symbol, interval, ts DESC)
    op.execute(
        """
        CREATE INDEX ix_bars_ohlcv_provider_symbol_interval_ts_desc
            ON bars_ohlcv (provider, symbol, interval, ts DESC);
    """
    )

    # Enable compression with 90-day hot tier
    op.execute(
        """
        ALTER TABLE bars_ohlcv SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'provider,symbol,interval'
        );
    """
    )
    op.execute(
        """
        SELECT add_compression_policy('bars_ohlcv', INTERVAL '90 days');
    """
    )

    # Updated_at trigger (reuses existing function)
    op.execute(
        """
        CREATE TRIGGER bars_ohlcv_set_updated_at
            BEFORE UPDATE ON bars_ohlcv
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """
    )

    # =====================================================================
    # job_runs: Audit-grade job execution tracking
    # =====================================================================
    op.execute(
        """
        CREATE TABLE job_runs (
            id                  BIGSERIAL PRIMARY KEY,
            job_name            TEXT NOT NULL,
            dataset_name        TEXT,
            provider            TEXT,
            mode                TEXT NOT NULL CHECK (mode IN ('live', 'backfill')),
            status              TEXT NOT NULL DEFAULT 'running'
                                CHECK (status IN ('running', 'success', 'failure', 'cancelled')),
            config_fingerprint  TEXT,
            pipeline_version    TEXT,
            rows_written        BIGINT DEFAULT 0,
            rows_failed         BIGINT DEFAULT 0,
            symbols             TEXT[],
            min_ts              TIMESTAMPTZ,
            max_ts              TIMESTAMPTZ,
            error_message       TEXT,
            metadata            JSONB DEFAULT '{}'::jsonb,
            started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at        TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

            -- Derived column for Grafana dashboards
            elapsed_ms          BIGINT GENERATED ALWAYS AS (
                                    CASE
                                        WHEN completed_at IS NOT NULL
                                        THEN EXTRACT(EPOCH FROM (completed_at - started_at)) * 1000
                                        ELSE NULL
                                    END
                                ) STORED
        );
    """
    )

    # Indexes for operational queries
    op.execute(
        """
        CREATE INDEX ix_job_runs_job_name_started
            ON job_runs (job_name, started_at DESC);
    """
    )
    op.execute(
        """
        CREATE INDEX ix_job_runs_job_status_completed
            ON job_runs (job_name, status, completed_at DESC NULLS LAST);
    """
    )
    op.execute(
        """
        CREATE INDEX ix_job_runs_provider_status
            ON job_runs (provider, status);
    """
    )
    op.execute(
        """
        CREATE INDEX ix_job_runs_started_desc
            ON job_runs (started_at DESC);
    """
    )
    # GIN index for fast heartbeat/metadata queries
    op.execute(
        """
        CREATE INDEX ix_job_runs_metadata_heartbeat
            ON job_runs USING GIN (metadata jsonb_path_ops);
    """
    )

    # Updated_at trigger for job_runs
    op.execute(
        """
        CREATE TRIGGER job_runs_set_updated_at
            BEFORE UPDATE ON job_runs
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    """
    )

    # =====================================================================
    # job_runs_summary: Monitoring view for dashboards
    # =====================================================================
    op.execute(
        """
        CREATE OR REPLACE VIEW job_runs_summary AS
        SELECT
            job_name,
            provider,
            status,
            COUNT(*) as run_count,
            AVG(elapsed_ms) as avg_duration_ms,
            SUM(rows_written) as total_rows,
            MAX(started_at) as last_run_at,
            COUNT(*) FILTER (WHERE status = 'failure') as failure_count
        FROM job_runs
        WHERE started_at > NOW() - INTERVAL '24 hours'
        GROUP BY job_name, provider, status
        ORDER BY last_run_at DESC;
    """
    )


def downgrade() -> None:
    """Remove bars_ohlcv and job_runs infrastructure."""
    op.execute("DROP VIEW IF EXISTS job_runs_summary")
    op.execute("DROP TABLE IF EXISTS job_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS bars_ohlcv CASCADE")
