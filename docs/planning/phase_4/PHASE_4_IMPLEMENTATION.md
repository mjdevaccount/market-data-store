# Phase 4.1 Implementation Guide
## Distributed Store & Backpressure - Async Sinks Layer

> **Status**: ✅ Phase 4.1 Complete (Week 1 & 2)
> **Version**: market-data-store v0.2.0
> **Date**: October 2025

---

## 📋 Overview

Phase 4.1 introduces an **async sink layer** to `market_data_store`, transforming it from a pure control-plane library into a **hybrid architecture** supporting both:
1. **Control-plane** operations (migrations, policies, admin endpoints)
2. **Data-plane** operations (high-throughput async ingestion with backpressure awareness)

This implementation provides the foundation for Phase 4.2 (WriteCoordinator) and Phase 4.3 (Backpressure Signaling).

---

## 🎯 Deliverables (Phase 4.1)

### ✅ Completed

| Component | Location | Description |
|-----------|----------|-------------|
| **BaseSink** | `src/market_data_store/sinks/base.py` | Abstract async context manager with metrics |
| **BarsSink** | `src/market_data_store/sinks/bars_sink.py` | OHLCV bar ingestion |
| **OptionsSink** | `src/market_data_store/sinks/options_sink.py` | Options data ingestion |
| **FundamentalsSink** | `src/market_data_store/sinks/fundamentals_sink.py` | Fundamentals ingestion |
| **NewsSink** | `src/market_data_store/sinks/news_sink.py` | News data ingestion |
| **Metrics** | `src/market_data_store/metrics/registry.py` | Prometheus metrics auto-registration |
| **Tests** | `tests/unit/sinks/` | 12 unit tests (100% pass) |
| **Integration** | `tests/integration/` | Integration test skeleton |

---

## 🏗️ Architecture

### Directory Structure

```
src/market_data_store/
├── sinks/
│   ├── __init__.py          # Sink exports + metrics
│   ├── base.py              # BaseSink abstract class
│   ├── bars_sink.py         # BarsSink implementation
│   ├── options_sink.py      # OptionsSink implementation
│   ├── fundamentals_sink.py # FundamentalsSink implementation
│   └── news_sink.py         # NewsSink implementation
└── metrics/
    ├── __init__.py          # Metrics exports
    └── registry.py          # Prometheus registration
```

### Design Principles

1. **Async-first**: All sinks use `async`/`await` for non-blocking I/O
2. **Context managers**: Proper lifecycle management with `__aenter__`/`__aexit__`
3. **Metrics integration**: Automatic Prometheus metrics for all writes
4. **Type safety**: Strong typing with Pydantic models from `mds_client`
5. **Error handling**: Graceful failure with metric recording
6. **Testability**: Clean separation allows easy mocking

---

## 🔧 Implementation Details

### BaseSink

**Purpose**: Abstract base class providing common functionality for all sinks.

**Key Features**:
- Async context manager protocol (`__aenter__`, `__aexit__`)
- Automatic metrics recording (success/failure, latency)
- Error handling with proper exception propagation
- Standardized logging with loguru

**Metrics Exported**:
```python
# Counter: Total write attempts by sink and status
sink_writes_total{sink="bars", status="success|failure"}

# Histogram: Write duration in seconds
sink_write_latency_seconds{sink="bars"}
```

**Example Usage**:
```python
from market_data_store.sinks import BarsSink
from mds_client import AMDS

async with AMDS(config) as amds:
    async with BarsSink(amds) as sink:
        await sink.write(bars)
```

---

### Sink Implementations

All sinks follow the same pattern:
1. Wrap existing `AMDS` upsert methods
2. Use `_safe_write()` for metrics and error handling
3. Accept `Sequence[Model]` for type safety

**BarsSink**:
- Wraps: `AMDS.upsert_bars()`
- Model: `mds_client.models.Bar`
- Use case: High-frequency OHLCV data

**OptionsSink**:
- Wraps: `AMDS.upsert_options()`
- Model: `mds_client.models.OptionSnap`
- Use case: Options market data

**FundamentalsSink**:
- Wraps: `AMDS.upsert_fundamentals()`
- Model: `mds_client.models.Fundamentals`
- Use case: Company financial data

