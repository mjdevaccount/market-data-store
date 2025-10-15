from typing import Sequence
from mds_client import AMDS
from mds_client.models import Fundamentals
from .base import BaseSink


class FundamentalsSink(BaseSink):
    """Async sink for fundamentals data."""

    def __init__(self, amds: AMDS) -> None:
        super().__init__("fundamentals")
        self.amds = amds

    async def write(self, batch: Sequence[Fundamentals]) -> None:
        async def _do(b: Sequence[Fundamentals]) -> None:
            await self.amds.upsert_fundamentals(list(b))

        await self._safe_write(_do, batch)
