# PHASE 6.0A — Backpressure Feedback Evaluation & Implementation Plan

**Project:** market-data-store
**Phase:** 6.0A – Backpressure Feedback (Library-First)
**Status:** 📋 **EVALUATION COMPLETE** | **READY FOR IMPLEMENTATION**
**Date:** 2025-10-15
**Evaluator:** AI Assistant

---

## 🎯 Executive Summary

### Proposal Overview
Add backpressure feedback signaling from `WriteCoordinator` to upstream producers (specifically `market-data-pipeline`), allowing for dynamic flow control based on queue depth and system health.

### Viability Assessment: ✅ **HIGHLY VIABLE**

**Key Strengths:**
- ✅ Clean architectural fit with existing Phase 4.2/4.3 infrastructure
- ✅ Minimal invasiveness - leverages existing watermark system
- ✅ Library-first approach maintains in-process simplicity
- ✅ Optional HTTP broadcast provides future distributed flexibility
- ✅ Consistent with project's patterns (pydantic-settings, loguru, prometheus)

**Key Considerations:**
- ⚠️ Requires coordination with `market-data-pipeline` (Phase 6.0B)
- ⚠️ httpx is optional dependency (needs testing/docs for graceful degradation)
- ⚠️ Settings need careful env prefix design (avoid conflicts with existing `MDS_*`)

---

## 📐 Architectural Analysis

### Current State (Phase 4.3 Complete)

```
Provider → ProviderRouter → WriteCoordinator → Workers → Sink → Database
                                   ↓
                          BoundedQueue (watermarks)
                                   ↓
                          BackpressureCallback (on_high/on_low)
                                   ↓
                          [Currently: manual coordination]
```

### Proposed State (Phase 6.0A)

```
Provider → ProviderRouter → WriteCoordinator → Workers → Sink → Database
                                   ↓
                          BoundedQueue (watermarks)
                                   ↓
                          FeedbackBus (pub/sub)
                                   ↙↓↘
                    RateCoordinator  HttpWebhook  Logging
                    (pipeline)       (optional)   (observer)
```

### Key Design Elements

#### 1. **FeedbackBus - In-Process Pub/Sub**
- **Pattern:** Observer/pub-sub for fanout
- **Rationale:** Multiple subscribers need feedback (RateCoordinator, metrics, logging)
- **Thread-safety:** Async-only (consistent with coordinator)
- **Error handling:** Best-effort delivery (no cascade failures)

#### 2. **BackpressureLevel Enum**
- **OK:** Below low watermark (normal operation)
- **SOFT:** Between low/high watermarks (cautionary)
- **HARD:** At/above high watermark (MUST slow down)

**Design Note:** Three-level system provides nuanced control:
- `SOFT` allows gradual reduction (prevent thrashing)
- `HARD` triggers immediate action
- `OK` signals clear recovery

#### 3. **FeedbackEvent - Structured Signal**
- **coordinator_id:** Identifies source (multi-coordinator support)
- **queue_size / capacity:** Absolute metrics
- **level:** Actionable state
- **reason:** Optional context (e.g., "circuit_open", "high_error_rate")

**Design Note:** Frozen dataclass ensures immutability (safe for async passing)

#### 4. **Singleton Bus Pattern**
```python
_bus: Optional[FeedbackBus] = None

def feedback_bus() -> FeedbackBus:
    global _bus
    if _bus is None:
        _bus = FeedbackBus()
    return _bus
```

**Analysis:**
- ✅ Simple for in-process use
- ✅ No DI complexity for library consumers
- ⚠️ Global state (acceptable for singleton coordinator pattern)
- 🔮 **Future:** Replace with dependency injection if multi-coordinator needed

#### 5. **HttpFeedbackBroadcaster - Optional Webhook**
- **Pattern:** Fire-and-forget HTTP POST
- **Dependency:** httpx (optional)
- **Timeout:** 2s default (prevents blocking on slow endpoints)
- **Error handling:** Log at debug level (non-critical path)

