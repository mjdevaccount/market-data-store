"""
BarsSink – wraps AMDS.upsert_bars for async ingestion.
"""

from typing import Sequence
from mds_client import AMDS
from mds_client.models import Bar
from .base import BaseSink


class BarsSink(BaseSink):
    """Async sink for OHLCV bars."""

    def __init__(self, amds: AMDS) -> None:
        super().__init__("bars")
        self.amds = amds

    async def write(self, batch: Sequence[Bar]) -> None:
        async def _do(b: Sequence[Bar]) -> None:
            await self.amds.upsert_bars(list(b))

        await self._safe_write(_do, batch)
