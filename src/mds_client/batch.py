from __future__ import annotations

import json
from dataclasses import dataclass
from time import monotonic
from typing import List, Optional

from .client import MDS
from .models import Bar, Fundamentals, News, OptionSnap


@dataclass(frozen=True)
class BatchConfig:
    """Simple size/time/bytes flush thresholds."""

    max_rows: int = 1000  # flush after N rows across all buffers
    max_ms: int = 5000  # or flush after this many ms
    max_bytes: int = 1_048_576  # or flush after ~1MB of payload (roughly)


class BatchProcessor:
    """
    Tiny, dead-simple sync batcher for high-throughput writes via MDS.

    Usage:
        mds = MDS({"dsn": "...", "tenant_id": "..."})
        bp = BatchProcessor(mds, BatchConfig(max_rows=2000, max_ms=3000, max_bytes=2_000_000))
        for bar in bars:
            bp.add_bar(bar)
        bp.close()  # final flush
    """

    def __init__(self, mds: MDS, config: Optional[BatchConfig] = None):
        self._mds = mds
        self._cfg = config or BatchConfig()
        self._t0 = monotonic()

        # Buffers
        self._bars: List[Bar] = []
        self._funds: List[Fundamentals] = []
        self._news: List[News] = []
        self._opts: List[OptionSnap] = []

        self._rows = 0
        self._bytes = 0

    # --------------------------- public API

    def add_bar(self, row: Bar) -> None:
        self._bars.append(row)
        self._account(row)
        self._maybe_flush()

    def add_fundamental(self, row: Fundamentals) -> None:
        self._funds.append(row)
        self._account(row)
        self._maybe_flush()

    def add_news(self, row: News) -> None:
        self._news.append(row)
        self._account(row)
        self._maybe_flush()

    def add_option(self, row: OptionSnap) -> None:
        self._opts.append(row)
        self._account(row)
        self._maybe_flush()

    def flush(self) -> int:
        """Flush all buffers. Returns total rows written (attempted)."""
        total = 0
        if self._bars:
            total += self._mds.upsert_bars(self._bars)
            self._bars.clear()
        if self._funds:
            total += self._mds.upsert_fundamentals(self._funds)
            self._funds.clear()
        if self._news:
            total += self._mds.upsert_news(self._news)
            self._news.clear()
        if self._opts:
            total += self._mds.upsert_options(self._opts)
            self._opts.clear()

        # reset counters/time window after a flush
        if total:
            self._rows = 0
            self._bytes = 0
            self._t0 = monotonic()
        return total

    def close(self) -> int:
        """Flush remaining rows; safe to call multiple times."""
        return self.flush()

    # --------------------------- internals

    def _account(self, model) -> None:
        """Fast-ish byte estimate using JSON of the pydantic dict."""
        self._rows += 1
        try:
            self._bytes += len(json.dumps(model.model_dump()))
        except Exception:
            # worst case—fallback fixed cost
            self._bytes += 256

    def _maybe_flush(self) -> None:
        if self._rows >= self._cfg.max_rows:
            self.flush()
            return
        if self._bytes >= self._cfg.max_bytes:
            self.flush()
            return
        elapsed_ms = (monotonic() - self._t0) * 1000.0
        if elapsed_ms >= self._cfg.max_ms:
            self.flush()
