"""
SQL statements and parameter mappers for Market Data Store operations.

All statements use the composite primary keys with time columns first
for TimescaleDB compatibility.
"""

from __future__ import annotations
from typing import Tuple
from .models import Bar, Fundamentals, News, OptionSnap


class SQL:
    """SQL statements with conflict resolution on composite primary keys."""

    # ---------- UPSERTS (Timescale: time column FIRST in conflict target)

    UPSERT_BARS = """
    INSERT INTO bars (ts, tenant_id, vendor, symbol, timeframe,
                      open_price, high_price, low_price, close_price, volume)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (ts, tenant_id, vendor, symbol, timeframe)
    DO UPDATE SET
      open_price  = EXCLUDED.open_price,
      high_price  = EXCLUDED.high_price,
      low_price   = EXCLUDED.low_price,
      close_price = EXCLUDED.close_price,
      volume      = EXCLUDED.volume,
      updated_at  = NOW();
    """

    @staticmethod
    def bar_params(r: Bar) -> Tuple:
        sym = r.symbol.upper()
        return (
            r.ts,
            r.tenant_id,
            r.vendor,
            sym,
            r.timeframe,
            r.open_price,
            r.high_price,
            r.low_price,
            r.close_price,
            r.volume,
        )

    UPSERT_FUNDAMENTALS = """
    INSERT INTO fundamentals (asof, tenant_id, vendor, symbol,
                              total_assets, total_liabilities, net_income, eps)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (asof, tenant_id, vendor, symbol)
    DO UPDATE SET
      total_assets      = EXCLUDED.total_assets,
      total_liabilities = EXCLUDED.total_liabilities,
      net_income        = EXCLUDED.net_income,
      eps               = EXCLUDED.eps,
      updated_at        = NOW();
    """

    @staticmethod
    def fund_params(r: Fundamentals) -> Tuple:
        return (
            r.asof,
            r.tenant_id,
            r.vendor,
            r.symbol.upper(),
            r.total_assets,
            r.total_liabilities,
            r.net_income,
            r.eps,
        )

    # PK is (published_at, tenant_id, vendor, id) – keep id if caller supplies one
    UPSERT_NEWS = """
    INSERT INTO news (published_at, tenant_id, vendor, id, title, url, symbol, sentiment_score)
    VALUES (%s,%s,%s,COALESCE(%s, gen_random_uuid()),%s,%s,%s,%s)
    ON CONFLICT (published_at, tenant_id, vendor, id)
    DO UPDATE SET
      title          = EXCLUDED.title,
      url            = EXCLUDED.url,
      symbol         = EXCLUDED.symbol,
      sentiment_score= EXCLUDED.sentiment_score,
      updated_at     = NOW();
    """

    @staticmethod
    def news_params(r: News) -> Tuple:
        return (
            r.published_at,
            r.tenant_id,
            r.vendor,
            r.id,
            r.title,
            r.url,
            (r.symbol.upper() if r.symbol else None),
            r.sentiment_score,
        )

    UPSERT_OPTIONS = """
    INSERT INTO options_snap (
      ts, tenant_id, vendor, symbol, expiry, option_type, strike,
      iv, delta, gamma, oi, volume, spot
    )
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (ts, tenant_id, vendor, symbol, expiry, option_type, strike)
    DO UPDATE SET
      iv       = EXCLUDED.iv,
      delta    = EXCLUDED.delta,
      gamma    = EXCLUDED.gamma,
      oi       = EXCLUDED.oi,
      volume   = EXCLUDED.volume,
      spot     = EXCLUDED.spot,
      updated_at = NOW();
    """

    @staticmethod
    def opt_params(r: OptionSnap) -> Tuple:
        return (
            r.ts,
            r.tenant_id,
            r.vendor,
            r.symbol.upper(),
            r.expiry,
            r.option_type,
            r.strike,
            r.iv,
            r.delta,
            r.gamma,
            r.oi,
            r.volume,
            r.spot,
        )

    # ---------- READS

    # Use your view for "latest per symbol"
    LATEST_PRICES = """
    SELECT tenant_id, vendor, symbol, price, price_timestamp
    FROM latest_prices
    WHERE vendor = %s AND symbol = ANY(%s)
    ORDER BY symbol;
    """

    # Windowed bars (RLS enforces tenant; we pass tenant explicitly to use an index path)
    BARS_WINDOW = """
    SELECT b.ts, b.tenant_id, b.vendor, b.symbol, b.timeframe,
           b.open_price, b.high_price, b.low_price, b.close_price, b.volume, b.id
    FROM bars b
    WHERE b.tenant_id = %s AND b.vendor = %s AND b.symbol = %s AND b.timeframe = %s
      AND b.ts >= %s AND b.ts < %s
    ORDER BY b.ts ASC;
    """
