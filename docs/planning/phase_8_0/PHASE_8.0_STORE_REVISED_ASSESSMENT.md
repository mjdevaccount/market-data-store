# Phase 8.0 Store v0.4.0 — REVISED Viability Assessment

**Date:** October 17, 2025
**Status:** ✅ **VIABLE with ADAPTER PATTERN REQUIRED**
**Core v1.1.0:** ✅ **INSTALLED & INSPECTED**

---

## 🔍 Executive Summary

After installing and inspecting Core v1.1.0, the implementation is **still viable** but requires a **different approach** than originally planned:

### Original Plan
❌ Direct import replacement: `from market_data_core.telemetry import FeedbackEvent`

### Revised Plan
✅ **Adapter Pattern**: Extend Core DTOs to preserve Store-specific fields (`reason`, `utilization`)

---

## 📊 Core v1.1.0 Inspection Results

### FeedbackEvent Schema (Core v1.1.0)

```python
# Signature from Core v1.1.0
FeedbackEvent(
    coordinator_id: str,
    queue_size: int,  # Annotated with Ge(ge=0)
    capacity: int,    # Annotated with Gt(gt=0)
    level: BackpressureLevel,
    source: str = 'store',  # ✅ Has default
    ts: float,              # ⚠️ Required, no default
)
```

**Fields Present:**
- ✅ `coordinator_id`
- ✅ `queue_size`
- ✅ `capacity`
- ✅ `level`
- ✅ `source` (default='store')
- ✅ `ts` (timestamp)

**Fields MISSING (that Store uses):**
- ❌ `reason` - Store passes optional context strings
- ❌ `utilization` property - Store calculates `queue_size / capacity`

---

### BackpressureLevel Enum

✅ **100% COMPATIBLE**

```python
BackpressureLevel.ok = 'ok'
BackpressureLevel.soft = 'soft'
BackpressureLevel.hard = 'hard'
```

---

### HealthStatus & HealthComponent

✅ **100% COMPATIBLE**

```python
HealthStatus(
    service: str,
    state: Literal['healthy', 'degraded', 'unhealthy'],
    components: list[HealthComponent] = [],
    version: str,
    ts: float,
)

HealthComponent(
    name: str,
    state: Literal['healthy', 'degraded', 'unhealthy'],
    details: Dict[str, str] = {},
)
```

---

### FeedbackPublisher Protocol

✅ **EXISTS**

```python
class FeedbackPublisher(Protocol):
    async def publish(self, event) -> None:
        ...
```

**Finding:** Protocol is simple and easy to implement

---

## ⚠️ Compatibility Issues

### Issue 1: Missing `reason` Field

**Store Current Usage:**
```python
# queue.py line 114
event = FeedbackEvent(
    coordinator_id=self._coord_id,
    queue_size=self._size,
    capacity=self._capacity,
    level=level,
    reason=reason,  # ← Core doesn't have this field!
)
```

**Impact:**
- Used in 3 places in Store codebase
- Provides context like `"high_watermark"`, `"queue_recovered"`, `"circuit_open"`
- Valuable debugging information

---

### Issue 2: Missing `utilization` Property

**Store Current Usage:**
```python
# tests/unit/coordinator/test_feedback_bus.py line 50
assert event.utilization == 0.75  # 75%
```

**Impact:**
- Used in 2 test files
- Convenient property for calculating `queue_size / capacity`
- Not critical (can be calculated inline)

---

### Issue 3: Required `ts` Parameter

**Store Current Code:**
```python
# Doesn't pass ts currently
event = FeedbackEvent(..., level=level)  # ← ts missing!
```

**Impact:**
- All emission sites need `import time` and `ts=time.time()`
- Minor change, easy to add

---

## ✅ Revised Implementation Strategy

### Option A: Extend Core DTO (RECOMMENDED)

**Create Store-specific subclass that adds missing fields:**

