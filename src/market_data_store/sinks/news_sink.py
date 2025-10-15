from typing import Sequence
from mds_client import AMDS
from mds_client.models import News
from .base import BaseSink


class NewsSink(BaseSink):
    """Async sink for news headlines."""

    def __init__(self, amds: AMDS) -> None:
        super().__init__("news")
        self.amds = amds

    async def write(self, batch: Sequence[News]) -> None:
        async def _do(b: Sequence[News]) -> None:
            await self.amds.upsert_news(list(b))

        await self._safe_write(_do, batch)
