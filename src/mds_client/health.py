"""
Health monitoring and metrics for mds_client.

Provides database health checks, connection pool metrics, and Prometheus integration.
"""

import asyncio
import time
from typing import Dict, Optional

from loguru import logger

# Optional Prometheus metrics
try:
    from prometheus_client import Counter, Gauge, Histogram, generate_latest

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


class HealthMetrics:
    """Health metrics and monitoring for mds_client."""

    def __init__(self):
        self._start_time = time.time()
        self._connection_attempts = 0
        self._connection_failures = 0
        self._query_count = 0
        self._query_duration_total = 0.0

        # Prometheus metrics (if available)
        if PROMETHEUS_AVAILABLE:
            self._connection_attempts_counter = Counter(
                "mds_client_connection_attempts_total", "Total number of connection attempts"
            )
            self._connection_failures_counter = Counter(
                "mds_client_connection_failures_total", "Total number of connection failures"
            )
            self._query_duration_histogram = Histogram(
                "mds_client_query_duration_seconds",
                "Query execution time",
                buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
            )
            self._pool_size_gauge = Gauge("mds_client_pool_size", "Current connection pool size")
            self._pool_in_use_gauge = Gauge(
                "mds_client_pool_in_use", "Number of connections currently in use"
            )
            self._pool_waiting_gauge = Gauge(
                "mds_client_pool_waiting", "Number of requests waiting for a connection"
            )

    def record_connection_attempt(self):
        """Record a connection attempt."""
        self._connection_attempts += 1
        if PROMETHEUS_AVAILABLE:
            self._connection_attempts_counter.inc()

    def record_connection_failure(self):
        """Record a connection failure."""
        self._connection_failures += 1
        if PROMETHEUS_AVAILABLE:
            self._connection_failures_counter.inc()

    def record_query(self, duration: float):
        """Record a query execution."""
        self._query_count += 1
        self._query_duration_total += duration
        if PROMETHEUS_AVAILABLE:
            self._query_duration_histogram.observe(duration)

    def update_pool_metrics(self, pool_size: int, in_use: int, waiting: int):
        """Update connection pool metrics."""
        if PROMETHEUS_AVAILABLE:
            self._pool_size_gauge.set(pool_size)
            self._pool_in_use_gauge.set(in_use)
            self._pool_waiting_gauge.set(waiting)

    def get_metrics_summary(self) -> Dict:
        """Get a summary of current metrics."""
        uptime = time.time() - self._start_time
        avg_query_duration = (
            self._query_duration_total / self._query_count if self._query_count > 0 else 0.0
        )
        connection_success_rate = (
            (self._connection_attempts - self._connection_failures) / self._connection_attempts
            if self._connection_attempts > 0
            else 1.0
        )

        return {
            "uptime_seconds": uptime,
            "connection_attempts": self._connection_attempts,
            "connection_failures": self._connection_failures,
            "connection_success_rate": connection_success_rate,
            "query_count": self._query_count,
            "avg_query_duration_seconds": avg_query_duration,
        }

    def get_prometheus_metrics(self) -> Optional[str]:
        """Get Prometheus metrics in text format."""
        if PROMETHEUS_AVAILABLE:
            return generate_latest().decode("utf-8")
        return None


class HealthChecker:
    """Database health checker with timeout and retry logic."""

    def __init__(self, timeout: float = 5.0, retries: int = 3):
        self.timeout = timeout
        self.retries = retries
        self.metrics = HealthMetrics()

    async def check_database_health(self, amds) -> Dict:
        """
        Perform comprehensive database health check.

        Returns:
            Dict with health status and metrics
        """
        start_time = time.time()

        try:
            # Basic connectivity test
            health_status = await asyncio.wait_for(amds.health(), timeout=self.timeout)

            # Schema version check
            schema_version = await asyncio.wait_for(amds.schema_version(), timeout=self.timeout)

            # Pool metrics (if available)
            pool_metrics = {}
            if hasattr(amds.pool, "get_stats"):
                try:
                    stats = amds.pool.get_stats()
                    pool_metrics = {
                        "pool_size": stats.get("pool_size", 0),
                        "pool_in_use": stats.get("pool_in_use", 0),
                        "pool_waiting": stats.get("pool_waiting", 0),
                    }
                    self.metrics.update_pool_metrics(
                        pool_metrics["pool_size"],
                        pool_metrics["pool_in_use"],
                        pool_metrics["pool_waiting"],
                    )
                except Exception as e:
                    logger.warning(f"Could not get pool stats: {e}")

            duration = time.time() - start_time
            self.metrics.record_query(duration)

            return {
                "status": "healthy" if health_status else "unhealthy",
                "database_connected": health_status,
                "schema_version": schema_version,
                "response_time_seconds": duration,
                "pool_metrics": pool_metrics,
                "metrics": self.metrics.get_metrics_summary(),
            }

        except asyncio.TimeoutError:
            self.metrics.record_connection_failure()
            return {
                "status": "unhealthy",
                "error": "Database health check timed out",
                "timeout_seconds": self.timeout,
            }
        except Exception as e:
            self.metrics.record_connection_failure()
            logger.error(f"Database health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
            }

    async def check_with_retry(self, amds) -> Dict:
        """Check database health with retry logic."""
        last_error = None

        for attempt in range(self.retries):
            try:
                result = await self.check_database_health(amds)
                if result["status"] == "healthy":
                    return result
                last_error = result.get("error", "Unknown error")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Health check attempt {attempt + 1} failed: {e}")

            if attempt < self.retries - 1:
                await asyncio.sleep(1.0)  # Wait before retry

        return {
            "status": "unhealthy",
            "error": f"All {self.retries} attempts failed. Last error: {last_error}",
            "attempts": self.retries,
        }


# Global health checker instance
_health_checker = HealthChecker()


async def check_health(amds) -> Dict:
    """
    Convenience function to check database health.

    Args:
        amds: AMDS client instance

    Returns:
        Dict with health status and metrics
    """
    return await _health_checker.check_database_health(amds)


async def check_health_with_retry(amds) -> Dict:
    """
    Convenience function to check database health with retry logic.

    Args:
        amds: AMDS client instance

    Returns:
        Dict with health status and metrics
    """
    return await _health_checker.check_with_retry(amds)


def get_prometheus_metrics() -> Optional[str]:
    """Get Prometheus metrics in text format."""
    return _health_checker.metrics.get_prometheus_metrics()


def get_metrics_summary() -> Dict:
    """Get metrics summary."""
    return _health_checker.metrics.get_metrics_summary()
