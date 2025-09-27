"""
Pytest configuration and fixtures for market-data-store.

Provides cross-platform event loop configuration and test utilities.
"""

import asyncio
import sys

import pytest

# Set policy *before* pytest-asyncio creates any loops
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
def mock_dsn():
    """Mock database DSN for testing."""
    return "postgresql://test:test@localhost:5432/testdb"


@pytest.fixture
def mock_tenant_id():
    """Mock tenant ID for testing."""
    return "6b6a6a8a-3e2e-4a8e-9c3d-9ef0ffa4d111"


@pytest.fixture
def mock_config(mock_dsn, mock_tenant_id):
    """Mock configuration for testing."""
    return {
        "dsn": mock_dsn,
        "tenant_id": mock_tenant_id,
        "app_name": "test_app",
        "pool_max": 5,
    }


# Windows-specific fixtures
@pytest.fixture
def windows_event_loop_policy():
    """Ensure Windows uses the correct event loop policy."""
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.get_event_loop_policy()


# Linux/macOS-specific fixtures
@pytest.fixture
def uvloop_policy():
    """Try to use uvloop if available on Linux/macOS."""
    if not sys.platform.startswith("win"):
        try:
            import uvloop

            uvloop.install()
            return uvloop.EventLoopPolicy()
        except ImportError:
            pass
    return asyncio.get_event_loop_policy()