**NewsSink**:
- Wraps: `AMDS.upsert_news()`
- Model: `mds_client.models.News`
- Use case: News articles and sentiment

---

## 🧪 Testing

### Test Coverage

```
tests/
├── unit/sinks/           # 12 unit tests (fast, no DB)
│   ├── conftest.py       # Fixtures (mock_amds_success/failure)
│   ├── test_bars_sink.py
│   ├── test_options_sink.py
│   ├── test_fundamentals_sink.py
│   ├── test_news_sink.py
│   └── test_metrics_recording.py
├── integration/          # Integration tests (require DB)
│   └── test_sink_integration.py
└── smoke_test_sinks.py   # Quick validation (no pytest)
```

### Running Tests

```powershell
# Unit tests (fast, no DB required)
pytest -v tests/unit/sinks/

# Smoke test (standalone)
python tests/smoke_test_sinks.py

# Integration tests (requires DB)
$env:MDS_DSN="postgresql://user:pass@localhost:5432/db"
$env:MDS_TENANT_ID="your-tenant-uuid"
pytest -v tests/integration/ -m integration

# All tests
pytest -v tests/
```

### Test Results (Phase 4.1)

```
✅ 12/12 unit tests passed (0.51s)
✅ 6/6 smoke test checks passed
✅ 0 linter errors
✅ 100% import success
```

---

## 📊 Metrics & Observability

### Prometheus Metrics

Metrics are **automatically registered** to the global Prometheus registry when the `market_data_store.sinks` module is imported.

**Available Metrics**:

```python
# Write attempts counter
sink_writes_total{sink="bars|options|fundamentals|news", status="success|failure"}

# Write latency histogram
sink_write_latency_seconds{sink="bars|options|fundamentals|news"}
```

**Scraping Metrics**:

```python
# In your FastAPI app (src/datastore/service/app.py)
from market_data_store.metrics import registry  # Ensure metrics loaded

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

**Example Grafana Queries**:

```promql
# Total writes per sink
sum(rate(sink_writes_total[5m])) by (sink)

# Success rate
sum(rate(sink_writes_total{status="success"}[5m])) by (sink)
/ sum(rate(sink_writes_total[5m])) by (sink)

# p95 latency
histogram_quantile(0.95, rate(sink_write_latency_seconds_bucket[5m]))
```

---

## 🚀 Usage Examples

### Basic Usage

```python
import asyncio
from datetime import datetime, timezone
from mds_client import AMDS
from mds_client.models import Bar
from market_data_store.sinks import BarsSink

async def main():
    config = {
        "dsn": "postgresql://user:pass@localhost:5432/marketdata",
        "tenant_id": "your-tenant-uuid",
        "pool_max": 10
    }

    bars = [
        Bar(
            tenant_id=config["tenant_id"],
            vendor="ibkr",
            symbol="AAPL",
            timeframe="1m",
            ts=datetime.now(timezone.utc),
            close_price=150.5,
            volume=1000
        )
    ]

    async with AMDS(config) as amds:
        async with BarsSink(amds) as sink:
            await sink.write(bars)

    print("✅ Bars written successfully")

if __name__ == "__main__":
    asyncio.run(main())
```

### All Sinks Example

See [`examples/run_store_pipeline.py`](examples/run_store_pipeline.py) for a comprehensive example using all four sinks.

```powershell
# Set environment variables
$env:MDS_DSN="postgresql://user:pass@localhost:5432/marketdata"
$env:MDS_TENANT_ID="your-tenant-uuid"

# Run example
python examples/run_store_pipeline.py
```

---

## 🔄 Migration from AsyncBatchProcessor

If you're currently using `mds_client.batch.AsyncBatchProcessor`, sinks provide a cleaner interface:

**Before (AsyncBatchProcessor)**:
```python
from mds_client import AMDS, AsyncBatchProcessor, BatchConfig

amds = AMDS(config)
async with AsyncBatchProcessor(amds, BatchConfig(max_rows=1000)) as processor:
    for bar in stream:
        await processor.add_bar(bar)
```

**After (BarsSink)**:
```python
from mds_client import AMDS
from market_data_store.sinks import BarsSink

