"""Add signals table for streaming inference signals

Revision ID: 0003_add_signals_table
Revises: 0002_add_bars_ohlcv_and_job_runs
Create Date: 2025-10-24

Adds:
- signals: TimescaleDB hypertable for streaming inference signals
- Compression policy for 30-day retention
- Indexes for efficient querying by provider, symbol, signal name, and time
"""

from alembic import op

# revision identifiers, used by Alembic
revision = "0003_add_signals_table"
down_revision = "0002_add_bars_ohlcv_and_job_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =====================================================================
    # signals: Streaming inference signals storage (provider-based, no RLS)
    # =====================================================================
    op.execute(
        """
        CREATE TABLE signals (
            provider  TEXT NOT NULL,
            symbol    TEXT NOT NULL CHECK (symbol = UPPER(symbol)),
            ts        TIMESTAMPTZ NOT NULL,
            name      TEXT NOT NULL,
            value     DOUBLE PRECISION NOT NULL,
            score     DOUBLE PRECISION,
            metadata  JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (provider, symbol, ts, name)
        );
    """
    )

    # Convert to TimescaleDB hypertable with 7-day chunks
    op.execute(
        """
        SELECT create_hypertable(
            'signals',
            by_range('ts'),
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
    """
    )

    # Index for common query patterns (provider, symbol, name, ts DESC)
    op.execute(
        """
        CREATE INDEX ix_signals_provider_symbol_name_ts_desc
            ON signals (provider, symbol, name, ts DESC);
    """
    )

    # Index for time-based queries
    op.execute(
        """
        CREATE INDEX ix_signals_ts_desc
            ON signals (ts DESC);
    """
    )

    # Index for signal name queries
    op.execute(
        """
        CREATE INDEX ix_signals_name_ts_desc
            ON signals (name, ts DESC);
    """
    )

    # Enable compression with 30-day hot tier
    op.execute(
        """
        ALTER TABLE signals SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'provider,symbol,name'
        );
    """
    )
    op.execute(
        """
        SELECT add_compression_policy('signals', INTERVAL '30 days');
    """
    )


def downgrade() -> None:
    """Remove signals infrastructure."""
    op.execute("DROP TABLE IF EXISTS signals CASCADE")
