# Phase 6.0A Architecture Diagrams

## Current State (Phase 4.3)

```
┌──────────────────────────────────────────────────────────────────┐
│                    market-data-pipeline                          │
│                      (External Package)                          │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            │ await coord.submit(bar)
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                     WriteCoordinator                             │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ BoundedQueue                                               │  │
│  │  • capacity: 10,000                                        │  │
│  │  • high_watermark: 8,000                                   │  │
│  │  • low_watermark: 5,000                                    │  │
│  │                                                            │  │
│  │  Watermark Events:                                         │  │
│  │  ├─ size >= 8000 → on_backpressure_high() callback        │  │
│  │  └─ size <= 5000 → on_backpressure_low() callback         │  │
│  │                                                            │  │
│  │  [Manual coordination required in pipeline]               │  │
│  └────────────────────────────────────────────────────────────┘  │
│                            │                                     │
│                    ┌───────┴───────┐                             │
│                    │               │                             │
│              ┌─────▼────┐    ┌────▼─────┐                        │
│              │ Worker 0 │    │ Worker 1 │  ... (4 workers)       │
│              └─────┬────┘    └────┬─────┘                        │
│                    └───────┬───────┘                             │
│                            ▼                                     │
└────────────────────────────┼─────────────────────────────────────┘
                             │ sink.write(batch)
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                        BarsSink                                  │
│                  (AMDS.upsert_bars)                              │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
                    [ TimescaleDB ]
```

**Problem:** Pipeline must manually check `coord.health().queue_size` in polling loop.

---

## Proposed State (Phase 6.0A)

```
┌──────────────────────────────────────────────────────────────────┐
│                    market-data-pipeline                          │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ RateCoordinator                                          │   │
│  │  async def on_feedback(event: FeedbackEvent):            │   │
│  │      if event.level == "hard":                           │   │
│  │          reduce_rate(0.5)  # 50% slowdown                │   │
│  │      elif event.level == "ok":                           │   │
│  │          restore_rate()    # Resume normal               │   │
│  └──────────────────▲───────────────────────────────────────┘   │
│                     │ subscribe                                 │
│                     │                                           │
└─────────────────────┼───────────────────────────────────────────┘
                      │
                      │ FeedbackBus (in-process pub/sub)
                      │
┌─────────────────────┴───────────────────────────────────────────┐
│                     WriteCoordinator                             │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ BoundedQueue                                               │  │
│  │                                                            │  │
│  │  _emit_feedback(level):                                    │  │
│  │    await feedback_bus().publish(FeedbackEvent(             │  │
│  │        coordinator_id=self.coord_id,                       │  │
│  │        queue_size=self._size,                              │  │
│  │        capacity=self._capacity,                            │  │
│  │        level=level                                         │  │
│  │    ))                                                      │  │
│  │                                                            │  │
│  │  Emission Points:                                          │  │
│  │  ├─ size >= 8000 → emit(HARD)                             │  │
│  │  ├─ 5000 < size < 8000 → emit(SOFT)                       │  │
│  │  └─ size <= 5000 → emit(OK)                               │  │
│  └────────────────────────────────────────────────────────────┘  │
│                            │                                     │
│                    ┌───────┴───────┐                             │
│                    │               │                             │
│              ┌─────▼────┐    ┌────▼─────┐                        │
│              │ Worker 0 │    │ Worker 1 │  ... (4 workers)       │
│              └─────┬────┘    └────┬─────┘                        │
│                    └───────┬───────┘                             │
│                            ▼                                     │
└────────────────────────────┼─────────────────────────────────────┘
                             │
                             ▼
                    [ BarsSink → Database ]
```

**Benefit:** Automatic, event-driven feedback. Pipeline reacts immediately without polling.

---

## FeedbackBus Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         FeedbackBus                              │
│                      (Singleton Instance)                        │
│                                                                  │
│  _subs: list[FeedbackSubscriber]                                │
│                                                                  │
│  async def publish(event: FeedbackEvent):                        │
│      for subscriber in self._subs:                               │
│          try:                                                    │
│              await subscriber(event)  # Isolated call            │
│          except Exception:                                       │
│              pass  # Best-effort delivery                        │
│                                                                  │
└──────────────────────┬──────────────┬──────────────┬─────────────┘
                       │              │              │
                       │              │              │
         ┌─────────────▼──┐   ┌───────▼──────┐  ┌───▼──────────────┐
         │ Pipeline        │   │ HTTP         │  │ Logging          │
         │ RateCoordinator │   │ Broadcaster  │  │ Observer         │
         │ (Phase 6.0B)    │   │ (Optional)   │  │ (Debug/Monitor)  │
         └─────────────────┘   └──────────────┘  └──────────────────┘
                  │                    │
                  │                    │ POST {event JSON}
                  ▼                    ▼
         [Adjust Producer]    [External Webhook]
         [Rate Limiting]      [Dashboard/Alerting]
