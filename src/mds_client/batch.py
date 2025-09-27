from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING

from .models import Bar, Fundamentals, News, OptionSnap

if TYPE_CHECKING:
    from .client import MDS
    from .aclient import AMDS


# ----------------------------
# Config
# ----------------------------


@dataclass(frozen=True)
class BatchConfig:
    """Batch thresholds. Tune for your pipeline.
    - max_rows:   flush when >= N rows pending (across all kinds)
    - max_ms:     flush when this many ms elapsed since last flush
    - max_bytes:  flush when pending JSON payload bytes exceed this
    """

    max_rows: int = 1000
    max_ms: int = 5000
    max_bytes: int = 1_048_576  # 1 MiB


# ----------------------------
# Helpers
# ----------------------------


def _json_size_bytes(model_obj) -> int:
    """Byte-accurate size using compact UTF-8 JSON."""
    # Pydantic v2 BaseModel has model_dump_json; fallback to dumps(model_dump())
    try:
        s = model_obj.model_dump_json(by_alias=True, exclude_none=True)
    except AttributeError:
        s = json.dumps(
            getattr(model_obj, "model_dump")(), separators=(",", ":"), ensure_ascii=False
        )
    return len(s.encode("utf-8"))


# ----------------------------
# Sync Batch Processor
# ----------------------------


class BatchProcessor:
    """Synchronous batcher around MDS upserts.
    Not thread-safe. Use from a single thread/coroutine.
    """

    def __init__(self, mds: "MDS", cfg: BatchConfig = BatchConfig()):
        self._mds = mds
        self._cfg = cfg

        # Pending buffers per kind
        self._bars: List[Bar] = []
        self._funds: List[Fundamentals] = []
        self._news: List[News] = []
        self._opts: List[OptionSnap] = []

        self._pending_rows: int = 0
        self._pending_bytes: int = 0
        self._last_flush: float = time.monotonic()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.flush()
        if hasattr(self._mds, "close"):
            self._mds.close()

    # ---- public adds ----

    def add_bar(self, row: Bar) -> None:
        self._enqueue("bars", row)

    def add_fundamental(self, row: Fundamentals) -> None:
        self._enqueue("fundamentals", row)

    def add_news(self, row: News) -> None:
        self._enqueue("news", row)

    def add_option(self, row: OptionSnap) -> None:
        self._enqueue("options", row)

    # ---- control ----

    def flush(self) -> Dict[str, int]:
        """Flush all buffers if non-empty. Returns counts per kind."""
        counts = {"bars": 0, "fundamentals": 0, "news": 0, "options": 0}

        # Flush each kind independently; keep buffers intact on failure for that kind
        if self._bars:
            self._mds.upsert_bars(self._bars)
            counts["bars"] = len(self._bars)
            self._pending_rows -= len(self._bars)
            self._pending_bytes -= sum(_json_size_bytes(x) for x in self._bars)
            self._bars.clear()

        if self._funds:
            self._mds.upsert_fundamentals(self._funds)
            counts["fundamentals"] = len(self._funds)
            self._pending_rows -= len(self._funds)
            self._pending_bytes -= sum(_json_size_bytes(x) for x in self._funds)
            self._funds.clear()

        if self._news:
            self._mds.upsert_news(self._news)
            counts["news"] = len(self._news)
            self._pending_rows -= len(self._news)
            self._pending_bytes -= sum(_json_size_bytes(x) for x in self._news)
            self._news.clear()

        if self._opts:
            self._mds.upsert_options(self._opts)
            counts["options"] = len(self._opts)
            self._pending_rows -= len(self._opts)
            self._pending_bytes -= sum(_json_size_bytes(x) for x in self._opts)
            self._opts.clear()

        if sum(counts.values()) > 0:
            self._last_flush = time.monotonic()

        # Safety: never go negative
        self._pending_rows = max(self._pending_rows, 0)
        self._pending_bytes = max(self._pending_bytes, 0)

        return counts

    def stats(self) -> Dict[str, int]:
        return {
            "pending_rows": self._pending_rows,
            "pending_bytes": self._pending_bytes,
            "bars": len(self._bars),
            "fundamentals": len(self._funds),
            "news": len(self._news),
            "options": len(self._opts),
        }

    # ---- internals ----

    def _enqueue(self, kind: str, row) -> None:
        sz = _json_size_bytes(row)
        if kind == "bars":
            self._bars.append(row)
        elif kind == "fundamentals":
            self._funds.append(row)
        elif kind == "news":
            self._news.append(row)
        else:
            self._opts.append(row)

        self._pending_rows += 1
        self._pending_bytes += sz
        self._maybe_flush()

    def _maybe_flush(self) -> None:
        elapsed_ms = (time.monotonic() - self._last_flush) * 1000.0
        if (
            self._pending_rows >= self._cfg.max_rows
            or self._pending_bytes >= self._cfg.max_bytes
            or elapsed_ms >= self._cfg.max_ms
        ):
            self.flush()


# ----------------------------
# Async Batch Processor
# ----------------------------


