-- Market Data Store: Signals table for streaming inference
-- PostgreSQL 15 + TimescaleDB OSS

--------------------------
-- signals: Streaming inference signals storage (provider-based, no RLS)
--------------------------
CREATE TABLE IF NOT EXISTS signals (
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

-- Convert to TimescaleDB hypertable with 7-day chunks
SELECT create_hypertable(
    'signals',
    by_range('ts'),
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Index for common query patterns (provider, symbol, name, ts DESC)
CREATE INDEX IF NOT EXISTS ix_signals_provider_symbol_name_ts_desc
    ON signals (provider, symbol, name, ts DESC);

-- Index for time-based queries
CREATE INDEX IF NOT EXISTS ix_signals_ts_desc
    ON signals (ts DESC);

-- Index for signal name queries
CREATE INDEX IF NOT EXISTS ix_signals_name_ts_desc
    ON signals (name, ts DESC);

-- Enable compression with 30-day hot tier
ALTER TABLE signals SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'provider,symbol,name'
);
SELECT add_compression_policy('signals', INTERVAL '30 days');

-- Trigger for signals
DROP TRIGGER IF EXISTS update_signals_updated_at ON signals;
CREATE TRIGGER update_signals_updated_at
    BEFORE UPDATE ON signals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
