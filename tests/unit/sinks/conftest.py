"""
Fixtures for sink unit tests.
"""

import pytest
from types import SimpleNamespace


@pytest.fixture()
def mock_amds_success():
    """AMDS mock that records calls and succeeds."""
    calls = {}

    async def _upsert_bars(b):
        calls["bars"] = len(b)

    async def _upsert_options(b):
        calls["options"] = len(b)

    async def _upsert_fundamentals(b):
        calls["fundamentals"] = len(b)

    async def _upsert_news(b):
        calls["news"] = len(b)

    amds = SimpleNamespace(
        upsert_bars=_upsert_bars,
        upsert_options=_upsert_options,
        upsert_fundamentals=_upsert_fundamentals,
        upsert_news=_upsert_news,
    )
    amds._calls = calls
    return amds


@pytest.fixture()
def mock_amds_failure():
    """AMDS mock that always raises (for failure path tests)."""

    async def _fail(_):
        raise RuntimeError("DB unavailable")

    return SimpleNamespace(
        upsert_bars=_fail,
        upsert_options=_fail,
        upsert_fundamentals=_fail,
        upsert_news=_fail,
    )