class AsyncBatchProcessor:
    """Async batcher around AMDS upserts.
    Safe for single task producer; use external coordination if multiple producers.
    """

    def __init__(self, amds: "AMDS", cfg: BatchConfig = BatchConfig()):
        self._amds = amds
        self._cfg = cfg

        self._bars: List[Bar] = []
        self._funds: List[Fundamentals] = []
        self._news: List[News] = []
        self._opts: List[OptionSnap] = []

        self._pending_rows: int = 0
        self._pending_bytes: int = 0
        self._last_flush: float = time.monotonic()

        self._lock = asyncio.Lock()
        self._ticker_task: Optional[asyncio.Task] = None
        # Ticker interval: half of max_ms, clamped into [0.1s, 2s]
        self._interval = max(0.1, min(2.0, self._cfg.max_ms / 2000.0))

    # ---- async context ----

    async def __aenter__(self) -> "AsyncBatchProcessor":
        self._ticker_task = asyncio.create_task(self._ticker())
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._ticker_task:
            self._ticker_task.cancel()
            try:
                await self._ticker_task
            except asyncio.CancelledError:
                pass
        await self.flush()
        if hasattr(self._amds, "aclose"):
            await self._amds.aclose()

    # ---- public adds ----

    async def add_bar(self, row: Bar) -> None:
        await self._enqueue("bars", row)

    async def add_fundamental(self, row: Fundamentals) -> None:
        await self._enqueue("fundamentals", row)

    async def add_news(self, row: News) -> None:
        await self._enqueue("news", row)

    async def add_option(self, row: OptionSnap) -> None:
        await self._enqueue("options", row)

    # ---- control ----

    async def flush(self) -> Dict[str, int]:
        """Flush all buffers if non-empty. Returns counts per kind."""
        async with self._lock:
            counts = {"bars": 0, "fundamentals": 0, "news": 0, "options": 0}

            if self._bars:
                await self._amds.upsert_bars(self._bars)
                counts["bars"] = len(self._bars)
                self._pending_rows -= len(self._bars)
                self._pending_bytes -= sum(_json_size_bytes(x) for x in self._bars)
                self._bars.clear()

            if self._funds:
                await self._amds.upsert_fundamentals(self._funds)
                counts["fundamentals"] = len(self._funds)
                self._pending_rows -= len(self._funds)
                self._pending_bytes -= sum(_json_size_bytes(x) for x in self._funds)
                self._funds.clear()

            if self._news:
                await self._amds.upsert_news(self._news)
                counts["news"] = len(self._news)
                self._pending_rows -= len(self._news)
                self._pending_bytes -= sum(_json_size_bytes(x) for x in self._news)
                self._news.clear()

            if self._opts:
                await self._amds.upsert_options(self._opts)
                counts["options"] = len(self._opts)
                self._pending_rows -= len(self._opts)
                self._pending_bytes -= sum(_json_size_bytes(x) for x in self._opts)
                self._opts.clear()

            if sum(counts.values()) > 0:
                self._last_flush = time.monotonic()

            self._pending_rows = max(self._pending_rows, 0)
            self._pending_bytes = max(self._pending_bytes, 0)

            return counts

    def stats(self) -> Dict[str, int]:
        return {
            "pending_rows": self._pending_rows,
            "pending_bytes": self._pending_bytes,
            "bars": len(self._bars),
            "fundamentals": len(self._funds),
            "news": len(self._news),
            "options": len(self._opts),
        }

    # ---- internals ----

    async def _enqueue(self, kind: str, row) -> None:
        sz = _json_size_bytes(row)
        async with self._lock:
            if kind == "bars":
                self._bars.append(row)
            elif kind == "fundamentals":
                self._funds.append(row)
            elif kind == "news":
                self._news.append(row)
            else:
                self._opts.append(row)

            self._pending_rows += 1
            self._pending_bytes += sz

            elapsed_ms = (time.monotonic() - self._last_flush) * 1000.0
            if (
                self._pending_rows >= self._cfg.max_rows
                or self._pending_bytes >= self._cfg.max_bytes
                or elapsed_ms >= self._cfg.max_ms
            ):
                # Flush while holding the lock to keep ordering simple.
                await self._flush_locked()

    async def _flush_locked(self) -> None:
        """Assumes self._lock is held; flushes non-empty buffers."""
        if self._bars:
            await self._amds.upsert_bars(self._bars)
            self._pending_rows -= len(self._bars)
            self._pending_bytes -= sum(_json_size_bytes(x) for x in self._bars)
            self._bars.clear()

        if self._funds:
            await self._amds.upsert_fundamentals(self._funds)
            self._pending_rows -= len(self._funds)
            self._pending_bytes -= sum(_json_size_bytes(x) for x in self._funds)
            self._funds.clear()

        if self._news:
            await self._amds.upsert_news(self._news)
            self._pending_rows -= len(self._news)
            self._pending_bytes -= sum(_json_size_bytes(x) for x in self._news)
            self._news.clear()

        if self._opts:
            await self._amds.upsert_options(self._opts)
            self._pending_rows -= len(self._opts)
            self._pending_bytes -= sum(_json_size_bytes(x) for x in self._opts)
            self._opts.clear()

        self._last_flush = time.monotonic()
        self._pending_rows = max(self._pending_rows, 0)
        self._pending_bytes = max(self._pending_bytes, 0)

    async def _ticker(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._interval)
                # Time-based flush: only if something is pending and we've exceeded max_ms
                now = time.monotonic()
                if (now - self._last_flush) * 1000.0 >= self._cfg.max_ms:
                    async with self._lock:
                        if self._pending_rows > 0:
                            await self._flush_locked()
        except asyncio.CancelledError:
            # Normal shutdown
            return
