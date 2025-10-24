"""
Signals query functions for streaming inference signals.

Provides read access to signals table with common query patterns:
- Latest signals by provider/symbol
- Signal history with time ranges
- Signal metrics and aggregations
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import psycopg


class SignalsQueryClient:
    """
    Query client for signals table.

    Usage:
        with SignalsQueryClient(uri) as client:
            signals = client.get_latest_signals("ibkr_primary", "SPY")
    """

    def __init__(self, uri: str):
        """
        Initialize SignalsQueryClient.

        Args:
            uri: PostgreSQL connection URI
        """
        self._uri = uri
        self._conn = None

    def __enter__(self):
        """Context manager entry - establish connection."""
        self._conn = psycopg.connect(self._uri)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close connection."""
        if self._conn:
            self._conn.close()
        return False

    def get_latest_signals(
        self,
        provider: str,
        symbol: str,
        limit: int = 100,
        signal_names: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get latest signals for a provider/symbol combination.

        Args:
            provider: Data provider name
            symbol: Symbol name
            limit: Maximum number of signals to return
            signal_names: Optional filter for specific signal names

        Returns:
            List of signal records with metadata
        """
        if not self._conn:
            raise RuntimeError("SignalsQueryClient must be used as context manager")

        with self._conn.cursor() as cur:
            if signal_names:
                placeholders = ",".join(["%s"] * len(signal_names))
                sql = f"""
                    SELECT provider, symbol, ts, name, value, score, metadata, created_at
                    FROM signals
                    WHERE provider = %s AND symbol = %s AND name IN ({placeholders})
                    ORDER BY ts DESC, name
                    LIMIT %s
                """
                params = [provider, symbol.upper()] + signal_names + [limit]
            else:
                sql = """
                    SELECT provider, symbol, ts, name, value, score, metadata, created_at
                    FROM signals
                    WHERE provider = %s AND symbol = %s
                    ORDER BY ts DESC, name
                    LIMIT %s
                """
                params = [provider, symbol.upper(), limit]

            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def get_signals_history(
        self,
        provider: str,
        symbol: str,
        start_ts: datetime,
        end_ts: Optional[datetime] = None,
        signal_names: Optional[List[str]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Get signals history for a time range.

        Args:
            provider: Data provider name
            symbol: Symbol name
            start_ts: Start timestamp (inclusive)
            end_ts: End timestamp (inclusive), defaults to now
            signal_names: Optional filter for specific signal names
            limit: Maximum number of signals to return

        Returns:
            List of signal records with metadata
        """
        if not self._conn:
            raise RuntimeError("SignalsQueryClient must be used as context manager")

        if end_ts is None:
            end_ts = datetime.utcnow()

        with self._conn.cursor() as cur:
            if signal_names:
                placeholders = ",".join(["%s"] * len(signal_names))
                sql = f"""
                    SELECT provider, symbol, ts, name, value, score, metadata, created_at
                    FROM signals
                    WHERE provider = %s AND symbol = %s
                    AND ts >= %s AND ts <= %s
                    AND name IN ({placeholders})
                    ORDER BY ts DESC, name
                    LIMIT %s
                """
                params = [provider, symbol.upper(), start_ts, end_ts] + signal_names + [limit]
            else:
                sql = """
                    SELECT provider, symbol, ts, name, value, score, metadata, created_at
                    FROM signals
                    WHERE provider = %s AND symbol = %s
                    AND ts >= %s AND ts <= %s
                    ORDER BY ts DESC, name
                    LIMIT %s
                """
                params = [provider, symbol.upper(), start_ts, end_ts, limit]

            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def get_signal_metrics(
        self,
        provider: str,
        symbol: str,
        signal_name: str,
        hours_back: int = 24,
    ) -> Dict[str, Any]:
        """
        Get aggregated metrics for a specific signal.

        Args:
            provider: Data provider name
            symbol: Symbol name
            signal_name: Signal name to analyze
            hours_back: Hours of history to analyze

        Returns:
            Dictionary with signal metrics (count, min, max, avg, latest)
        """
        if not self._conn:
            raise RuntimeError("SignalsQueryClient must be used as context manager")

        with self._conn.cursor() as cur:
            sql = """
                SELECT
                    COUNT(*) as signal_count,
                    MIN(value) as min_value,
                    MAX(value) as max_value,
                    AVG(value) as avg_value,
                    MAX(ts) as latest_ts,
                    MIN(ts) as earliest_ts
                FROM signals
                WHERE provider = %s AND symbol = %s AND name = %s
                AND ts >= NOW() - INTERVAL '%s hours'
            """
            cur.execute(sql, [provider, symbol.upper(), signal_name, hours_back])
            row = cur.fetchone()

            if row:
                columns = [desc[0] for desc in cur.description]
                return dict(zip(columns, row))
            else:
                return {
                    "signal_count": 0,
                    "min_value": None,
                    "max_value": None,
                    "avg_value": None,
                    "latest_ts": None,
                    "earliest_ts": None,
                }

    def get_active_signals(
        self,
        provider: str,
        minutes_back: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Get all signals that have been active in the last N minutes.

        Args:
            provider: Data provider name
            minutes_back: Minutes of history to check

        Returns:
            List of unique signal combinations with latest values
        """
        if not self._conn:
            raise RuntimeError("SignalsQueryClient must be used as context manager")

        with self._conn.cursor() as cur:
            sql = """
                SELECT DISTINCT ON (symbol, name)
                    symbol, name, value, score, ts, metadata
                FROM signals
                WHERE provider = %s
                AND ts >= NOW() - INTERVAL '%s minutes'
                ORDER BY symbol, name, ts DESC
            """
            cur.execute(sql, [provider, minutes_back])
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

    def get_signal_summary(
        self,
        provider: str,
        hours_back: int = 24,
    ) -> Dict[str, Any]:
        """
        Get summary statistics for all signals from a provider.

        Args:
            provider: Data provider name
            hours_back: Hours of history to analyze

        Returns:
            Dictionary with signal summary statistics
        """
        if not self._conn:
            raise RuntimeError("SignalsQueryClient must be used as context manager")

        with self._conn.cursor() as cur:
            sql = """
                SELECT
                    COUNT(*) as total_signals,
                    COUNT(DISTINCT symbol) as unique_symbols,
                    COUNT(DISTINCT name) as unique_signal_types,
                    MAX(ts) as latest_signal_ts,
                    MIN(ts) as earliest_signal_ts
                FROM signals
                WHERE provider = %s
                AND ts >= NOW() - INTERVAL '%s hours'
            """
            cur.execute(sql, [provider, hours_back])
            row = cur.fetchone()

            if row:
                columns = [desc[0] for desc in cur.description]
                return dict(zip(columns, row))
            else:
                return {
                    "total_signals": 0,
                    "unique_symbols": 0,
                    "unique_signal_types": 0,
                    "latest_signal_ts": None,
                    "earliest_signal_ts": None,
                }


class AsyncSignalsQueryClient:
    """
    Async query client for signals table.

    Usage:
        async with AsyncSignalsQueryClient(uri) as client:
            signals = await client.get_latest_signals("ibkr_primary", "SPY")
    """

    def __init__(self, uri: str):
        """
        Initialize AsyncSignalsQueryClient.

        Args:
            uri: PostgreSQL connection URI
        """
        self._uri = uri
        self._conn = None

    async def __aenter__(self):
        """Async context manager entry - establish connection."""
        self._conn = await psycopg.AsyncConnection.connect(self._uri)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close connection."""
        if self._conn:
            await self._conn.close()
        return False

    async def get_latest_signals(
        self,
        provider: str,
        symbol: str,
        limit: int = 100,
        signal_names: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Async get latest signals for a provider/symbol combination."""
        if not self._conn:
            raise RuntimeError("AsyncSignalsQueryClient must be used as context manager")

        async with self._conn.cursor() as cur:
            if signal_names:
                placeholders = ",".join(["%s"] * len(signal_names))
                sql = f"""
                    SELECT provider, symbol, ts, name, value, score, metadata, created_at
                    FROM signals
                    WHERE provider = %s AND symbol = %s AND name IN ({placeholders})
                    ORDER BY ts DESC, name
                    LIMIT %s
                """
                params = [provider, symbol.upper()] + signal_names + [limit]
            else:
                sql = """
                    SELECT provider, symbol, ts, name, value, score, metadata, created_at
                    FROM signals
                    WHERE provider = %s AND symbol = %s
                    ORDER BY ts DESC, name
                    LIMIT %s
                """
                params = [provider, symbol.upper(), limit]

            await cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in await cur.fetchall()]

    async def get_signals_history(
        self,
        provider: str,
        symbol: str,
        start_ts: datetime,
        end_ts: Optional[datetime] = None,
        signal_names: Optional[List[str]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Async get signals history for a time range."""
        if not self._conn:
            raise RuntimeError("AsyncSignalsQueryClient must be used as context manager")

        if end_ts is None:
            end_ts = datetime.utcnow()

        async with self._conn.cursor() as cur:
            if signal_names:
                placeholders = ",".join(["%s"] * len(signal_names))
                sql = f"""
                    SELECT provider, symbol, ts, name, value, score, metadata, created_at
                    FROM signals
                    WHERE provider = %s AND symbol = %s
                    AND ts >= %s AND ts <= %s
                    AND name IN ({placeholders})
                    ORDER BY ts DESC, name
                    LIMIT %s
                """
                params = [provider, symbol.upper(), start_ts, end_ts] + signal_names + [limit]
            else:
                sql = """
                    SELECT provider, symbol, ts, name, value, score, metadata, created_at
                    FROM signals
                    WHERE provider = %s AND symbol = %s
                    AND ts >= %s AND ts <= %s
                    ORDER BY ts DESC, name
                    LIMIT %s
                """
                params = [provider, symbol.upper(), start_ts, end_ts, limit]

            await cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in await cur.fetchall()]

    async def get_signal_metrics(
        self,
        provider: str,
        symbol: str,
        signal_name: str,
        hours_back: int = 24,
    ) -> Dict[str, Any]:
        """Async get aggregated metrics for a specific signal."""
        if not self._conn:
            raise RuntimeError("AsyncSignalsQueryClient must be used as context manager")

        async with self._conn.cursor() as cur:
            sql = """
                SELECT
                    COUNT(*) as signal_count,
                    MIN(value) as min_value,
                    MAX(value) as max_value,
                    AVG(value) as avg_value,
                    MAX(ts) as latest_ts,
                    MIN(ts) as earliest_ts
                FROM signals
                WHERE provider = %s AND symbol = %s AND name = %s
                AND ts >= NOW() - INTERVAL '%s hours'
            """
            await cur.execute(sql, [provider, symbol.upper(), signal_name, hours_back])
            row = await cur.fetchone()

            if row:
                columns = [desc[0] for desc in cur.description]
                return dict(zip(columns, row))
            else:
                return {
                    "signal_count": 0,
                    "min_value": None,
                    "max_value": None,
                    "avg_value": None,
                    "latest_ts": None,
                    "earliest_ts": None,
                }

    async def get_active_signals(
        self,
        provider: str,
        minutes_back: int = 5,
    ) -> List[Dict[str, Any]]:
        """Async get all signals that have been active in the last N minutes."""
        if not self._conn:
            raise RuntimeError("AsyncSignalsQueryClient must be used as context manager")

        async with self._conn.cursor() as cur:
            sql = """
                SELECT DISTINCT ON (symbol, name)
                    symbol, name, value, score, ts, metadata
                FROM signals
                WHERE provider = %s
                AND ts >= NOW() - INTERVAL '%s minutes'
                ORDER BY symbol, name, ts DESC
            """
            await cur.execute(sql, [provider, minutes_back])
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in await cur.fetchall()]

    async def get_signal_summary(
        self,
        provider: str,
        hours_back: int = 24,
    ) -> Dict[str, Any]:
        """Async get summary statistics for all signals from a provider."""
        if not self._conn:
            raise RuntimeError("AsyncSignalsQueryClient must be used as context manager")

        async with self._conn.cursor() as cur:
            sql = """
                SELECT
                    COUNT(*) as total_signals,
                    COUNT(DISTINCT symbol) as unique_symbols,
                    COUNT(DISTINCT name) as unique_signal_types,
                    MAX(ts) as latest_signal_ts,
                    MIN(ts) as earliest_signal_ts
                FROM signals
                WHERE provider = %s
                AND ts >= NOW() - INTERVAL '%s hours'
            """
            await cur.execute(sql, [provider, hours_back])
            row = await cur.fetchone()

            if row:
                columns = [desc[0] for desc in cur.description]
                return dict(zip(columns, row))
            else:
                return {
                    "total_signals": 0,
                    "unique_symbols": 0,
                    "unique_signal_types": 0,
                    "latest_signal_ts": None,
                    "earliest_signal_ts": None,
                }
