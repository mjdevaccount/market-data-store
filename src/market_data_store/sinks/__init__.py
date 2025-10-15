"""
Async sinks for high-throughput ingestion.

Implements:
• BaseSink  – common context & metrics
• BarsSink  – AMDS.upsert_bars
• OptionsSink – AMDS.upsert_options
• FundamentalsSink – AMDS.upsert_fundamentals
• NewsSink – AMDS.upsert_news
"""

from .base import BaseSink, SINK_WRITES_TOTAL, SINK_WRITE_LATENCY
from .bars_sink import BarsSink
from .options_sink import OptionsSink
from .fundamentals_sink import FundamentalsSink
from .news_sink import NewsSink

__all__ = [
    "BaseSink",
    "BarsSink",
    "OptionsSink",
    "FundamentalsSink",
    "NewsSink",
    "SINK_WRITES_TOTAL",
    "SINK_WRITE_LATENCY",
]
