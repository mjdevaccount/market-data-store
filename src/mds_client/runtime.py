"""
Runtime configuration and resource management for mds_client.

Handles cross-platform event loop configuration, connection pool lifecycle,
and proper resource cleanup for both Windows development and Linux/Docker production.
"""

import asyncio
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Optional

from loguru import logger

# Optional uvloop for Linux/macOS performance
try:
    import uvloop

    UVLOOP_AVAILABLE = True
except ImportError:
    UVLOOP_AVAILABLE = False


def configure_event_loop() -> None:
    """
    Configure the event loop policy for optimal cross-platform compatibility.

    Windows: Use WindowsSelectorEventLoopPolicy (required for psycopg)
    Linux/macOS: Try uvloop for performance, fallback to standard asyncio
    """
    if sys.platform.startswith("win"):
        # Windows: Force SelectorEventLoop for psycopg compatibility
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        logger.info("WindowsSelectorEventLoopPolicy active for psycopg compatibility")
    else:
        # Linux/macOS: Try uvloop for performance
        if UVLOOP_AVAILABLE:
            uvloop.install()
            logger.info("uvloop event loop policy active for enhanced performance")
        else:
            logger.info("Standard asyncio event loop policy active")


def maybe_use_uvloop() -> None:
    """Install uvloop if available (Linux/macOS only)."""
    if not sys.platform.startswith("win") and UVLOOP_AVAILABLE:
        uvloop.install()
        logger.info("uvloop event loop policy active")


def boot_event_loop() -> None:
    """
    Initialize event loop configuration for the application.
    Call this early in CLI entrypoints and server startup.
    """
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        logger.info("WindowsSelectorEventLoopPolicy active")
    else:
        try:
            import uvloop

            uvloop.install()
            logger.info("uvloop installed")
        except Exception:
            logger.info("uvloop not available; using default asyncio")


class ResourceManager:
    """
    Centralized resource management using AsyncExitStack.

    Ensures proper cleanup order and prevents resource leaks.
    """

    def __init__(self):
        self._stack: Optional[AsyncExitStack] = None

    async def __aenter__(self):
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        assert self._stack is not None
        return await self._stack.__aexit__(exc_type, exc_val, exc_tb)

    async def register_pool(self, pool):
        """Register a connection pool for automatic cleanup."""
        assert self._stack is not None, "ResourceManager not initialized"
        return await self._stack.enter_async_context(pool)


async def shutdown_with_timeout(pool, timeout: float = 2.0) -> None:
    """
    Shutdown connection pool with timeout to prevent hanging threads.

    Args:
        pool: Connection pool to close
        timeout: Maximum time to wait for cleanup
    """
    try:
        await pool.close(timeout=timeout)
    except Exception:
        # last-resort fallback; usually not needed
        try:
            pool.close(timeout=0)  # fire-and-forget if available
        except Exception:
            pass


@asynccontextmanager
async def create_pool_context_manager(conninfo: str, **pool_kwargs):
    """
    Create a properly configured connection pool context manager.

    This ensures pools are never auto-opened and always properly cleaned up.
    """
    from psycopg_pool import AsyncConnectionPool

    pool = AsyncConnectionPool(conninfo, open=False, **pool_kwargs)
    await pool.open(wait=True, timeout=5.0)
    try:
        yield pool
    finally:
        await pool.close(timeout=2.0)