**Design Note:** Gracefully degrades if httpx not installed

---

## 🔍 Integration Point Analysis

### 1. Where to Emit Feedback

**Proposal:** Emit from `BoundedQueue` watermark logic

**Current Implementation (queue.py:104-114):**
```python
async def _maybe_signal_high(self) -> None:
    if not self._high_fired and self._size >= self._high_wm:
        self._high_fired = True
        if self._on_high:
            await self._on_high()

async def _maybe_signal_low(self) -> None:
    if self._high_fired and self._size <= self._low_wm:
        self._high_fired = False
        if self._on_low:
            await self._on_low()
```

**Proposed Enhancement:**
```python
async def _maybe_signal_high(self) -> None:
    if not self._high_fired and self._size >= self._high_wm:
        self._high_fired = True
        await self._emit_feedback(BackpressureLevel.HARD)
        if self._on_high:
            await self._on_high()

async def _maybe_signal_low(self) -> None:
    if self._high_fired and self._size <= self._low_wm:
        self._high_fired = False
        await self._emit_feedback(BackpressureLevel.OK)
        if self._on_low:
            await self._on_low()
```

**Additional Emission Points:**
1. **After each put()** - Emit SOFT when transitioning into mid-range
2. **On stop()** - Emit OK to signal recovery/shutdown
3. **On circuit breaker open** - Emit HARD with reason="circuit_open"

### 2. coordinator_id Sourcing

**Current:** WriteCoordinator has `coord_id` parameter (default: "default")
**Proposed:** Pass `coord_id` to BoundedQueue constructor

**Changes Required:**
```python
# write_coordinator.py (line 77-85)
self._q = BoundedQueue[T](
    capacity=capacity,
    coord_id=coord_id,  # NEW
    # ... existing params
)

# queue.py (line 15-26)
def __init__(
    self,
    capacity: int,
    coord_id: str = "default",  # NEW
    # ... existing params
):
    self._coord_id = coord_id
```

### 3. Backward Compatibility

**Critical Assessment:**
- ✅ All new code is additive (no breaking changes)
- ✅ Existing callbacks (`on_high`/`on_low`) continue to work
- ✅ FeedbackBus is optional - coordinator works without subscribers
- ✅ HttpBroadcaster is opt-in via settings

**Migration Path:** Users can adopt incrementally:
1. **Phase 1:** Deploy feedback code (no-op if unused)
2. **Phase 2:** Subscribe to FeedbackBus in pipeline
3. **Phase 3:** Optionally enable HTTP webhook

---

## 🧪 Testing Strategy

### Unit Tests Required

#### 1. **test_feedback_bus.py** (NEW)
```python
- test_subscribe_unsubscribe
- test_publish_to_multiple_subscribers
- test_subscriber_exception_isolation (ensure one failure doesn't break others)
- test_singleton_accessor
```

#### 2. **test_feedback_integration.py** (NEW)
```python
- test_coordinator_emits_on_watermark_cross
- test_soft_level_emission (mid-range queue)
- test_ok_on_recovery
- test_coordinator_id_propagation
```

#### 3. **test_http_broadcast.py** (NEW)
```python
- test_http_post_on_event (mock httpx)
- test_graceful_degradation_without_httpx
- test_timeout_handling
- test_settings_integration
```

#### 4. **Existing Test Updates**
- `test_queue_watermarks.py` - Add feedback emission assertions
- `test_write_coordinator.py` - Verify feedback bus integration

### Integration Testing Considerations
- **Mock httpx:** Use `pytest-httpx` or similar for HTTP tests
- **Event ordering:** Verify SOFT → HARD → OK transitions
- **Concurrency:** Test multiple coordinators publishing simultaneously
- **Performance:** Ensure <1ms overhead per emit

---

## 📦 Dependencies & Environment

### New Dependencies

