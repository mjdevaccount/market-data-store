"""
Batch processing utilities for high-throughput data ingestion.

Provides efficient bulk operations with size/time-based flushing and
COPY-based staging for maximum performance.
"""

from typing import Union
from dataclasses import dataclass

from .client import MDS, AMDS
from .models import Bar, Fundamentals, News, OptionSnap
from .utils import BatchConfig, BatchWriter
from .errors import MDSError


@dataclass
class BatchStats:
    """Statistics for batch processing."""

    total_rows: int = 0
    total_batches: int = 0
    total_errors: int = 0
    avg_batch_size: float = 0.0
    processing_time_ms: float = 0.0


class BatchProcessor:
    """
    Batch processor for high-throughput data ingestion.

    Handles automatic flushing based on size, time, or manual triggers.
    """

    def __init__(self, client: Union[MDS, AMDS], config: BatchConfig):
        self.client = client
        self.config = config
        self.writer = BatchWriter(config)
        self.stats = BatchStats()

    def add_bar(self, bar: Bar) -> None:
        """Add bar to batch."""
        self.writer.add("bars", bar.dict())
        if self.writer.should_flush("bars"):
            self._flush_bars()

    def add_fundamental(self, fundamental: Fundamentals) -> None:
        """Add fundamental to batch."""
        self.writer.add("fundamentals", fundamental.dict())
        if self.writer.should_flush("fundamentals"):
            self._flush_fundamentals()

    def add_news(self, news: News) -> None:
        """Add news to batch."""
        self.writer.add("news", news.dict())
        if self.writer.should_flush("news"):
            self._flush_news()

    def add_option(self, option: OptionSnap) -> None:
        """Add option to batch."""
        self.writer.add("options", option.dict())
        if self.writer.should_flush("options"):
            self._flush_options()

    def _flush_bars(self) -> None:
        """Flush bars batch."""
        batch = self.writer.get_batch("bars")
        if not batch:
            return

        try:
            bars = [Bar(**record) for record in batch]
            count = self.client.upsert_bars(bars)
            self.stats.total_rows += count
            self.stats.total_batches += 1
        except Exception as e:
            self.stats.total_errors += 1
            raise MDSError(f"Failed to flush bars batch: {e}")

    def _flush_fundamentals(self) -> None:
        """Flush fundamentals batch."""
        batch = self.writer.get_batch("fundamentals")
        if not batch:
            return

        try:
            fundamentals = [Fundamentals(**record) for record in batch]
            count = self.client.upsert_fundamentals(fundamentals)
            self.stats.total_rows += count
            self.stats.total_batches += 1
        except Exception as e:
            self.stats.total_errors += 1
            raise MDSError(f"Failed to flush fundamentals batch: {e}")

    def _flush_news(self) -> None:
        """Flush news batch."""
        batch = self.writer.get_batch("news")
        if not batch:
            return

        try:
            news = [News(**record) for record in batch]
            count = self.client.upsert_news(news)
            self.stats.total_rows += count
            self.stats.total_batches += 1
        except Exception as e:
            self.stats.total_errors += 1
            raise MDSError(f"Failed to flush news batch: {e}")

    def _flush_options(self) -> None:
        """Flush options batch."""
        batch = self.writer.get_batch("options")
        if not batch:
            return

        try:
            options = [OptionSnap(**record) for record in batch]
            count = self.client.upsert_options(options)
            self.stats.total_rows += count
            self.stats.total_batches += 1
        except Exception as e:
            self.stats.total_errors += 1
            raise MDSError(f"Failed to flush options batch: {e}")

    def flush_all(self) -> None:
        """Flush all pending batches."""
        self._flush_bars()
        self._flush_fundamentals()
        self._flush_news()
        self._flush_options()

    def get_stats(self) -> BatchStats:
        """Get batch processing statistics."""
        if self.stats.total_batches > 0:
            self.stats.avg_batch_size = self.stats.total_rows / self.stats.total_batches
        return self.stats


class AsyncBatchProcessor:
    """
    Async batch processor for high-throughput data ingestion.
    """

    def __init__(self, client: AMDS, config: BatchConfig):
        self.client = client
        self.config = config
        self.writer = BatchWriter(config)
        self.stats = BatchStats()

    async def add_bar(self, bar: Bar) -> None:
        """Add bar to batch."""
        self.writer.add("bars", bar.dict())
        if self.writer.should_flush("bars"):
            await self._flush_bars()

    async def add_fundamental(self, fundamental: Fundamentals) -> None:
        """Add fundamental to batch."""
        self.writer.add("fundamentals", fundamental.dict())
        if self.writer.should_flush("fundamentals"):
            await self._flush_fundamentals()

    async def add_news(self, news: News) -> None:
        """Add news to batch."""
        self.writer.add("news", news.dict())
        if self.writer.should_flush("news"):
            await self._flush_news()

    async def add_option(self, option: OptionSnap) -> None:
        """Add option to batch."""
        self.writer.add("options", option.dict())
        if self.writer.should_flush("options"):
            await self._flush_options()

    async def _flush_bars(self) -> None:
        """Flush bars batch."""
        batch = self.writer.get_batch("bars")
        if not batch:
            return

        try:
            bars = [Bar(**record) for record in batch]
            count = await self.client.upsert_bars(bars)
            self.stats.total_rows += count
            self.stats.total_batches += 1
        except Exception as e:
            self.stats.total_errors += 1
            raise MDSError(f"Failed to flush bars batch: {e}")

    async def _flush_fundamentals(self) -> None:
        """Flush fundamentals batch."""
        batch = self.writer.get_batch("fundamentals")
        if not batch:
            return

        try:
            fundamentals = [Fundamentals(**record) for record in batch]
            count = await self.client.upsert_fundamentals(fundamentals)
            self.stats.total_rows += count
            self.stats.total_batches += 1
        except Exception as e:
            self.stats.total_errors += 1
            raise MDSError(f"Failed to flush fundamentals batch: {e}")

    async def _flush_news(self) -> None:
        """Flush news batch."""
        batch = self.writer.get_batch("news")
        if not batch:
            return

        try:
            news = [News(**record) for record in batch]
            count = await self.client.upsert_news(news)
            self.stats.total_rows += count
            self.stats.total_batches += 1
        except Exception as e:
            self.stats.total_errors += 1
            raise MDSError(f"Failed to flush news batch: {e}")

    async def _flush_options(self) -> None:
        """Flush options batch."""
        batch = self.writer.get_batch("options")
        if not batch:
            return

        try:
            options = [OptionSnap(**record) for record in batch]
            count = await self.client.upsert_options(options)
            self.stats.total_rows += count
            self.stats.total_batches += 1
        except Exception as e:
            self.stats.total_errors += 1
            raise MDSError(f"Failed to flush options batch: {e}")

    async def flush_all(self) -> None:
        """Flush all pending batches."""
        await self._flush_bars()
        await self._flush_fundamentals()
        await self._flush_news()
        await self._flush_options()

    def get_stats(self) -> BatchStats:
        """Get batch processing statistics."""
        if self.stats.total_batches > 0:
            self.stats.avg_batch_size = self.stats.total_rows / self.stats.total_batches
        return self.stats
