# Phase 4.2A – Write Coordinator Implementation

## 📋 Overview

**Phase 4.2A** delivers the **Write Coordinator** for `market_data_store`: an in-process async queue + worker pool that provides:

- **Bounded Queue** with watermarks and overflow strategies
- **Worker Pool** with batching, time-based flushing, and retry policies
- **Backpressure Signaling** via high/low watermark callbacks
- **Graceful Shutdown** with queue draining
- **Health Checks** for monitoring worker and queue state

## 🏗️ Architecture

```
Producer(s)
    ↓
submit() / submit_many()
    ↓
WriteCoordinator
    ↓
BoundedQueue (watermarks + overflow)
    ↓
WorkerPool[1..N]
    ↓
Retry Logic (RetryPolicy)
    ↓
Sink (BarsSink, OptionsSink, etc.)
    ↓
Database
```

### Key Components

| Component | Purpose | Key Features |
|-----------|---------|--------------|
| **WriteCoordinator** | High-level orchestrator | Context manager, submit API, health checks |
| **BoundedQueue** | Async bounded queue | High/low watermarks, overflow strategies (block, drop_oldest, error) |
| **SinkWorker** | Consumer task | Batching (size + time), retry with backoff, graceful stop |
| **RetryPolicy** | Error retry logic | Exponential backoff, jitter, retryable classifier |
| **Types** | Protocols & types | `Sink`, `BackpressureCallback`, `QueueFullError` |

## 📁 File Structure

```
src/market_data_store/coordinator/
├── __init__.py              # Public API exports
├── types.py                 # Protocols & type definitions
├── policy.py                # RetryPolicy & error classifier
├── queue.py                 # BoundedQueue with watermarks
├── worker.py                # SinkWorker with batching & retry
└── write_coordinator.py     # WriteCoordinator orchestration

examples/
└── run_coordinator_demo.py  # Working demo

tests/unit/coordinator/
├── test_policy.py           # RetryPolicy tests
├── test_queue_watermarks.py # BoundedQueue watermark tests
├── test_worker_retry.py     # SinkWorker retry tests
└── test_write_coordinator.py # WriteCoordinator integration tests
```

## 🚀 Usage

### Basic Example

```python
import asyncio
from mds_client import AMDS
from mds_client.models import Bar
from market_data_store.sinks import BarsSink
from market_data_store.coordinator import WriteCoordinator

async def main():
    amds = AMDS.from_env()
    sink = BarsSink(amds)

    async with sink, WriteCoordinator[Bar](
        sink=sink,
        capacity=10_000,
        workers=4,
        batch_size=500,
        flush_interval=0.25,
    ) as coord:
        # Submit items
        for i in range(10_000):
            bar = Bar(symbol="AAPL", open=190.0, high=192.0, low=189.0, close=191.5, volume=1000)
            await coord.submit(bar)

        # Coordinator will drain queue on exit

if __name__ == "__main__":
    asyncio.run(main())
```

### With Backpressure Callbacks

```python
async def on_high():
    logger.warning("⚠️ Backpressure HIGH - slow down producers")
    # Optional: signal to pipeline's RateCoordinator to reduce intake

async def on_low():
    logger.info("✅ Backpressure recovered - resume normal rate")

async with WriteCoordinator[Bar](
    sink=sink,
    capacity=10_000,
    high_watermark=8000,
    low_watermark=5000,
    on_backpressure_high=on_high,
    on_backpressure_low=on_low,
) as coord:
    # ...
```

### Advanced Configuration

```python
from market_data_store.coordinator import RetryPolicy

# Custom retry policy
retry = RetryPolicy(
    max_attempts=5,
    initial_backoff_ms=50,
    max_backoff_ms=2000,
    backoff_multiplier=2.0,
    jitter=True,
    classify_retryable=lambda exc: isinstance(exc, (TimeoutError, ConnectionError)),
)

async with WriteCoordinator[Bar](
    sink=sink,
    capacity=10_000,
    workers=8,
    batch_size=1000,
    flush_interval=0.5,
    overflow_strategy="drop_oldest",
    retry_policy=retry,
) as coord:
    # ...
```

## 🧪 Testing

### Run All Coordinator Tests

```bash
pytest -v tests/unit/coordinator/
```

**Expected Result:** All 15 tests pass ✅

### Test Coverage