#### Required
None (all code uses stdlib + existing deps)

#### Optional
```toml
# pyproject.toml [project.optional-dependencies]
feedback = [
    "httpx>=0.27.0",  # For HTTP webhook broadcaster
]
```

**Installation:**
```bash
pip install .[feedback]  # With webhook support
pip install .            # Without webhook (still works)
```

### Environment Variables

**New Settings Class:** `FeedbackSettings`

**Proposed Env Vars:**
```bash
# Feedback HTTP broadcast settings
MDS_FB_ENABLE_HTTP_BROADCAST=false      # Enable HTTP webhook
MDS_FB_FEEDBACK_WEBHOOK_URL=http://...  # Target webhook URL
```

**Design Rationale:**
- `MDS_FB_` prefix avoids collision with existing `MDS_*` (coordinator runtime)
- Clear naming: "FB" = Feedback
- Follows existing pattern from `CoordinatorRuntimeSettings` (`MDS_` prefix)

### Settings File Structure

**Proposed:** `src/market_data_store/coordinator/settings.py` (UPDATE existing)

**Current Structure:**
```
src/market_data_store/coordinator/
├── settings.py  (CoordinatorRuntimeSettings)
```

**Proposal Says:** Create `src/market_data_store/settings/feedback.py`

**Recommendation:** ⚠️ **MODIFY PROPOSAL**
- Keep all coordinator settings in `coordinator/settings.py` (cohesion)
- No need for new `settings/` directory (over-engineering for 2 settings)
- Add `FeedbackSettings` class to existing `settings.py`

**Rationale:**
- Coordinator feedback is tightly coupled to coordinator module
- Avoid directory proliferation
- Consistent with Phase 4.2B approach (all settings in one file)

---

## 🔄 Implementation Phases

### Phase 1: Core Feedback Infrastructure (2-3 hours)
**Files:**
- `src/market_data_store/coordinator/feedback.py` (NEW)
- `tests/unit/coordinator/test_feedback_bus.py` (NEW)

**Deliverables:**
- `BackpressureLevel` enum
- `FeedbackEvent` dataclass
- `FeedbackSubscriber` protocol
- `FeedbackBus` implementation
- `feedback_bus()` singleton accessor
- Unit tests (8-10 tests)

**Success Criteria:**
- ✅ All tests pass
- ✅ 0 linter errors
- ✅ Subscriber isolation verified

---

### Phase 2: Queue Integration (1-2 hours)
**Files:**
- `src/market_data_store/coordinator/queue.py` (UPDATE)
- `src/market_data_store/coordinator/write_coordinator.py` (UPDATE)
- `tests/unit/coordinator/test_queue_watermarks.py` (UPDATE)
- `tests/unit/coordinator/test_feedback_integration.py` (NEW)

**Changes:**
1. Add `coord_id` parameter to `BoundedQueue`
2. Implement `_emit_feedback()` method in `BoundedQueue`
3. Call `_emit_feedback()` in watermark methods
4. Pass `coord_id` from `WriteCoordinator` to `BoundedQueue`
5. Emit SOFT level when transitioning mid-range

**Success Criteria:**
- ✅ Backward compatible (existing tests still pass)
- ✅ Feedback events emitted on watermark cross
- ✅ coordinator_id correctly propagated
- ✅ SOFT level emitted appropriately

---

### Phase 3: HTTP Broadcaster (1-2 hours)
**Files:**
- `src/market_data_store/coordinator/http_broadcast.py` (NEW)
- `src/market_data_store/coordinator/settings.py` (UPDATE)
- `tests/unit/coordinator/test_http_broadcast.py` (NEW)

**Deliverables:**
- `HttpFeedbackBroadcaster` class
- `FeedbackSettings` (add to existing settings.py)
- Graceful httpx import handling
- Unit tests with mocked httpx

**Success Criteria:**
- ✅ Works without httpx installed (logs warning)
- ✅ HTTP POST fires with correct payload
- ✅ Timeout handling tested
- ✅ Settings loaded from environment