```

---

## FeedbackEvent Data Structure

```python
@dataclass(frozen=True)
class FeedbackEvent:
    coordinator_id: str          # "bars-coord", "options-coord", etc.
    queue_size: int              # Current queue depth (e.g., 8234)
    capacity: int                # Max capacity (e.g., 10000)
    level: BackpressureLevel     # OK | SOFT | HARD
    reason: str | None           # Optional context

# Example events:
FeedbackEvent(
    coordinator_id="pipeline-store",
    queue_size=8234,
    capacity=10000,
    level=BackpressureLevel.HARD,
    reason=None
)

FeedbackEvent(
    coordinator_id="pipeline-store",
    queue_size=4567,
    capacity=10000,
    level=BackpressureLevel.OK,
    reason="queue_drained"
)
```

---

## BackpressureLevel State Machine

```
                    ┌──────────────────┐
                    │                  │
         ┌──────────▼──────────┐       │
         │       HARD           │       │
         │  (size >= 8000)      │       │
         │  Action: MUST slow   │       │
         └──────────┬───────────┘       │
                    │ queue draining    │
                    │                   │ queue filling
         ┌──────────▼───────────┐       │
         │       SOFT            │       │
         │  (5000 < size < 8000) │       │
         │  Action: gradual slow │       │
         └──────────┬───────────┘       │
                    │ queue emptying    │
                    │                   │
         ┌──────────▼───────────┐       │
         │        OK             │       │
         │  (size <= 5000)       │◄──────┘
         │  Action: normal rate  │
         └───────────────────────┘
```

---

## Emission Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Producer                                 │
│               await coord.submit(bar)                           │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ BoundedQueue.put(bar)                                           │
│                                                                 │
│  1. await self._q.put(bar)        # Add to internal queue      │
│                                                                 │
│  2. async with self._lock:                                      │
│         self._size += 1                                         │
│                                                                 │
│  3. await self._maybe_signal_high()                             │
│      ├─ if size >= high_wm:                                     │
│      │    await self._emit_feedback(HARD)  ◄─── NEW            │
│      │    if self._on_high:                                     │
│      │        await self._on_high()        # Existing callback  │
│      └─ elif low_wm < size < high_wm:                           │
│           await self._emit_feedback(SOFT)  ◄─── NEW            │
│                                                                 │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ FeedbackBus.publish(event)                                      │
│                                                                 │
│  for subscriber in self._subs:                                  │
│      try:                                                       │
│          await subscriber(event)                                │
│      except Exception:                                          │
│          pass  # Isolate failures                               │
│                                                                 │
└───────────┬──────────────────┬──────────────────────────────────┘
            │                  │
            ▼                  ▼
   ┌────────────────┐  ┌──────────────────┐
   │ Pipeline       │  │ HTTP Broadcaster │
   │ (if present)   │  │ (if enabled)     │
   └────────────────┘  └──────────────────┘
```

---

## HTTP Webhook Flow (Optional)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Coordinator Startup                          │
│                                                                 │
│  if settings.enable_http_broadcast:                             │
│      broadcaster = HttpFeedbackBroadcaster(                     │
│          url=settings.feedback_webhook_url                      │
│      )                                                          │
│      await broadcaster.start()                                  │
│      # This subscribes to feedback_bus()                        │
│                                                                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ Event published
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              HttpFeedbackBroadcaster._on_feedback()             │
│                                                                 │
│  payload = {                                                    │
│      "coordinator_id": event.coordinator_id,                    │
│      "queue_size": event.queue_size,                            │
│      "capacity": event.capacity,                                │
│      "level": event.level.value,  # "ok"|"soft"|"hard"          │
│      "reason": event.reason                                     │
│  }                                                              │
│                                                                 │
│  async with httpx.AsyncClient(timeout=2.0) as client:           │
│      await client.post(self.url, json=payload)                  │
│      # Fire-and-forget, errors logged at debug level           │
│                                                                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ HTTP POST
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   External Webhook Endpoint                     │
│            (Dashboard, Alerting, Other Services)                │
│                                                                 │
│  POST /backpressure-webhook                                     │
│  Body: {                                                        │
│      "coordinator_id": "pipeline-store",                        │
│      "queue_size": 8234,                                        │
│      "capacity": 10000,                                         │
│      "level": "hard",                                           │
│      "reason": null                                             │
│  }                                                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 6.0A File Structure

