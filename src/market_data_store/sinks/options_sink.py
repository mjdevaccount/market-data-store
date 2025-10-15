from typing import Sequence
from mds_client import AMDS
from mds_client.models import OptionSnap
from .base import BaseSink


class OptionsSink(BaseSink):
    """Async sink for options snapshots."""

    def __init__(self, amds: AMDS) -> None:
        super().__init__("options")
        self.amds = amds

    async def write(self, batch: Sequence[OptionSnap]) -> None:
        async def _do(b: Sequence[OptionSnap]) -> None:
            await self.amds.upsert_options(list(b))

        await self._safe_write(_do, batch)