---

### Phase 4: Documentation & Examples (1 hour)
**Files:**
- `PHASE_6.0A_IMPLEMENTATION.md` (NEW)
- `examples/run_coordinator_feedback.py` (NEW)
- Update `README.md` (add Phase 6.0A section)
- Update `cursorrules/solution_manifest.json` (if needed)

**Deliverables:**
- Comprehensive usage guide
- Example showing in-process feedback
- Example showing HTTP webhook setup
- Integration guide for `market-data-pipeline`

**Success Criteria:**
- ✅ Clear migration path documented
- ✅ Examples run successfully
- ✅ Phase 6.0B coordination explained

---

## ⚠️ Risks & Mitigations

### Risk 1: Performance Overhead
**Concern:** Emitting feedback on every put/get could slow queue operations

**Mitigation:**
- Only emit on state transitions (not every operation)
- Use `asyncio.create_task()` for fire-and-forget pub/sub
- Benchmark: Ensure <1ms overhead per emit

**Test:** Add performance test comparing queue throughput with/without feedback

---

### Risk 2: Subscriber Exception Cascade
**Concern:** One bad subscriber could crash others

**Mitigation:**
- Already handled in proposal: `try/except` around each subscriber
- Log exceptions at debug level (avoid spam)
- Continue delivery to remaining subscribers

**Test:** `test_subscriber_exception_isolation`

---

### Risk 3: HTTP Webhook Blocking
**Concern:** Slow/down webhook endpoint could block coordinator

**Mitigation:**
- 2s timeout (configurable)
- Fire-and-forget pattern (no await on response processing)
- Log failures at debug level (not error)

**Test:** Mock slow endpoint, verify timeout enforcement

---

### Risk 4: Circular Dependency with Pipeline
**Concern:** Store depends on pipeline, pipeline depends on store

**Mitigation:**
- **Library-first design:** Store emits events, pipeline subscribes
- No import of pipeline code in store
- Protocol-based coupling (FeedbackSubscriber)
- Clear ownership: Store owns FeedbackBus, pipeline subscribes

**Validation:** Ensure `market_data_store` has zero imports from `market_data_pipeline`

---

### Risk 5: Environment Variable Collision
**Concern:** `MDS_FB_*` might collide with future pipeline vars

**Mitigation:**
- Prefix follows existing pattern (`MDS_*` = store namespace)
- `FB` clearly indicates "Feedback" submodule
- Document in both repos

**Alternative:** Use `MDS_COORD_FB_*` (even more specific)

**Recommendation:** Stick with `MDS_FB_*` (sufficient specificity)

---

## 🎯 Acceptance Criteria

### Phase 6.0A Complete When:

#### Code Quality
- ✅ All new code follows project standards (100 char line length, type hints)
- ✅ 0 linter errors (ruff, black)
- ✅ All docstrings present (module + class level)
- ✅ Loguru used (not print)

#### Testing
- ✅ 15+ new unit tests passing
- ✅ Existing 35 coordinator tests still pass (backward compat)
- ✅ Coverage >90% for new code
- ✅ Integration test with mock pipeline subscriber

#### Functionality
- ✅ FeedbackBus publishes to multiple subscribers
- ✅ Watermark crossings trigger correct levels (OK/SOFT/HARD)
- ✅ coordinator_id propagates correctly
- ✅ HTTP broadcaster works with httpx
- ✅ HTTP broadcaster gracefully degrades without httpx
- ✅ Settings load from environment

#### Documentation
- ✅ Implementation guide written
- ✅ Usage examples provided
- ✅ README updated with Phase 6.0A section
- ✅ Phase 6.0B integration path documented

---

## 🔮 Phase 6.0B Preview (Pipeline Integration)

**Not in Scope for 6.0A, but documented for planning:**

