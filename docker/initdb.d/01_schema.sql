-- Market Data Store: Production-Ready Base Schema (TimescaleDB + RLS)
-- PostgreSQL 15 + TimescaleDB OSS

--------------------------
-- Extensions
--------------------------
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pgcrypto;     -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- optional

-- Session TZ for this script + persistent DB default
SET TIME ZONE 'UTC';
ALTER DATABASE market_data SET timezone TO 'UTC';

--------------------------
-- Tenants
--------------------------
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

--------------------------
-- Jobs Outbox (tenant-scoped; RLS)
--------------------------
CREATE TABLE IF NOT EXISTS jobs_outbox (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL UNIQUE,
    job_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','completed','failed','deadletter')),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low','medium','high','urgent')),
    retries INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_jobs_outbox_status_created
  ON jobs_outbox (tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_jobs_outbox_priority_created
  ON jobs_outbox (tenant_id, priority, created_at DESC);

--------------------------
-- API Config (tenant-scoped)
--------------------------
CREATE TABLE IF NOT EXISTS api_config (
    key TEXT NOT NULL,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT api_config_pk PRIMARY KEY (tenant_id, key)
);

--------------------------
-- Bars (PK: time first)
--------------------------
CREATE TABLE IF NOT EXISTS bars (
    id UUID NOT NULL DEFAULT gen_random_uuid(),  -- non-unique handle
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    vendor VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL CHECK (symbol = UPPER(symbol)),
    timeframe VARCHAR(16) NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    open_price  NUMERIC(20,8),
    high_price  NUMERIC(20,8),
    low_price   NUMERIC(20,8),
    close_price NUMERIC(20,8),
    volume BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT bars_pk PRIMARY KEY (ts, tenant_id, vendor, symbol, timeframe)
);
CREATE INDEX IF NOT EXISTS ix_bars_id ON bars (id);
CREATE INDEX IF NOT EXISTS ix_bars_tenant_vendor_sym_tf_ts_desc
  ON bars (tenant_id, vendor, symbol, timeframe, ts DESC);

--------------------------
-- Fundamentals (PK: time first)
--------------------------
CREATE TABLE IF NOT EXISTS fundamentals (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    vendor VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL CHECK (symbol = UPPER(symbol)),
    asof TIMESTAMPTZ NOT NULL,
    total_assets       NUMERIC(25,2),
    total_liabilities  NUMERIC(25,2),
    net_income         NUMERIC(25,2),
    eps                NUMERIC(10,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fundamentals_pk PRIMARY KEY (asof, tenant_id, vendor, symbol)
);
CREATE INDEX IF NOT EXISTS ix_fundamentals_id ON fundamentals (id);
CREATE INDEX IF NOT EXISTS ix_fundamentals_tenant_vendor_sym_asof_desc
  ON fundamentals (tenant_id, vendor, symbol, asof DESC);

--------------------------
-- News (PK: time first; symbol nullable)
--------------------------
CREATE TABLE IF NOT EXISTS news (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    vendor VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) CHECK (symbol IS NULL OR symbol = UPPER(symbol)),
    title TEXT NOT NULL,
    url TEXT,
    published_at TIMESTAMPTZ NOT NULL,
    sentiment_score NUMERIC(5,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT news_pk PRIMARY KEY (published_at, tenant_id, vendor, id)
);
CREATE INDEX IF NOT EXISTS ix_news_tenant_vendor_symbol_pub_desc
  ON news (tenant_id, vendor, symbol, published_at DESC);

--------------------------
-- Options Snap (PK: time first)
--------------------------
CREATE TABLE IF NOT EXISTS options_snap (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    vendor VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL CHECK (symbol = UPPER(symbol)),
    expiry DATE NOT NULL,
    option_type VARCHAR(1) NOT NULL CHECK (option_type IN ('C','P')),
    strike NUMERIC(12,2) NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    iv NUMERIC(6,4),
    delta NUMERIC(8,6),
    gamma NUMERIC(10,8),
    oi BIGINT,
    volume BIGINT,
    spot NUMERIC(12,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT options_snap_pk PRIMARY KEY (ts, tenant_id, vendor, symbol, expiry, option_type, strike)
);
CREATE INDEX IF NOT EXISTS ix_options_id ON options_snap (id);
CREATE INDEX IF NOT EXISTS ix_options_tenant_vendor_sym_expiry_ts_desc
  ON options_snap (tenant_id, vendor, symbol, expiry, ts DESC);

--------------------------
-- Updated-at trigger
--------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE t TEXT;
BEGIN
  FOR t IN SELECT unnest(ARRAY['tenants','jobs_outbox','api_config','bars','fundamentals','news','options_snap'])
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS update_%1$s_updated_at ON %1$s;', t);
    EXECUTE format($fmt$
      CREATE TRIGGER update_%1$s_updated_at
      BEFORE UPDATE ON %1$s
      FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    $fmt$, t);
  END LOOP;
END$$;

--------------------------
-- Hypertables (explicit chunk sizes)
--------------------------
SELECT create_hypertable('bars',         'ts',           chunk_time_interval => INTERVAL '7 days',   if_not_exists => TRUE);
SELECT create_hypertable('fundamentals', 'asof',         chunk_time_interval => INTERVAL '90 days',  if_not_exists => TRUE);
SELECT create_hypertable('news',         'published_at', chunk_time_interval => INTERVAL '30 days',  if_not_exists => TRUE);
SELECT create_hypertable('options_snap', 'ts',           chunk_time_interval => INTERVAL '7 days',   if_not_exists => TRUE);

--------------------------
-- RLS + FORCE RLS (deny if tenant header not set)
--------------------------
ALTER TABLE jobs_outbox   ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_config    ENABLE ROW LEVEL SECURITY;
ALTER TABLE bars          ENABLE ROW LEVEL SECURITY;
ALTER TABLE fundamentals  ENABLE ROW LEVEL SECURITY;
ALTER TABLE news          ENABLE ROW LEVEL SECURITY;
ALTER TABLE options_snap  ENABLE ROW LEVEL SECURITY;

ALTER TABLE jobs_outbox   FORCE ROW LEVEL SECURITY;
ALTER TABLE api_config    FORCE ROW LEVEL SECURITY;
ALTER TABLE bars          FORCE ROW LEVEL SECURITY;
ALTER TABLE fundamentals  FORCE ROW LEVEL SECURITY;
ALTER TABLE news          FORCE ROW LEVEL SECURITY;
ALTER TABLE options_snap  FORCE ROW LEVEL SECURITY;

DO $$
DECLARE t TEXT;
BEGIN
  FOR t IN SELECT unnest(ARRAY['jobs_outbox','api_config','bars','fundamentals','news','options_snap'])
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_%1$s ON %1$s;', t);
    EXECUTE format($policy$
      CREATE POLICY tenant_isolation_%1$s ON %1$s
      USING (
        current_setting('app.tenant_id', true) IS NOT NULL
        AND tenant_id = current_setting('app.tenant_id', true)::uuid
      )
      WITH CHECK (
        current_setting('app.tenant_id', true) IS NOT NULL
        AND tenant_id = current_setting('app.tenant_id', true)::uuid
      );
    $policy$, t);
  END LOOP;
END$$;

--------------------------
-- Views (RLS applies)
--------------------------
CREATE OR REPLACE VIEW latest_prices AS
SELECT DISTINCT ON (tenant_id, vendor, symbol)
    tenant_id,
    vendor,
    symbol,
    close_price AS price,
    ts AS price_timestamp
FROM bars
ORDER BY tenant_id, vendor, symbol, ts DESC;

CREATE OR REPLACE VIEW data_freshness AS
SELECT 'bars' AS table_name, MAX(ts) FROM bars
UNION ALL
SELECT 'fundamentals', MAX(asof) FROM fundamentals
UNION ALL
SELECT 'news', MAX(published_at) FROM news;

CREATE OR REPLACE VIEW job_queue_health AS
SELECT status, priority, COUNT(*) AS job_count
FROM jobs_outbox
GROUP BY status, priority;

--------------------------
-- bars_ohlcv (Provider-based OHLCV storage, no tenant isolation)
-- Optional: For config-driven pipeline ingestion
--------------------------
CREATE TABLE IF NOT EXISTS bars_ohlcv (
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
CREATE INDEX IF NOT EXISTS ix_bars_ohlcv_provider_symbol_interval_ts_desc
    ON bars_ohlcv (provider, symbol, interval, ts DESC);

-- Hypertable + compression for bars_ohlcv
SELECT create_hypertable('bars_ohlcv', by_range('ts'),
    chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);
ALTER TABLE bars_ohlcv SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'provider,symbol,interval'
);
SELECT add_compression_policy('bars_ohlcv', INTERVAL '90 days');

-- Trigger for bars_ohlcv
DROP TRIGGER IF EXISTS update_bars_ohlcv_updated_at ON bars_ohlcv;
CREATE TRIGGER update_bars_ohlcv_updated_at
    BEFORE UPDATE ON bars_ohlcv
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

--------------------------
-- job_runs (Audit-grade job execution tracking)
--------------------------
CREATE TABLE IF NOT EXISTS job_runs (
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
    elapsed_ms          BIGINT GENERATED ALWAYS AS (
                            CASE
                                WHEN completed_at IS NOT NULL
                                THEN EXTRACT(EPOCH FROM (completed_at - started_at)) * 1000
                                ELSE NULL
                            END
                        ) STORED
);

-- Indexes for operational queries
CREATE INDEX IF NOT EXISTS ix_job_runs_job_name_started
    ON job_runs (job_name, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_job_runs_job_status_completed
    ON job_runs (job_name, status, completed_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS ix_job_runs_provider_status
    ON job_runs (provider, status);
CREATE INDEX IF NOT EXISTS ix_job_runs_started_desc
    ON job_runs (started_at DESC);
CREATE INDEX IF NOT EXISTS ix_job_runs_metadata_heartbeat
    ON job_runs USING GIN (metadata jsonb_path_ops);

-- Trigger for job_runs
DROP TRIGGER IF EXISTS update_job_runs_updated_at ON job_runs;
CREATE TRIGGER update_job_runs_updated_at
    BEFORE UPDATE ON job_runs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Monitoring view for dashboards
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