- **RetryPolicy:** Default classifier, backoff curves, custom classifiers, jitter
- **BoundedQueue:** Watermark signals, overflow strategies (block, drop_oldest, error)
- **SinkWorker:** Retry on transient errors, exhausting retries, time-based flush
- **WriteCoordinator:** Submit, drain, health checks, backpressure callbacks, graceful shutdown

### Run Demo

```bash
python examples/run_coordinator_demo.py
```

**Expected Output:**
- Coordinator starts with 2 workers, capacity 1000
- Backpressure HIGH triggered when queue fills
- Workers process batches of 50 items in parallel
- Backpressure recovered when queue drains
- All 5,000 items processed
- Graceful shutdown with queue drain

## ⚙️ Configuration Reference

### WriteCoordinator Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sink` | `Sink[T]` | **required** | Target sink for writes |
| `capacity` | `int` | `10_000` | Queue capacity |
| `workers` | `int` | `4` | Number of worker tasks |
| `batch_size` | `int` | `500` | Max items per batch |
| `flush_interval` | `float` | `0.25` | Max seconds between flushes |
| `high_watermark` | `int \| None` | `0.8 * capacity` | Queue size to trigger backpressure HIGH |
| `low_watermark` | `int \| None` | `0.5 * capacity` | Queue size to trigger backpressure recovery |
| `overflow_strategy` | `"block" \| "drop_oldest" \| "error"` | `"block"` | Behavior when queue is full |
| `on_backpressure_high` | `BackpressureCallback \| None` | `None` | Callback when high watermark hit |
| `on_backpressure_low` | `BackpressureCallback \| None` | `None` | Callback when low watermark recovered |
| `drop_callback` | `Callable[[T], Awaitable[None]] \| None` | `None` | Callback when item dropped (drop_oldest) |
| `retry_policy` | `RetryPolicy \| None` | `RetryPolicy()` | Retry configuration |

### RetryPolicy Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_attempts` | `int` | `5` | Max retry attempts per batch |
| `initial_backoff_ms` | `int` | `50` | Initial backoff in milliseconds |
| `max_backoff_ms` | `int` | `2000` | Max backoff cap |
| `backoff_multiplier` | `float` | `2.0` | Exponential multiplier |
| `jitter` | `bool` | `True` | Add jitter (50-100% of calculated backoff) |
| `classify_retryable` | `Callable[[Exception], bool]` | `default_retry_classifier` | Function to classify retryable errors |

### Overflow Strategies

| Strategy | Behavior | Use Case |
|----------|----------|----------|
| `"block"` | Producer waits until space available | Default, ensures no data loss |
| `"drop_oldest"` | Removes oldest item to make space | Real-time streams, okay to drop old data |
| `"error"` | Raises `QueueFullError` | Fail-fast, let caller handle |

## 📊 Metrics

Phase 4.2A reuses the **Phase 4.1 sink metrics**:

- `sink_writes_total{sink, status}` – Counter of write attempts (success/failure)
- `sink_write_latency_seconds{sink}` – Histogram of write durations

**Future (Phase 4.2B):**
- `coordinator_queue_depth` – Gauge of current queue size
- `coordinator_worker_errors_total` – Counter of worker crashes
- `coordinator_items_dropped_total` – Counter of dropped items (drop_oldest strategy)

## 🔍 Health Monitoring

```python
health = coord.health()
print(f"Workers alive: {health.workers_alive}/{coord._workers}")
print(f"Queue depth: {health.queue_size}/{health.capacity}")
```

**CoordinatorHealth Fields:**
- `workers_alive` – Number of active worker tasks
- `queue_size` – Current queue depth
- `capacity` – Queue capacity

## 🚧 Limitations & Future Work

### Current Limitations (Phase 4.2A)
- **No Dead Letter Queue (DLQ):** Items that fail after all retries are dropped
- **No Circuit Breaker:** No automatic pause on repeated failures
- **Basic Metrics:** No queue depth or worker error counters yet
- **No Dynamic Scaling:** Worker count is fixed at startup
- **In-Process Only:** No distributed coordination across services

### Planned Enhancements (Phase 4.2B+)

