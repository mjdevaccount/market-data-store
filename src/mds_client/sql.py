from __future__ import annotations

# ---------- Writes (UPSERTS) ----------

UPSERT_BARS = """
INSERT INTO bars (
    ts, tenant_id, vendor, symbol, timeframe,
    open_price, high_price, low_price, close_price, volume
) VALUES (
    %(ts)s, %(tenant_id)s, %(vendor)s, %(symbol)s, %(timeframe)s,
    %(open_price)s, %(high_price)s, %(low_price)s, %(close_price)s, %(volume)s
)
ON CONFLICT (ts, tenant_id, vendor, symbol, timeframe) DO UPDATE
SET
    open_price  = EXCLUDED.open_price,
    high_price  = EXCLUDED.high_price,
    low_price   = EXCLUDED.low_price,
    close_price = EXCLUDED.close_price,
    volume      = EXCLUDED.volume,
    updated_at  = NOW();
"""

UPSERT_FUNDAMENTALS = """
INSERT INTO fundamentals (
    asof, tenant_id, vendor, symbol,
    total_assets, total_liabilities, net_income, eps
) VALUES (
    %(asof)s, %(tenant_id)s, %(vendor)s, %(symbol)s,
    %(total_assets)s, %(total_liabilities)s, %(net_income)s, %(eps)s
)
ON CONFLICT (asof, tenant_id, vendor, symbol) DO UPDATE
SET
    total_assets      = EXCLUDED.total_assets,
    total_liabilities = EXCLUDED.total_liabilities,
    net_income        = EXCLUDED.net_income,
    eps               = EXCLUDED.eps,
    updated_at        = NOW();
"""

# News PK includes id; we'll provide an id (uuid4 if missing) in client code
UPSERT_NEWS = """
INSERT INTO news (
    published_at, tenant_id, vendor, id,
    symbol, title, url, sentiment_score
) VALUES (
    %(published_at)s, %(tenant_id)s, %(vendor)s, %(id)s,
    %(symbol)s, %(title)s, %(url)s, %(sentiment_score)s
)
ON CONFLICT (published_at, tenant_id, vendor, id) DO UPDATE
SET
    symbol          = EXCLUDED.symbol,
    title           = EXCLUDED.title,
    url             = EXCLUDED.url,
    sentiment_score = EXCLUDED.sentiment_score,
    updated_at      = NOW();
"""

UPSERT_OPTIONS = """
INSERT INTO options_snap (
    ts, tenant_id, vendor, symbol, expiry, option_type, strike,
    iv, delta, gamma, oi, volume, spot
) VALUES (
    %(ts)s, %(tenant_id)s, %(vendor)s, %(symbol)s, %(expiry)s, %(option_type)s, %(strike)s,
    %(iv)s, %(delta)s, %(gamma)s, %(oi)s, %(volume)s, %(spot)s
)
ON CONFLICT (ts, tenant_id, vendor, symbol, expiry, option_type, strike) DO UPDATE
SET
    iv       = EXCLUDED.iv,
    delta    = EXCLUDED.delta,
    gamma    = EXCLUDED.gamma,
    oi       = EXCLUDED.oi,
    volume   = EXCLUDED.volume,
    spot     = EXCLUDED.spot,
    updated_at = NOW();
"""

ENQUEUE_JOB = """
INSERT INTO jobs_outbox (idempotency_key, job_type, payload, status, priority, retries)
VALUES (%(idempotency_key)s, %(job_type)s, %(payload)s, 'queued', %(priority)s, 0)
ON CONFLICT (idempotency_key) DO NOTHING;
"""

# ---------- Reads ----------

HEALTH = "SELECT 1;"
SCHEMA_VERSION = "SELECT version_num FROM alembic_version LIMIT 1;"

LATEST_PRICES = """
SELECT tenant_id, vendor, symbol, price, price_timestamp
FROM latest_prices
WHERE vendor = %(vendor)s
  AND symbol = ANY(%(symbols)s)
  AND tenant_id = current_setting('app.tenant_id', true)::uuid;
"""

BARS_WINDOW = """
SELECT ts, open_price, high_price, low_price, close_price, volume
FROM bars
WHERE vendor = %(vendor)s
  AND symbol = %(symbol)s
  AND timeframe = %(timeframe)s
  AND ts >= %(start)s AND ts < %(end)s
  AND tenant_id = current_setting('app.tenant_id', true)::uuid
ORDER BY ts;
"""