```python
# src/market_data_store/coordinator/feedback.py

from market_data_core.telemetry import (
    FeedbackEvent as CoreFeedbackEvent,
    BackpressureLevel,
)
from pydantic import Field
import time

class FeedbackEvent(CoreFeedbackEvent):
    """Store-extended feedback event with additional context fields.

    Extends Core v1.1.0 FeedbackEvent with:
    - reason: Optional context string for debugging
    - utilization: Computed property for queue usage percentage
    """

    # Add store-specific field
    reason: str | None = Field(default=None, description="Optional backpressure context")

    @property
    def utilization(self) -> float:
        """Queue utilization as percentage (0.0 to 1.0)."""
        return self.queue_size / self.capacity if self.capacity > 0 else 0.0

    @classmethod
    def create(
        cls,
        coordinator_id: str,
        queue_size: int,
        capacity: int,
        level: BackpressureLevel,
        reason: str | None = None,
    ) -> "FeedbackEvent":
        """Factory method that auto-fills ts and source."""
        return cls(
            coordinator_id=coordinator_id,
            queue_size=queue_size,
            capacity=capacity,
            level=level,
            source="store",
            ts=time.time(),
            reason=reason,
        )
```

**Advantages:**
- ✅ Preserves existing Store functionality (`reason`, `utilization`)
- ✅ Conforms to Core contracts (is-a relationship)
- ✅ JSON serializes with all Core fields + extras
- ✅ Can be passed to Core-compatible consumers (they ignore extra fields)
- ✅ Minimal code changes (just import path + add `.create()` calls)

**Disadvantages:**
- ⚠️ Store has "extended" DTO vs pure Core DTO
- ⚠️ Need to document extension for consumers

---

### Option B: Pure Core DTO (NOT RECOMMENDED)

**Use Core DTO as-is, remove Store-specific features:**

```python
from market_data_core.telemetry import FeedbackEvent, BackpressureLevel

# Lose 'reason' field → merge into logs instead
# Lose 'utilization' property → calculate inline in tests
```

**Advantages:**
- ✅ Pure Core contract compliance
- ✅ No extensions or adapters

**Disadvantages:**
- ❌ Lose valuable `reason` field (debugging context)
- ❌ Lose convenient `utilization` property
- ❌ More test changes required
- ❌ Less information in feedback events

**Verdict:** Not recommended due to loss of functionality

---

## 📝 Updated Implementation Plan

### Phase 2: Feedback Contract Adoption (REVISED)

**File:** `src/market_data_store/coordinator/feedback.py`

**Changes:**

1. **Import Core base DTO:**
   ```python
   from market_data_core.telemetry import (
       FeedbackEvent as CoreFeedbackEvent,
       BackpressureLevel,
   )
   ```

2. **Create extended FeedbackEvent:**
   ```python
   class FeedbackEvent(CoreFeedbackEvent):
       reason: str | None = None

       @property
       def utilization(self) -> float:
           return self.queue_size / self.capacity if self.capacity > 0 else 0.0

       @classmethod
       def create(cls, coordinator_id, queue_size, capacity, level, reason=None):
           import time
           return cls(
               coordinator_id=coordinator_id,
               queue_size=queue_size,
               capacity=capacity,
               level=level,
               source="store",
               ts=time.time(),
               reason=reason,
           )
   ```

3. **Update emission sites to use `.create()`:**
   ```python
   # queue.py line 108-117
   async def _emit_feedback(self, level: BackpressureLevel, reason: str | None = None):
       event = FeedbackEvent.create(
           coordinator_id=self._coord_id,
           queue_size=self._size,
           capacity=self._capacity,
           level=level,
           reason=reason,  # ← preserved!
       )
       await feedback_bus().publish(event)
   ```

**Test Impact:**
- ✅ No test changes needed (reason and utilization still work)
- ✅ Import paths update only

---

### Phase 3: Health Contract Adoption (UNCHANGED)

✅ **No changes from original plan** - Health DTOs are 100% compatible

---

## 🔧 Updated File Change Summary

### Modified (13 files - same as before)
- `pyproject.toml` ✅ **DONE** (version 0.4.0, Core dependency added)
- `requirements.txt` ✅ **DONE** (Core dependency added)
- `config.py` (add `admin_token` field)
- `app.py` (health endpoints use Core DTOs)
- `feedback.py` (extend Core DTO with Store fields)
- `queue.py` (use `.create()` factory method)
- `http_broadcast.py` (import path update)
- `__init__.py` (export extended FeedbackEvent)
- 4 test files (import path updates only)
- `README.md`, `CHANGELOG.md`