| Feature | Priority | Target |
|---------|----------|--------|
| Dead Letter Queue | High | 4.2B |
| Circuit Breaker | High | 4.2B |
| Queue Depth Metrics | Medium | 4.2B |
| Worker Error Metrics | Medium | 4.2B |
| Dynamic Worker Scaling | Low | 4.3 |
| Distributed Coordination | Low | 4.3 |
| gRPC Backpressure API | Medium | 4.3 |

## 🔗 Integration with market-data-pipeline

### Current State (Phase 4.2A)
The coordinator is **library-first** and operates in-process. No cross-repo dependencies yet.

### Future Integration (Phase 4.3)
When `market-data-pipeline` reaches v0.8.0+, you can wire backpressure callbacks to `RateCoordinator`:

```python
# In pipeline's sink operator
from market_data_pipeline import RateCoordinator
from market_data_store.coordinator import WriteCoordinator

rate_coord = RateCoordinator.from_config()

async def on_high():
    await rate_coord.reduce_tokens()  # Slow down pipeline

async def on_low():
    await rate_coord.restore_tokens()  # Resume normal rate

coord = WriteCoordinator(
    sink=bars_sink,
    on_backpressure_high=on_high,
    on_backpressure_low=on_low,
)
```

This gives true **end-to-end flow control** from source → pipeline → store.

## 📝 Implementation Notes

### Design Decisions

1. **BoundedQueue watermarks fire once:** High watermark triggers once when crossed, low watermark triggers once when recovered. This prevents callback spam.

2. **Workers use time-based + size-based flushing:** Workers flush when either `batch_size` items collected OR `flush_interval` seconds elapsed. This ensures low-latency writes even under low load.

3. **Graceful shutdown drains queue:** On context exit, coordinator waits for queue to drain (up to `timeout` seconds) before stopping workers. This prevents data loss.

4. **Retry classifier checks both type and message:** `default_retry_classifier` checks both the exception type name and message text for keywords like "timeout", "temporary", etc. This improves retryability detection.

5. **Drop callback is async:** When using `drop_oldest` overflow strategy, the `drop_callback` is async to allow logging, metrics, or DLQ writes.

### Thread Safety
All operations are async-safe using `asyncio` primitives (`Queue`, `Event`, `Lock`). No threading or multiprocessing is used.

### Memory Usage
Memory usage scales with:
- Queue capacity (`capacity` parameter)
- Batch size (`batch_size` parameter)
- Number of workers (`workers` parameter)

Typical memory footprint: **10-50 MB** for capacity=10,000, workers=4, batch_size=500.

## 🎯 Success Criteria

Phase 4.2A is **complete** and **production-ready** when:

- ✅ All 15 unit tests pass
- ✅ Demo runs successfully
- ✅ Zero linter errors
- ✅ Backpressure callbacks fire correctly
- ✅ Graceful shutdown drains queue
- ✅ Retry logic handles transient errors
- ✅ Documentation is comprehensive

**Status: ✅ ALL CRITERIA MET**

## 🚀 Next Steps

### Immediate (Within Phase 4.2A)
1. ✅ Implement core coordinator components
2. ✅ Write comprehensive unit tests
3. ✅ Create working demo
4. ✅ Document usage and architecture

### Short-Term (Phase 4.2B - Optional)
1. Add Dead Letter Queue for failed items
2. Implement Circuit Breaker pattern
3. Add queue depth and worker error metrics
4. Create integration tests with live database

### Long-Term (Phase 4.3)
1. Wire backpressure to `market-data-pipeline` RateCoordinator
2. Add gRPC/REST backpressure API for distributed coordination
3. Implement dynamic worker scaling based on queue depth
4. Add distributed tracing with OpenTelemetry

## 📚 Additional Resources

- [Phase 4.1 Implementation (Sinks)](./PHASE_4_IMPLEMENTATION.md)
- [Cursorrules: Sinks Layer](./cursorrules/rules/sinks_layer.mdc)
- [Cursorrules: Index](./cursorrules/index.mdc)
- [Python asyncio Documentation](https://docs.python.org/3/library/asyncio.html)
- [Prometheus Python Client](https://github.com/prometheus/client_python)

## 🙏 Acknowledgments

Phase 4.2A builds on:
- **Phase 4.1** async sinks architecture
- **mds_client** AMDS async capabilities
- **market-data-core** DTO models
- User-provided architectural guidance and code scaffolding

---

**Version:** 1.0.0
**Date:** October 15, 2025
**Status:** ✅ Complete and Production-Ready