```
src/market_data_store/coordinator/
├── __init__.py                    (UPDATE - add exports)
├── feedback.py                    (NEW - 150 LOC)
│   ├── BackpressureLevel
│   ├── FeedbackEvent
│   ├── FeedbackSubscriber
│   ├── FeedbackBus
│   └── feedback_bus()
│
├── http_broadcast.py              (NEW - 50 LOC)
│   └── HttpFeedbackBroadcaster
│
├── settings.py                    (UPDATE - add FeedbackSettings)
│
├── queue.py                       (UPDATE - add _emit_feedback)
│
└── write_coordinator.py           (UPDATE - pass coord_id to queue)

tests/unit/coordinator/
├── test_feedback_bus.py           (NEW - 8-10 tests)
├── test_feedback_integration.py   (NEW - 5-7 tests)
├── test_http_broadcast.py         (NEW - 5-7 tests)
├── test_queue_watermarks.py       (UPDATE - add feedback assertions)
└── test_write_coordinator.py      (UPDATE - verify integration)

examples/
└── run_coordinator_feedback.py    (NEW - usage demo)
```

---

## Example Usage Code

### Basic In-Process Feedback

```python
from market_data_store.coordinator import (
    WriteCoordinator,
    feedback_bus,
    FeedbackEvent
)

# Subscribe to feedback
async def on_feedback(event: FeedbackEvent):
    if event.level == "hard":
        logger.warning(f"HARD backpressure from {event.coordinator_id}")
        # Slow down producer
    elif event.level == "ok":
        logger.info(f"Backpressure recovered on {event.coordinator_id}")
        # Resume normal rate

feedback_bus().subscribe(on_feedback)

# Start coordinator (feedback emits automatically)
async with WriteCoordinator[Bar](
    sink=bars_sink,
    capacity=10_000,
    coord_id="bars-coordinator"
) as coord:
    # Submit items as usual
    await coord.submit(bar)
```

### With HTTP Webhook

```python
from market_data_store.coordinator import (
    WriteCoordinator,
    HttpFeedbackBroadcaster,
    FeedbackSettings
)

# Load settings from environment
settings = FeedbackSettings(
    enable_http_broadcast=True,
    feedback_webhook_url="http://dashboard:8080/webhook"
)

# Start HTTP broadcaster
broadcaster = HttpFeedbackBroadcaster(
    url=str(settings.feedback_webhook_url)
)
await broadcaster.start()

# Coordinator runs normally, webhook fires automatically
async with WriteCoordinator[Bar](sink=bars_sink) as coord:
    await coord.submit(bar)
```

---

## Integration with market-data-pipeline (Phase 6.0B)

```python
# In market-data-pipeline (future work)
from market_data_pipeline import RateCoordinator
from market_data_store.coordinator import feedback_bus, FeedbackEvent

class BackpressureOperator:
    def __init__(self, rate_coord: RateCoordinator):
        self.rate_coord = rate_coord

        # Subscribe to store feedback
        feedback_bus().subscribe(self._on_feedback)

    async def _on_feedback(self, event: FeedbackEvent):
        """React to backpressure from store"""
        if event.level == "hard":
            # Immediate slowdown
            await self.rate_coord.set_rate_multiplier(0.5)
            logger.warning(
                f"Store backpressure HARD: "
                f"{event.queue_size}/{event.capacity}"
            )

        elif event.level == "soft":
            # Gradual slowdown
            await self.rate_coord.set_rate_multiplier(0.8)
            logger.info(
                f"Store backpressure SOFT: "
                f"{event.queue_size}/{event.capacity}"
            )

        elif event.level == "ok":
            # Resume normal rate
            await self.rate_coord.set_rate_multiplier(1.0)
            logger.info("Store backpressure recovered")
```

---

## Metrics Dashboard View (Future)

```
┌──────────────────────────────────────────────────────────────────┐
│              Backpressure Feedback Dashboard                     │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Coordinator: pipeline-store                                     │
│                                                                  │
│  Queue Depth:  ████████████░░░░░░░░░░  8,234 / 10,000  (82%)    │
│                               ▲                                  │
│                          High Watermark (8000)                   │
│                                                                  │
│  Current Level: 🔴 HARD                                          │
│                                                                  │
│  Recent Events:                                                  │
│  ├─ 14:23:45 - HARD (queue=8234)                                │
│  ├─ 14:23:42 - SOFT (queue=7123)                                │
│  └─ 14:23:38 - OK (queue=4567)                                  │
│                                                                  │
│  Pipeline Response:                                              │
│  ├─ Rate reduced to 50%                                          │
│  └─ Intake slowed from 10k/sec → 5k/sec                         │
│                                                                  │
│  Workers: 4/4 alive                                              │
│  Circuit Breaker: CLOSED                                         │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

**These diagrams complement the full evaluation in PHASE_6.0A_EVALUATION_AND_PLAN.md**
