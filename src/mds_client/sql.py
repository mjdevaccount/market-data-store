"""
SQL statements and parameter mappers for Market Data Store operations.

All statements use the composite primary keys with time columns first
for TimescaleDB compatibility.
"""

from .models import Bar, Fundamentals, News, OptionSnap


class SQL:
    """SQL statements with conflict resolution on composite primary keys."""

    UPSERT_BARS = """
    INSERT INTO bars (
      ts, tenant_id, vendor, symbol, timeframe,
      open_price, high_price, low_price, close_price, volume, id
    ) VALUES (
      %(ts)s, %(tenant_id)s, %(vendor)s, %(symbol)s, %(timeframe)s,
      %(open_price)s, %(high_price)s, %(low_price)s, %(close_price)s, %(volume)s, %(id)s
    )
    ON CONFLICT ON CONSTRAINT bars_pk DO UPDATE SET
      open_price = EXCLUDED.open_price,
      high_price = EXCLUDED.high_price,
      low_price  = EXCLUDED.low_price,
      close_price= EXCLUDED.close_price,
      volume     = EXCLUDED.volume,
      updated_at = NOW();
    """

    UPSERT_FUNDAMENTALS = """
    INSERT INTO fundamentals (
      asof, tenant_id, vendor, symbol,
      total_assets, total_liabilities, net_income, eps, id
    ) VALUES (
      %(asof)s, %(tenant_id)s, %(vendor)s, %(symbol)s,
      %(total_assets)s, %(total_liabilities)s, %(net_income)s, %(eps)s, %(id)s
    )
    ON CONFLICT ON CONSTRAINT fundamentals_pk DO UPDATE SET
      total_assets      = EXCLUDED.total_assets,
      total_liabilities = EXCLUDED.total_liabilities,
      net_income        = EXCLUDED.net_income,
      eps               = EXCLUDED.eps,
      updated_at        = NOW();
    """

    UPSERT_NEWS = """
    INSERT INTO news (
      published_at, tenant_id, vendor, id, symbol, title, url, sentiment_score
    ) VALUES (
      %(published_at)s, %(tenant_id)s, %(vendor)s, %(id)s, %(symbol)s, %(title)s, %(url)s, %(sentiment_score)s
    )
    ON CONFLICT ON CONSTRAINT news_pk DO UPDATE SET
      symbol          = EXCLUDED.symbol,
      title           = EXCLUDED.title,
      url             = EXCLUDED.url,
      sentiment_score = EXCLUDED.sentiment_score,
      updated_at      = NOW();
    """

    UPSERT_OPTIONS = """
    INSERT INTO options_snap (
      ts, tenant_id, vendor, symbol, expiry, option_type, strike,
      iv, delta, gamma, oi, volume, spot, id
    ) VALUES (
      %(ts)s, %(tenant_id)s, %(vendor)s, %(symbol)s, %(expiry)s, %(option_type)s, %(strike)s,
      %(iv)s, %(delta)s, %(gamma)s, %(oi)s, %(volume)s, %(spot)s, %(id)s
    )
    ON CONFLICT ON CONSTRAINT options_snap_pk DO UPDATE SET
      iv     = EXCLUDED.iv,
      delta  = EXCLUDED.delta,
      gamma  = EXCLUDED.gamma,
      oi     = EXCLUDED.oi,
      volume = EXCLUDED.volume,
      spot   = EXCLUDED.spot,
      updated_at = NOW();
    """

    # Read queries
    LATEST_PRICES = """
    SELECT tenant_id, vendor, symbol, close_price AS price, ts AS price_timestamp
    FROM latest_prices
    WHERE vendor = %s AND symbol = ANY(%s)
    ORDER BY symbol, ts DESC
    """

    BARS_WINDOW = """
    SELECT ts, tenant_id, vendor, symbol, timeframe,
           open_price, high_price, low_price, close_price, volume, id
    FROM bars
    WHERE tenant_id = %s AND vendor = %s AND symbol = %s AND timeframe = %s
      AND ts >= %s AND ts <= %s
    ORDER BY ts ASC
    """

    # Job queue operations
    ENQUEUE_JOB = """
    INSERT INTO jobs_outbox (tenant_id, idempotency_key, job_type, payload, priority)
    VALUES (%(tenant_id)s, %(idempotency_key)s, %(job_type)s, %(payload)s, %(priority)s)
    ON CONFLICT (idempotency_key) DO NOTHING
    RETURNING id
    """

    # Parameter mappers
    @staticmethod
    def bar_params(b: Bar) -> dict:
        """Convert Bar model to SQL parameters."""
        return b.dict()

    @staticmethod
    def fund_params(f: Fundamentals) -> dict:
        """Convert Fundamentals model to SQL parameters."""
        return f.dict()

    @staticmethod
    def news_params(n: News) -> dict:
        """Convert News model to SQL parameters."""
        return n.dict()

    @staticmethod
    def opt_params(o: OptionSnap) -> dict:
        """Convert OptionSnap model to SQL parameters."""
        return o.dict()

    @staticmethod
    def job_params(
        tenant_id: str, idempotency_key: str, job_type: str, payload: dict, priority: str = "medium"
    ) -> dict:
        """Convert job parameters to SQL parameters."""
        return {
            "tenant_id": tenant_id,
            "idempotency_key": idempotency_key,
            "job_type": job_type,
            "payload": payload,
            "priority": priority,
        }
