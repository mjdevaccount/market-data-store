"""
Simple file-based Dead Letter Queue (DLQ) for failed batches.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Sequence, TypeVar, Any, Optional

from loguru import logger

T = TypeVar("T")


@dataclass
class DLQRecord(Generic[T]):
    """A single DLQ record representing a failed batch."""

    ts: float
    error: str
    metadata: dict[str, Any]
    items: list[T]


class DeadLetterQueue(Generic[T]):
    """Simple file-based NDJSON DLQ.

    Writes each failed batch as one JSON line:
    {"ts": ..., "error": "...", "metadata": {...}, "items": [...]}
    """

    def __init__(self, path: str | os.PathLike, mkdirs: bool = True) -> None:
        self._path = Path(path)
        if mkdirs:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    async def save(
        self,
        items: Sequence[T],
        error: Exception,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Save a failed batch to the DLQ."""
        rec = DLQRecord[T](
            ts=time.time(),
            error=str(error),
            metadata=metadata or {},
            items=list(items),
        )
        line = json.dumps(
            {
                "ts": rec.ts,
                "error": rec.error,
                "metadata": rec.metadata,
                "items": rec.items,
            },
            default=str,
        )

        # Use a thread to avoid blocking loop
        await asyncio.to_thread(self._append_line, f"{line}\n")

    def _append_line(self, line: str) -> None:
        """Append a line to the DLQ file (blocking I/O)."""
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line)

    async def replay(self, max_records: int = 100) -> list[DLQRecord[T]]:
        """Read up to max_records from the DLQ for replay/diagnostics."""
        lines = await asyncio.to_thread(self._read_lines, max_records)
        out: list[DLQRecord[T]] = []
        for ln in lines:
            try:
                obj = json.loads(ln)
                out.append(
                    DLQRecord(
                        ts=obj.get("ts", 0.0),
                        error=obj.get("error", ""),
                        metadata=obj.get("metadata", {}) or {},
                        items=obj.get("items", []),
                    )
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"DLQ replay decode error: {e}")
        return out

    def _read_lines(self, max_records: int) -> list[str]:
        """Read lines from DLQ file (blocking I/O)."""
        if not self._path.exists():
            return []
        out: list[str] = []
        with self._path.open("r", encoding="utf-8") as f:
            for i, ln in enumerate(f):
                if i >= max_records:
                    break
                out.append(ln.rstrip("\n"))
        return out
