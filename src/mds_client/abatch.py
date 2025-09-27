from __future__ import annotations

import asyncio
import json
from time import monotonic
from typing import List, Optional

from .aclient import AMDS
from .batch import BatchConfig  # reuse the same config dataclass
from .models import Bar, Fundamentals, News, OptionSnap


class AsyncBatchProcessor:
    """
    Tiny async batcher for high-throughput writes via AMDS.

    Usage:

        amds = AMDS({"dsn": "...", "tenant_id": "...", "pool_max": 10})
        async with AsyncBatchProcessor(amds, BatchConfig(max_rows=2000, max_ms=3000)) as bp:
            for bar in bars:
                await bp.add_bar(bar)   # thresholds auto-flush
        # auto-flush on context exit
    """

    def __init__(self, amds: AMDS, config: Optional[BatchConfig] = None):
        self._amds = amds
        self._cfg = config or BatchConfig()
        self._t0 = monotonic()

        # Buffers
        self._bars: List[Bar] = []
        self._funds: List[Fundamentals] = []
        self._news: List[News] = []
        self._opts: List[OptionSnap] = []

        self._rows = 0
        self._bytes = 0

        self._lock = asyncio.Lock()

    # --------------- context management

    async def __aenter__(self) -> "AsyncBatchProcessor":
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.flush()

    # --------------- public API (async add/flush)

    async def add_bar(self, row: Bar) -> None:
        self._bars.append(row)
        self._account(row)
        await self._maybe_flush()

    async def add_fundamental(self, row: Fundamentals) -> None:
        self._funds.append(row)
        self._account(row)
        await self._maybe_flush()

    async def add_news(self, row: News) -> None:
        self._news.append(row)
        self._account(row)
        await self._maybe_flush()

    async def add_option(self, row: OptionSnap) -> None:
        self._opts.append(row)
        self._account(row)
        await self._maybe_flush()

    async def flush(self) -> int:
        """Flush all buffers. Returns total rows written (attempted)."""
        async with self._lock:
            total = 0

            if self._bars:
                total += await self._amds.upsert_bars(self._bars)
                self._bars.clear()

            if self._funds:
                total += await self._amds.upsert_fundamentals(self._funds)
                self._funds.clear()

            if self._news:
                total += await self._amds.upsert_news(self._news)
                self._news.clear()

            if self._opts:
                total += await self._amds.upsert_options(self._opts)
                self._opts.clear()

            if total:
                self._rows = 0
                self._bytes = 0
                self._t0 = monotonic()

            return total

    async def close(self) -> int:
        return await self.flush()

    # --------------- internals

    def _account(self, model) -> None:
        """Rough byte estimate for max_bytes threshold."""
        self._rows += 1
        try:
            # pydantic v2: model_dump() then json.dumps keeps it version-agnostic
            self._bytes += len(json.dumps(model.model_dump()))
        except Exception:
            self._bytes += 256  # fallback fixed cost

    async def _maybe_flush(self) -> None:
        if self._rows >= self._cfg.max_rows or self._bytes >= self._cfg.max_bytes:
            await self.flush()
            return
        elapsed_ms = (monotonic() - self._t0) * 1000.0
        if elapsed_ms >= self._cfg.max_ms:
            await self.flush()