### New (5 files - same as before)
- `redis_publisher.py` (optional)
- `test_contract_schemas.py`
- `test_feedback_publisher_contract.py`
- `test_health_contract.py`
- `CHANGELOG.md` (if doesn't exist)

**Total:** 18 files

---

## 📊 Revised Effort Estimate

| Phase | Original | Revised | Delta | Notes |
|-------|----------|---------|-------|-------|
| 1. Foundation | 4h | 4h | - | Unchanged |
| 2. Feedback | 6h | **8h** | +2h | Adapter pattern adds complexity |
| 3. Health | 4h | 4h | - | Unchanged (100% compatible) |
| 4. Tests | 6h | **5h** | -1h | Fewer test changes (reason/utilization preserved) |
| 5. Integration | 4h | 4h | - | Unchanged |
| **TOTAL** | 24h | **25h** | +1h | Still 3-4 days |

**Conclusion:** Adapter pattern adds ~1 hour overhead but preserves functionality

---

## ✅ Revised Success Criteria

### Technical (Updated)
- ✅ FeedbackEvent extends `market_data_core.telemetry.FeedbackEvent`
- ✅ Store-specific fields (`reason`, `utilization`) **preserved**
- ✅ BackpressureLevel imported directly from Core (100% compatible)
- ✅ Health endpoints return Core `HealthStatus` (100% compatible)
- ✅ All existing tests pass **without removing functionality**
- ✅ Contract tests validate Core schema compatibility
- ✅ Config bug fixed (`ADMIN_TOKEN` added)

### Operational (Unchanged)
- ✅ Zero-downtime deployment
- ✅ Backward compatible (extended DTO serializes to superset)
- ✅ Rollback safe

---

## 🎯 Key Decisions Made

### Decision 1: Adapter Pattern vs Pure Core DTO

**Choice:** ✅ **Adapter Pattern (Option A)**

**Rationale:**
- Preserves Store's `reason` field (valuable debugging context)
- Preserves Store's `utilization` property (convenience)
- Still conforms to Core contract (extended DTO is-a Core DTO)
- Minimal test changes (no functionality removed)
- Core-compatible consumers ignore extra fields (forward compatible)

**Trade-off Accepted:**
- Store has "extended" DTO vs pure Core DTO
- Need to document extension in CHANGELOG

---

### Decision 2: Factory Method vs Direct Construction

**Choice:** ✅ **Factory Method `.create()`**

**Rationale:**
- Auto-fills `ts` and `source` (reduces boilerplate)
- Centralizes timestamp logic
- Optional: can still use direct construction if needed
- Clear API for Store-internal use

---

## 📚 Updated Documentation Needs

### CHANGELOG.md (revised entry)

```markdown
## [0.4.0] - 2025-10-XX

### Added
- Core v1.1.0 contract adoption
- `FeedbackEvent` extends Core DTO with Store-specific fields:
  - `reason`: Optional context string (e.g., "queue_recovered")
  - `utilization`: Computed property for queue usage percentage
- Health endpoints return Core `HealthStatus` DTO
- Contract tests for schema compliance

### Changed
- `FeedbackEvent` now inherits from `market_data_core.telemetry.FeedbackEvent`
- `BackpressureLevel` imported directly from Core (no local definition)
- Health endpoints return structured DTOs instead of plain dicts
- Version bump to 0.4.0

### Fixed
- Added missing `ADMIN_TOKEN` field to Settings class

### Migration Guide
**For Store developers:**
- Use `FeedbackEvent.create()` factory method for convenience
- Import `BackpressureLevel` from `market_data_core.telemetry`

**For consumers:**
- Store `FeedbackEvent` is backward compatible (Core + extras)
- Core-only consumers can parse Store events (ignore extra fields)
```

---

## 🔍 Contract Compliance Testing

### New Test: Core Schema Compliance

```python
# tests/unit/test_contract_schemas.py

def test_store_feedback_event_extends_core():
    """Store FeedbackEvent is-a Core FeedbackEvent."""
    from market_data_core.telemetry import FeedbackEvent as CoreFeedbackEvent
    from market_data_store.coordinator import FeedbackEvent

    # Type check
    assert issubclass(FeedbackEvent, CoreFeedbackEvent)

    # Create Store event
    event = FeedbackEvent.create(
        coordinator_id="test",
        queue_size=80,
        capacity=100,
        level=BackpressureLevel.hard,
        reason="test_reason",
    )

    # Verify Core fields
    assert event.coordinator_id == "test"
    assert event.queue_size == 80
    assert event.level == BackpressureLevel.hard
    assert event.source == "store"
    assert isinstance(event.ts, float)

    # Verify Store-specific fields
    assert event.reason == "test_reason"
    assert event.utilization == 0.8

    # Verify JSON serialization includes all fields
    json_dict = event.model_dump()
    assert "reason" in json_dict
    assert "utilization" not in json_dict  # Property, not field
```

---

## 🚀 Deployment Strategy (Revised)

### Stage 1: Deploy Store v0.4.0

**Sequence:**
1. Install Core v1.1.0 dependency
2. Deploy extended `FeedbackEvent` with adapter
3. Upgrade health endpoints to Core DTOs

**Compatibility:**
- ✅ Backward compatible: Old consumers parse subset of Store events
- ✅ Forward compatible: Store events work with Core-compatible systems
- ✅ Zero downtime: No breaking changes

---

### Stage 2: Deploy Pipeline v0.9.0 (Later)

**Sequence:**
1. Pipeline consumes Store `FeedbackEvent` (ignores `reason` if not needed)
2. Pipeline uses Core `BackpressureLevel` directly

**Compatibility:**
- ✅ Pipeline can parse Store events (ignores extra `reason` field)
- ✅ If Pipeline needs `reason`, it's available

---

### Stage 3: Deploy Orchestrator v0.4.0 (Later)

**Sequence:**
1. Orchestrator consumes Store health checks (Core `HealthStatus`)

**Compatibility:**
- ✅ Full Core DTO compatibility

---

## 🎯 Final Verdict

### Viability: ✅ **CONFIRMED VIABLE**

**Changes from Original Assessment:**
- ❌ Cannot use pure Core DTOs (missing Store fields)
- ✅ Can use **Adapter Pattern** (extend Core DTOs)
- ✅ Preserves all Store functionality
- ✅ Still Core-compatible (extended DTO conforms to contracts)

### Effort: **25 hours** (3-4 days, +1h from original)

### Risk: 🟡 **LOW-MEDIUM** (unchanged)
- Adapter pattern is well-tested approach
- No functionality removed
- Full backward compatibility

### Recommendation: ✅ **PROCEED with Adapter Pattern**

---

## 📋 Next Steps

1. ✅ **DONE:** Install Core v1.1.0 ✓
2. ✅ **DONE:** Inspect Core exports ✓
3. ✅ **DONE:** Update dependencies (`pyproject.toml`, `requirements.txt`) ✓
4. ⏳ **TODO:** Implement adapter pattern (Phase 2)
5. ⏳ **TODO:** Upgrade health endpoints (Phase 3)
6. ⏳ **TODO:** Add contract tests (Phase 4)
7. ⏳ **TODO:** Integration & docs (Phase 5)

---

## 📞 Open Questions ANSWERED

### Q1: Core FeedbackEvent schema?
✅ **ANSWERED:** Has `coordinator_id`, `queue_size`, `capacity`, `level`, `source`, `ts`
❌ **MISSING:** `reason`, `utilization` (Store needs adapter)

### Q2: FeedbackPublisher protocol?
✅ **ANSWERED:** `async def publish(self, event) -> None`

### Q3: HealthComponent.state values?
✅ **ANSWERED:** `Literal['healthy', 'degraded', 'unhealthy']`

### Q4: Redis publisher required?
⏳ **OPTIONAL:** Can defer to future release

### Q5: Core v1.1.0 availability?
✅ **RESOLVED:** Published and installed

---

**Document Version:** 2.0 (Revised after Core v1.1.0 inspection)
**Previous Version:** 1.0 (Pre-inspection assessment)
**Status:** ✅ **Ready to Implement with Adapter Pattern**
**Approved By:** ⏳ Pending Tech Lead Review
