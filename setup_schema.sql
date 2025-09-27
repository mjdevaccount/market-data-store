-- Create extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Tenants table
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Jobs Outbox table
CREATE TABLE IF NOT EXISTS jobs_outbox (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    job_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'queued',
    priority VARCHAR(20) DEFAULT 'medium',
    retries INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- API Config table
CREATE TABLE IF NOT EXISTS api_config (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Bars table
CREATE TABLE IF NOT EXISTS bars (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    symbol VARCHAR(20) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    open_price NUMERIC(20, 8),
    high_price NUMERIC(20, 8),
    low_price NUMERIC(20, 8),
    close_price NUMERIC(20, 8),
    volume BIGINT,
    vendor VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_bars UNIQUE (symbol, timeframe, ts)
);

CREATE INDEX IF NOT EXISTS ix_bars_symbol_tf_ts ON bars (symbol, timeframe, ts);

-- Fundamentals table
CREATE TABLE IF NOT EXISTS fundamentals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    symbol VARCHAR(20) NOT NULL,
    asof TIMESTAMPTZ NOT NULL,
    total_assets NUMERIC(25, 2),
    total_liabilities NUMERIC(25, 2),
    net_income NUMERIC(25, 2),
    eps NUMERIC(10, 4),
    vendor VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_fundamentals UNIQUE (symbol, asof)
);

CREATE INDEX IF NOT EXISTS ix_fundamentals_symbol_asof ON fundamentals (symbol, asof);

-- News table
CREATE TABLE IF NOT EXISTS news (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    symbol VARCHAR(20),
    title TEXT NOT NULL,
    url TEXT,
    published_at TIMESTAMPTZ NOT NULL,
    sentiment_score NUMERIC(5, 4),
    vendor VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_news UNIQUE (symbol, published_at, vendor)
);

CREATE INDEX IF NOT EXISTS ix_news_symbol_published ON news (symbol, published_at);

-- Options Snap table
CREATE TABLE IF NOT EXISTS options_snap (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    symbol VARCHAR(20) NOT NULL,
    expiry DATE NOT NULL,
    option_type VARCHAR(1) NOT NULL,
    strike NUMERIC(12, 2) NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    iv NUMERIC(6, 4),
    delta NUMERIC(8, 6),
    gamma NUMERIC(10, 8),
    oi BIGINT,
    volume BIGINT,
    spot NUMERIC(12, 4),
    vendor VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_options UNIQUE (symbol, expiry, option_type, strike, ts)
);

CREATE INDEX IF NOT EXISTS ix_options_symbol_expiry_ts ON options_snap (symbol, expiry, ts);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply triggers to all tables with updated_at
DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOR table_name IN SELECT unnest(ARRAY['tenants', 'jobs_outbox', 'api_config', 'bars', 'fundamentals', 'news', 'options_snap']) LOOP
        EXECUTE format('
            DROP TRIGGER IF EXISTS update_%s_updated_at ON %s;
            CREATE TRIGGER update_%s_updated_at
            BEFORE UPDATE ON %s
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        ', table_name, table_name, table_name, table_name);
    END LOOP;
END $$;

-- Enable Row Level Security on fact tables
ALTER TABLE bars ENABLE ROW LEVEL SECURITY;
ALTER TABLE fundamentals ENABLE ROW LEVEL SECURITY;
ALTER TABLE news ENABLE ROW LEVEL SECURITY;
ALTER TABLE options_snap ENABLE ROW LEVEL SECURITY;

-- Create RLS policies for tenant isolation
DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOR table_name IN SELECT unnest(ARRAY['bars', 'fundamentals', 'news', 'options_snap']) LOOP
        EXECUTE format('
            DROP POLICY IF EXISTS tenant_isolation_%s ON %s;
            CREATE POLICY tenant_isolation_%s ON %s
            USING (tenant_id = current_setting(''app.tenant_id'', true)::uuid)
            WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true)::uuid);
        ', table_name, table_name, table_name, table_name);
    END LOOP;
END $$;

-- Create views
CREATE OR REPLACE VIEW latest_prices AS
SELECT DISTINCT ON (symbol)
    symbol,
    close_price as price,
    ts as price_timestamp,
    vendor
FROM bars
ORDER BY symbol, ts DESC;

CREATE OR REPLACE VIEW data_freshness AS
SELECT 'bars' as table_name, MAX(ts) as latest_asof FROM bars
UNION ALL
SELECT 'fundamentals', MAX(asof) FROM fundamentals
UNION ALL
SELECT 'news', MAX(published_at) FROM news;

CREATE OR REPLACE VIEW job_queue_health AS
SELECT status, priority, COUNT(*) as job_count
FROM jobs_outbox
GROUP BY status, priority;
