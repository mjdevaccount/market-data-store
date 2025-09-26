"""Initial schema for market-data-store

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-25

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # Tenants
    op.create_table(
        "tenants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(255)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )

    # Jobs Outbox
    op.create_table(
        "jobs_outbox",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("idempotency_key", sa.Text, nullable=False, unique=True),
        sa.Column("job_type", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(20), server_default="queued"),
        sa.Column("priority", sa.String(20), server_default="medium"),
        sa.Column("retries", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )

    # API Config
    op.create_table(
        "api_config",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", postgresql.JSONB, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )

    # Bars
    op.create_table(
        "bars",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id")),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("ts", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("open_price", sa.Numeric(20, 8)),
        sa.Column("high_price", sa.Numeric(20, 8)),
        sa.Column("low_price", sa.Numeric(20, 8)),
        sa.Column("close_price", sa.Numeric(20, 8)),
        sa.Column("volume", sa.BigInteger),
        sa.Column("vendor", sa.String(50), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("symbol", "timeframe", "ts", name="uq_bars"),
    )
    op.create_index("ix_bars_symbol_tf_ts", "bars", ["symbol", "timeframe", "ts"], unique=False)

    # Fundamentals
    op.create_table(
        "fundamentals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id")),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("asof", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("total_assets", sa.Numeric(25, 2)),
        sa.Column("total_liabilities", sa.Numeric(25, 2)),
        sa.Column("net_income", sa.Numeric(25, 2)),
        sa.Column("eps", sa.Numeric(10, 4)),
        sa.Column("vendor", sa.String(50), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("symbol", "asof", name="uq_fundamentals"),
    )
    op.create_index("ix_fundamentals_symbol_asof", "fundamentals", ["symbol", "asof"], unique=False)

    # News
    op.create_table(
        "news",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id")),
        sa.Column("symbol", sa.String(20)),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("url", sa.Text),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("sentiment_score", sa.Numeric(5, 4)),
        sa.Column("vendor", sa.String(50), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("symbol", "published_at", "vendor", name="uq_news"),
    )
    op.create_index("ix_news_symbol_published", "news", ["symbol", "published_at"], unique=False)

    # Options Snap
    op.create_table(
        "options_snap",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id")),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("expiry", sa.Date, nullable=False),
        sa.Column("option_type", sa.String(1), nullable=False),
        sa.Column("strike", sa.Numeric(12, 2), nullable=False),
        sa.Column("ts", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("iv", sa.Numeric(6, 4)),
        sa.Column("delta", sa.Numeric(8, 6)),
        sa.Column("gamma", sa.Numeric(10, 8)),
        sa.Column("oi", sa.BigInteger),
        sa.Column("volume", sa.BigInteger),
        sa.Column("spot", sa.Numeric(12, 4)),
        sa.Column("vendor", sa.String(50), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("symbol", "expiry", "option_type", "strike", "ts", name="uq_options"),
    )
    op.create_index(
        "ix_options_symbol_expiry_ts", "options_snap", ["symbol", "expiry", "ts"], unique=False
    )

    # Create updated_at triggers for all tables
    op.execute(
        """
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """
    )

    # Apply triggers to all tables with updated_at
    for table in [
        "tenants",
        "jobs_outbox",
        "api_config",
        "bars",
        "fundamentals",
        "news",
        "options_snap",
    ]:
        op.execute(
            f"""
            CREATE TRIGGER update_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """
        )

    # Enable Row Level Security on fact tables
    for table in ["bars", "fundamentals", "news", "options_snap"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

    # Create RLS policies for tenant isolation
    for table in ["bars", "fundamentals", "news", "options_snap"]:
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
            FOR ALL TO PUBLIC
            USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
        """
        )

    # Views
    op.execute(
        """
        CREATE OR REPLACE VIEW latest_prices AS
        SELECT DISTINCT ON (symbol)
            symbol,
            close_price as price,
            ts as price_timestamp,
            vendor
        FROM bars
        ORDER BY symbol, ts DESC
        """
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW data_freshness AS
        SELECT 'bars' as table_name, MAX(ts) as latest_asof FROM bars
        UNION ALL
        SELECT 'fundamentals', MAX(asof) FROM fundamentals
        UNION ALL
        SELECT 'news', MAX(published_at) FROM news
        """
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW job_queue_health AS
        SELECT status, priority, COUNT(*) as job_count
        FROM jobs_outbox
        GROUP BY status, priority
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS job_queue_health")
    op.execute("DROP VIEW IF EXISTS data_freshness")
    op.execute("DROP VIEW IF EXISTS latest_prices")

    # Drop triggers
    for table in [
        "tenants",
        "jobs_outbox",
        "api_config",
        "bars",
        "fundamentals",
        "news",
        "options_snap",
    ]:
        op.execute(f"DROP TRIGGER IF EXISTS update_{table}_updated_at ON {table}")

    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")

    op.drop_table("options_snap")
    op.drop_table("news")
    op.drop_table("fundamentals")
    op.drop_table("bars")
    op.drop_table("api_config")
    op.drop_table("jobs_outbox")
    op.drop_table("tenants")