### Pipeline Changes Required
```python
# market-data-pipeline/src/operators/backpressure_operator.py
from market_data_store.coordinator import feedback_bus, FeedbackEvent

class BackpressureOperator:
    def __init__(self, rate_coordinator: RateCoordinator):
        self.rate_coord = rate_coordinator
        feedback_bus().subscribe(self._on_feedback)

    async def _on_feedback(self, event: FeedbackEvent):
        if event.level == "hard":
            await self.rate_coord.reduce_rate(0.5)  # 50% reduction
        elif event.level == "soft":
            await self.rate_coord.reduce_rate(0.8)  # 20% reduction
        elif event.level == "ok":
            await self.rate_coord.restore_rate()
```

### Metrics to Add (Phase 6.0B)
```python
FEEDBACK_EVENTS_TOTAL = Counter(
    "mds_feedback_events_total",
    "Feedback events published",
    ["coordinator_id", "level"]
)

FEEDBACK_SUBSCRIBERS = Gauge(
    "mds_feedback_subscribers",
    "Active feedback subscribers"
)
```

---

## 📊 Effort Estimate

| Phase | Estimated Time | Complexity |
|-------|---------------|------------|
| Phase 1: Core Infrastructure | 2-3 hours | Low |
| Phase 2: Queue Integration | 1-2 hours | Medium |
| Phase 3: HTTP Broadcaster | 1-2 hours | Low |
| Phase 4: Documentation | 1 hour | Low |
| **Total** | **5-8 hours** | **Low-Medium** |

### Complexity Factors
- ✅ Low: Clear architectural fit, well-defined requirements
- ✅ Low: No complex algorithms or data structures
- ⚠️ Medium: Integration with existing watermark system requires care
- ⚠️ Medium: Testing HTTP broadcaster requires mocking

---

## 🚦 Go/No-Go Recommendation

### ✅ **RECOMMENDATION: PROCEED WITH IMPLEMENTATION**

**Justification:**
1. **Clean Design:** Proposal follows existing patterns and is minimally invasive
2. **High Value:** Enables critical end-to-end flow control (Phase 6.0B dependency)
3. **Low Risk:** Well-isolated changes, excellent backward compatibility
4. **Testable:** Clear test strategy with good coverage
5. **Documented:** Comprehensive evaluation and plan in place

### Prerequisites Before Starting:
1. ✅ Phase 4.3 complete (confirmed via evaluation)
2. ✅ Virtual environment activated
3. ✅ No pending coordinator tests failures
4. ⚠️ Confirm `pydantic-settings>=2.0` installed (check: `pip list | grep pydantic-settings`)

### Suggested Modifications to Proposal:
1. **Settings Location:** Keep `FeedbackSettings` in `coordinator/settings.py` (not new directory)
2. **Additional Emission Point:** Emit SOFT level when queue size transitions into mid-range
3. **Metric Addition:** Add feedback emission counter in Phase 1 (not defer to 6.0B)
4. **Coordinator Stop:** Emit OK level on coordinator stop() for clean recovery signal

---

## 📋 Implementation Checklist

### Pre-Implementation
- [ ] Verify all Phase 4.3 tests pass: `pytest tests/unit/coordinator/ -v`
- [ ] Confirm pydantic-settings installed
- [ ] Review existing coordinator code (queue.py, write_coordinator.py)
- [ ] Create feature branch: `git checkout -b feature/phase-6.0a-feedback`

### Phase 1: Core Infrastructure
- [ ] Create `feedback.py` with all core classes
- [ ] Create `test_feedback_bus.py` with 8-10 tests
- [ ] Run tests: `pytest tests/unit/coordinator/test_feedback_bus.py -v`
- [ ] Run linter: `ruff check src/market_data_store/coordinator/feedback.py`
- [ ] Format: `black src/market_data_store/coordinator/feedback.py`