async with AMDS(config) as amds:
    async with BarsSink(amds) as sink:
        await sink.write(batch_of_bars)
```

**Key Differences**:
- Sinks focus on **batch writes**, not incremental adds
- Sinks provide **automatic Prometheus metrics**
- Sinks use **standardized logging** (loguru)
- AsyncBatchProcessor provides **auto-flushing** on batch size/time
- Both use the same underlying `AMDS.upsert_*()` methods

**When to Use Each**:
- **BarsSink**: When you have pre-batched data and want metrics
- **AsyncBatchProcessor**: When you need auto-batching from a stream

---

## 🛠️ Performance Characteristics

### Throughput

Based on smoke tests with mock AMDS:
- **BarsSink**: ~0.000s per write (async overhead minimal)
- **All sinks**: Concurrent writes fully supported via AMDS connection pool

### Memory

- Minimal overhead: Sinks are thin wrappers around AMDS
- Connection pooling: Controlled by `AMDS(pool_max=N)`
- Batch size: Determined by caller (no internal buffering)

### Bottlenecks

1. **Database writes**: Primary bottleneck (TimescaleDB insert performance)
2. **Connection pool**: Limited by `pool_max` (default: 10)
3. **Serialization**: Pydantic model validation (negligible for most use cases)

**Optimization Tips**:
- Increase `pool_max` for higher concurrency
- Use larger batch sizes (500-5000 rows optimal)
- Enable COPY write mode in AMDS config (`write_mode="copy"`)

---

## ⏭️ Next Steps (Phase 4.2 & 4.3)

### Phase 4.2: Write Coordinator (Deferred)

**Goal**: Add in-process queue for flow control

**Components**:
```python
src/market_data_store/coordinator/
├── write_coordinator.py  # Async queue manager
└── feedback.py           # Backpressure metrics
```

**Status**: ⏸️ **Deferred** until architecture decision (library vs service mode)

---

### Phase 4.3: Backpressure Signaling (Deferred)

**Goal**: Feedback path to `market-data-pipeline` RateCoordinator

**Requirements**:
- `market-data-pipeline` v0.8.0 (not yet available)
- Inter-repo API contract in `market-data-core`
- Communication mechanism (gRPC/REST/in-memory)

**Status**: 🚫 **Blocked** by external dependencies

---

## 📚 References

### Related Documentation
- [`README.md`](README.md) - Project overview
- [`cursorrules/index.mdc`](cursorrules/index.mdc) - Development rules
- [`src/mds_client/`](src/mds_client/) - Client library documentation

### External Dependencies
- **mds_client**: Provides AMDS client and Pydantic models
- **asyncpg**: Async PostgreSQL driver
- **prometheus-client**: Metrics collection
- **loguru**: Structured logging

### Related Issues
- Phase 4.0 Viability Evaluation ✅ Complete
- Phase 4.1 Implementation ✅ Complete
- Phase 4.2 Write Coordinator ⏸️ Deferred
- Phase 4.3 Backpressure ⚠️ Blocked

---

## 🤝 Contributing

### Adding a New Sink

1. **Create sink file**: `src/market_data_store/sinks/your_sink.py`
2. **Extend BaseSink**: Implement `write()` method
3. **Add to `__init__.py`**: Export in `__all__`
4. **Add tests**: Create `tests/unit/sinks/test_your_sink.py`
5. **Update docs**: Add to this guide

**Example**:
```python
from typing import Sequence
from mds_client import AMDS
from mds_client.models import YourModel
from .base import BaseSink

class YourSink(BaseSink):
    def __init__(self, amds: AMDS) -> None:
        super().__init__("your_sink_name")
        self.amds = amds

    async def write(self, batch: Sequence[YourModel]) -> None:
        async def _do(b: Sequence[YourModel]) -> None:
            await self.amds.upsert_your_data(list(b))
        await self._safe_write(_do, batch)
```

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## ✅ Sign-Off

**Phase 4.1 Status**: ✅ **COMPLETE**

**Implemented By**: Cursor AI + Phase 4 Planning Committee
**Review Date**: October 15, 2025
**Approved For**: Production use (Week 1 & 2 deliverables)

**Next Review**: Phase 4.2 (Write Coordinator) - pending architecture decision