### Phase 2: Queue Integration
- [ ] Add `coord_id` to BoundedQueue
- [ ] Implement `_emit_feedback()` method
- [ ] Update watermark methods to emit feedback
- [ ] Pass coord_id from WriteCoordinator
- [ ] Update `test_queue_watermarks.py`
- [ ] Create `test_feedback_integration.py`
- [ ] Run all coordinator tests: `pytest tests/unit/coordinator/ -v`

### Phase 3: HTTP Broadcaster
- [ ] Create `http_broadcast.py` with HttpFeedbackBroadcaster
- [ ] Add FeedbackSettings to `settings.py`
- [ ] Create `test_http_broadcast.py` with httpx mocks
- [ ] Test graceful degradation (without httpx)
- [ ] Update `__init__.py` to export new classes
- [ ] Run all tests: `pytest tests/unit/coordinator/ -v`

### Phase 4: Documentation
- [ ] Write `PHASE_6.0A_IMPLEMENTATION.md`
- [ ] Create `examples/run_coordinator_feedback.py`
- [ ] Update `README.md` with Phase 6.0A section
- [ ] Update `cursorrules/solution_manifest.json`
- [ ] Test examples: `python examples/run_coordinator_feedback.py`

### Post-Implementation
- [ ] Final test run: `pytest tests/ -v`
- [ ] Final lint check: `ruff check src/`
- [ ] Final format: `black src/`
- [ ] Run integration demo: `python examples/run_pipeline_to_store.py`
- [ ] Verify metrics endpoint: `curl http://localhost:9000/metrics`
- [ ] Create PR with comprehensive description

---

## 📚 Reference Links

### Existing Documentation
- [PHASE_4.2A_WRITE_COORDINATOR.md](PHASE_4.2A_WRITE_COORDINATOR.md) - Coordinator architecture
- [PHASE_4.3_INTEGRATION.md](PHASE_4.3_INTEGRATION.md) - Integration patterns
- [PHASE_4_COMPLETE.md](PHASE_4_COMPLETE.md) - Complete Phase 4 overview

### Code References
- `src/market_data_store/coordinator/queue.py:104-114` - Watermark methods
- `src/market_data_store/coordinator/write_coordinator.py:42-59` - Coordinator init
- `src/market_data_store/coordinator/settings.py` - Existing settings pattern

### External
- [Pydantic Settings Docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [httpx Documentation](https://www.python-httpx.org/)
- [asyncio Pub/Sub Patterns](https://docs.python.org/3/library/asyncio-task.html)

---

## 🎓 Design Patterns Used

| Pattern | Application | Justification |
|---------|-------------|---------------|
| **Observer (Pub/Sub)** | FeedbackBus | Multiple consumers need feedback |
| **Singleton** | feedback_bus() | Single global bus for in-process use |
| **Protocol** | FeedbackSubscriber | Duck typing for subscribers |
| **Strategy** | BackpressureLevel | Encapsulates feedback strategies |
| **Immutable Data** | FeedbackEvent (frozen) | Safe async passing |
| **Graceful Degradation** | Optional httpx | Works without HTTP support |
| **Fire-and-Forget** | HTTP broadcast | Non-blocking webhook |

---

## ✅ Final Assessment

**Viability Score: 9/10**

**Strengths:**
- Excellent architectural fit
- Minimal code changes required
- Clear testing strategy
- Good backward compatibility
- Well-documented proposal

**Minor Concerns:**
- Settings directory structure (easily addressed)
- httpx as optional dependency (needs clear docs)
- Performance testing needed (minor)

**Confidence Level: HIGH**

**Recommendation: PROCEED WITH IMPLEMENTATION**

---

**Evaluation Complete:** October 15, 2025
**Next Step:** Begin Phase 1 implementation (Core Feedback Infrastructure)
**Expected Completion:** October 15-16, 2025 (1-2 days)

---

*This evaluation was conducted with full analysis of existing codebase, architectural patterns, testing infrastructure, and project standards. All recommendations are based on code review and feasibility analysis.*
