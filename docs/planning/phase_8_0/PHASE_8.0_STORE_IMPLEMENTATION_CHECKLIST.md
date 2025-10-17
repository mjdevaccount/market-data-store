# Phase 8.0 Store v0.4.0 — Implementation Checklist

**Purpose:** Step-by-step execution checklist for implementing Core v1.1.0 contract adoption
**Use:** Check off items as you complete them; track progress daily

---

## Pre-Implementation Checklist

### Prerequisites (Complete Before Starting)
- [ ] Core v1.1.0 has been published and is available via pip
- [ ] Core v1.1.0 documentation is accessible (DTO schemas, protocols)
- [ ] Feature branch created: `feature/phase-8.0-core-contracts`
- [ ] Development environment ready (venv activated, dependencies current)
- [ ] All existing tests pass on current `master` branch
- [ ] Open questions (Q1-Q5) answered by Core team

### Environment Setup
```powershell
# Verify environment
.\.venv\Scripts\Activate.ps1
python --version  # Should be 3.11+
pytest --version
git status        # Should be on feature branch

# Verify Core availability
pip search market-data-core  # Verify v1.1.0 exists
```

---

## Phase 1: Foundation (Target: 4 hours)

### 1.1 Add Core Dependency
- [ ] Update `pyproject.toml`:
  - [ ] Change `version = "0.4.0"` (line 3)
  - [ ] Add `"market-data-core>=1.1.0"` to dependencies (line 7)
- [ ] Update `requirements.txt`:
  - [ ] Add `market-data-core>=1.1.0` at top
- [ ] Install and verify:
  ```powershell
  pip install -e .
  python -c "import market_data_core; print(market_data_core.__version__)"
  ```
- [ ] Commit: `feat: add market-data-core v1.1.0 dependency`

**Validation:**
- [ ] `pip list | grep market-data-core` shows v1.1.0+
- [ ] No import errors when importing `market_data_core.telemetry`

---

### 1.2 Fix Config Bug
- [ ] Edit `src/datastore/config.py`:
  - [ ] Add `ADMIN_TOKEN: str = "changeme"` field (after line 7)
- [ ] Test config loads:
  ```python
  from datastore.config import get_settings
  settings = get_settings()
  print(settings.admin_token)  # Should not error
  ```
- [ ] Update `.env.example` (if exists):
  ```
  ADMIN_TOKEN=your-secure-token-here
  ```
- [ ] Commit: `fix: add missing ADMIN_TOKEN field to Settings`

**Validation:**
- [ ] `settings.admin_token` accessible (no AttributeError)
- [ ] FastAPI app starts without errors

---

### 1.3 Inspect Core v1.1.0 Schemas

**Before proceeding to Phase 2, verify Core exports:**

```python
# Run this validation script
from market_data_core.telemetry import FeedbackEvent, BackpressureLevel, HealthStatus, HealthComponent
from market_data_core.protocols import FeedbackPublisher
import inspect

# Check FeedbackEvent signature
print("FeedbackEvent fields:")
print(inspect.signature(FeedbackEvent.__init__))

# Check for utilization property
print(f"Has utilization property: {hasattr(FeedbackEvent, 'utilization')}")

# Check BackpressureLevel values
print("BackpressureLevel values:")
for level in BackpressureLevel:
    print(f"  {level.name} = {level.value}")

# Check HealthStatus signature
print("HealthStatus fields:")
print(inspect.signature(HealthStatus.__init__))

# Check FeedbackPublisher protocol
print("FeedbackPublisher methods:")
print([m for m in dir(FeedbackPublisher) if not m.startswith('_')])
```

**Document findings:**
- [ ] FeedbackEvent has fields: `coordinator_id`, `queue_size`, `capacity`, `level`, `reason`, `ts`, `source`
- [ ] FeedbackEvent has `utilization` property: YES / NO (circle one)
- [ ] BackpressureLevel values: `ok`, `soft`, `hard` (verify match)
- [ ] HealthStatus has fields: `service`, `state`, `components`, `version`, `ts`
- [ ] FeedbackPublisher has method: `publish(event: FeedbackEvent) -> None`

**Decision Point:**
- [ ] If Core FeedbackEvent matches local (95%+) → Use direct import (continue Phase 2A)
- [ ] If Core FeedbackEvent differs significantly → Use adapter pattern (see Phase 2B)

---

## Phase 2: Feedback Contract Adoption (Target: 6 hours)

### 2.1 Update Feedback Module

**File:** `src/market_data_store/coordinator/feedback.py`

- [ ] **Backup original file** (for comparison):
  ```powershell
  cp feedback.py feedback.py.backup
  ```

- [ ] **Update imports** (lines 10-16):
  - [ ] Remove: `from dataclasses import dataclass`
  - [ ] Remove: `from enum import Enum`
  - [ ] Add: `from market_data_core.telemetry import FeedbackEvent, BackpressureLevel`

- [ ] **Delete local DTOs** (lines 18-50):
  - [ ] Delete `BackpressureLevel` enum definition
  - [ ] Delete `FeedbackEvent` dataclass definition
  - [ ] Keep `FeedbackSubscriber` protocol (lines 53-62)
  - [ ] Keep `FeedbackBus` class (lines 65-142)
  - [ ] Keep `feedback_bus()` function (lines 149-168)

- [ ] **Update docstring** (line 1-7):
  - [ ] Add note: "As of v0.4.0, FeedbackEvent and BackpressureLevel imported from market_data_core.telemetry"

- [ ] **Test imports work**:
  ```python
  from market_data_store.coordinator.feedback import FeedbackEvent, BackpressureLevel
  print(FeedbackEvent)  # Should be Core DTO
  ```

- [ ] Commit: `refactor: migrate FeedbackEvent to Core v1.1.0 contracts`

**Validation:**
- [ ] `from .feedback import FeedbackEvent` works
- [ ] `FeedbackEvent.__module__` shows `market_data_core.telemetry`
- [ ] No linter errors in `feedback.py`

---

### 2.2 Update Queue Module

**File:** `src/market_data_store/coordinator/queue.py`

- [ ] **Update imports** (line 7):
  ```python
  # Old:
  from .feedback import BackpressureLevel, FeedbackEvent, feedback_bus

  # New:
  from market_data_core.telemetry import BackpressureLevel, FeedbackEvent
  from .feedback import feedback_bus
  ```

- [ ] **Update `_emit_feedback` method** (lines 108-117):
  - [ ] Add `import time` at top of method (if `ts` field required)
  - [ ] Add `ts=time.time()` parameter to FeedbackEvent constructor
  - [ ] Add `source="store"` parameter to FeedbackEvent constructor
  - [ ] Verify all required fields present based on Phase 1.3 findings

- [ ] **Example:**
  ```python
  async def _emit_feedback(self, level: BackpressureLevel, reason: str | None = None) -> None:
      import time
      event = FeedbackEvent(
          coordinator_id=self._coord_id,
          queue_size=self._size,
          capacity=self._capacity,
          level=level,
          reason=reason,
          source="store",      # ← ADD if Core requires
          ts=time.time(),      # ← ADD if Core requires
      )
      await feedback_bus().publish(event)
  ```

- [ ] Commit: `refactor: update queue to use Core FeedbackEvent`

**Validation:**
- [ ] No import errors
- [ ] FeedbackEvent constructor accepts all parameters (no TypeError)
- [ ] No linter errors

---

### 2.3 Update HTTP Broadcaster

**File:** `src/market_data_store/coordinator/http_broadcast.py`

- [ ] **Update imports** (line 15):
  ```python
  # Old:
  from .feedback import FeedbackEvent, feedback_bus

  # New:
  from market_data_core.telemetry import FeedbackEvent
  from .feedback import feedback_bus
  ```

- [ ] **Verify payload construction** (lines 111-118):
  - [ ] Check if `event.level.value` still works (should be fine)
  - [ ] Check if `event.utilization` still exists (if not, remove from payload or calculate inline)

- [ ] Commit: `refactor: update HTTP broadcaster to use Core FeedbackEvent`

**Validation:**
- [ ] No import errors
- [ ] Payload dict construction succeeds
- [ ] JSON serialization works

---

### 2.4 Update Coordinator Exports

**File:** `src/market_data_store/coordinator/__init__.py`

- [ ] **Update imports** (lines 26-32):
  ```python
  # Old:
  from .feedback import (
      BackpressureLevel,
      FeedbackEvent,
      FeedbackSubscriber,
      FeedbackBus,
      feedback_bus,
  )

  # New:
  from market_data_core.telemetry import BackpressureLevel, FeedbackEvent
  from .feedback import (
      FeedbackSubscriber,
      FeedbackBus,
      feedback_bus,
  )
  ```

- [ ] Commit: `refactor: expose Core DTOs in coordinator __init__`

**Validation:**
- [ ] `from market_data_store.coordinator import FeedbackEvent` works
- [ ] External consumers can still import as before

---

### 2.5 (Optional) Implement Redis Publisher

**Skip this step if Redis publisher not required for v0.4.0**

- [ ] Create `src/market_data_store/coordinator/redis_publisher.py`
- [ ] Implement `RedisFeedbackPublisher` class conforming to `FeedbackPublisher` protocol
- [ ] Add to `__init__.py` exports
- [ ] Add `redis[asyncio]` to optional dependencies
- [ ] Commit: `feat: add RedisFeedbackPublisher conforming to Core protocol`

**Validation:**
- [ ] `isinstance(publisher, FeedbackPublisher)` returns True
- [ ] `publish()` method accepts `FeedbackEvent`
- [ ] Graceful degradation if Redis unavailable

---

### Phase 2 Validation (Run Before Proceeding)

```powershell
# Run feedback-related tests
pytest tests/unit/coordinator/test_feedback_bus.py -v
pytest tests/unit/coordinator/test_feedback_integration.py -v
pytest tests/unit/coordinator/test_http_broadcast.py -v

# Expected: Some tests may fail due to import issues - fix in Phase 4
```

---

## Phase 3: Health Contract Adoption (Target: 4 hours)

### 3.1 Update Health Endpoint

**File:** `src/datastore/service/app.py`

- [ ] **Add Core imports** (after line 12):
  ```python
  from market_data_core.telemetry import HealthStatus, HealthComponent
  ```

- [ ] **Refactor `/healthz` endpoint** (lines 58-61 → expand to ~30 lines):
  - [ ] Change signature: `@app.get("/healthz", response_model=HealthStatus)`
  - [ ] Make async: `async def healthz()`
  - [ ] Add DB health check (move from `/readyz`)
  - [ ] Build `components` list
  - [ ] Determine overall `state` (degraded if any component degraded)
  - [ ] Return `HealthStatus` DTO with `service`, `state`, `components`, `version`, `ts`

- [ ] **Example:**
  ```python
  @app.get("/healthz", response_model=HealthStatus)
  async def healthz():
      STORE_UP.set(1)

      # Check DB
      db_state = "healthy"
      try:
          from sqlalchemy import create_engine, text
          settings = get_settings()
          engine = create_engine(settings.database_url)
          with engine.connect() as conn:
              conn.execute(text("SELECT 1"))
      except Exception as e:
          logger.error(f"DB health check failed: {e}")
          db_state = "degraded"

      components = [
          HealthComponent(name="database", state=db_state),
          HealthComponent(name="prometheus", state="healthy"),
      ]

      overall_state = "degraded" if any(c.state != "healthy" for c in components) else "healthy"

      return HealthStatus(
          service="market-data-store",
          state=overall_state,
          components=components,
          version="0.4.0",
          ts=time.time(),
      )
  ```

- [ ] Commit: `refactor: upgrade /healthz to use Core HealthStatus`

**Validation:**
- [ ] Endpoint compiles (no syntax errors)
- [ ] FastAPI generates OpenAPI schema correctly
- [ ] `response_model=HealthStatus` works

---

### 3.2 Update Readiness Endpoint

**File:** `src/datastore/service/app.py`

- [ ] **Refactor `/readyz` endpoint** (lines 64-77 → update):
  - [ ] Change signature: `@app.get("/readyz", response_model=HealthStatus)`
  - [ ] Make async: `async def readyz()`
  - [ ] Return `HealthStatus` DTO on success
  - [ ] Keep 503 exception on failure

- [ ] **Example:**
  ```python
  @app.get("/readyz", response_model=HealthStatus)
  async def readyz():
      try:
          from sqlalchemy import create_engine, text
          settings = get_settings()
          engine = create_engine(settings.database_url)
          with engine.connect() as conn:
              conn.execute(text("SELECT 1"))

          components = [
              HealthComponent(name="database", state="healthy"),
          ]

          return HealthStatus(
              service="market-data-store",
              state="healthy",
              components=components,
              version="0.4.0",
              ts=time.time(),
          )
      except Exception as e:
          logger.error(f"Readiness check failed: {e}")
          raise HTTPException(status_code=503, detail="Service not ready")
  ```

- [ ] Commit: `refactor: upgrade /readyz to use Core HealthStatus`

**Validation:**
- [ ] Endpoint compiles
- [ ] 503 still raised on failure (readiness semantics preserved)

---

### Phase 3 Validation (Manual Testing)

```powershell
# Start FastAPI service
uvicorn datastore.service.app:app --reload --port 8081

# Test health endpoint
curl http://localhost:8081/healthz | jq

# Expected response:
{
  "service": "market-data-store",
  "state": "healthy",
  "components": [
    {"name": "database", "state": "healthy"},
    {"name": "prometheus", "state": "healthy"}
  ],
  "version": "0.4.0",
  "ts": 1697654400.0
}

# Test readiness endpoint
curl http://localhost:8081/readyz | jq

# Test with DB down (stop Docker postgres)
curl http://localhost:8081/healthz | jq
# Should show "state": "degraded"
```

- [ ] `/healthz` returns `HealthStatus` JSON
- [ ] `/readyz` returns `HealthStatus` JSON (or 503)
- [ ] Health shows "degraded" when DB fails
- [ ] Readiness returns 503 when DB fails
- [ ] Old consumers can still parse response (backward compatible)

---

## Phase 4: Contract Tests (Target: 6 hours)

### 4.1 Create Contract Schema Tests

**File:** `tests/unit/test_contract_schemas.py` (NEW)

- [ ] Create new file
- [ ] Add imports:
  ```python
  from market_data_core.telemetry import FeedbackEvent, BackpressureLevel, HealthStatus, HealthComponent
  from market_data_store.coordinator import FeedbackBus
  ```
- [ ] Implement tests:
  - [ ] `test_feedback_event_schema_roundtrip()` - JSON serialize/deserialize
  - [ ] `test_backpressure_level_values()` - Enum values match
  - [ ] `test_health_status_schema()` - HealthStatus roundtrip
  - [ ] `test_health_component_state_enum()` - State values valid
- [ ] Commit: `test: add Core v1.1.0 contract schema tests`

**Validation:**
```powershell
pytest tests/unit/test_contract_schemas.py -v
```
- [ ] All tests pass
- [ ] JSON roundtrip successful
- [ ] Enum values match expected

---

### 4.2 Create Protocol Conformance Tests

**File:** `tests/unit/test_feedback_publisher_contract.py` (NEW)

- [ ] Create new file
- [ ] Add imports:
  ```python
  from market_data_core.protocols import FeedbackPublisher
  from market_data_store.coordinator import HttpFeedbackBroadcaster
  # Optionally: RedisFeedbackPublisher if implemented
  ```
- [ ] Implement tests:
  - [ ] `test_http_broadcaster_has_required_methods()` - Has `start`, `stop`, publish-like method
  - [ ] `test_redis_publisher_conforms_to_protocol()` - If implemented
- [ ] Commit: `test: add FeedbackPublisher protocol conformance tests`

**Validation:**
```powershell
pytest tests/unit/test_feedback_publisher_contract.py -v
```
- [ ] Protocol conformance validated
- [ ] Required methods present

---

### 4.3 Create Health Integration Tests

**File:** `tests/integration/test_health_contract.py` (NEW)

- [ ] Create new file
- [ ] Add imports:
  ```python
  from fastapi.testclient import TestClient
  from market_data_core.telemetry import HealthStatus
  from datastore.service.app import app
  ```
- [ ] Implement tests:
  - [ ] `test_healthz_returns_health_status()` - Parse as Core DTO
  - [ ] `test_readyz_returns_health_status()` - Parse as Core DTO
  - [ ] `test_health_degraded_when_component_fails()` - Mock DB failure
- [ ] Commit: `test: add health endpoint contract integration tests`

**Validation:**
```powershell
pytest tests/integration/test_health_contract.py -v
```
- [ ] Health endpoints return valid Core DTOs
- [ ] Degraded state detected correctly

---

### 4.4 Update Existing Tests (Import Fixes)

**Files to update:**
- `tests/unit/coordinator/test_feedback_bus.py`
- `tests/unit/coordinator/test_feedback_integration.py`
- `tests/unit/coordinator/test_http_broadcast.py`
- `tests/unit/coordinator/test_queue_watermarks.py` (if exists)

**For each file:**
- [ ] Update imports:
  ```python
  # Old:
  from market_data_store.coordinator.feedback import BackpressureLevel, FeedbackEvent, feedback_bus

  # New:
  from market_data_core.telemetry import BackpressureLevel, FeedbackEvent
  from market_data_store.coordinator.feedback import feedback_bus
  ```
- [ ] If Core FeedbackEvent lacks `utilization` property:
  - [ ] Replace `event.utilization` with `event.queue_size / event.capacity`

- [ ] Commit (per file): `test: update imports to use Core DTOs`

**Validation (after each file):**
```powershell
pytest tests/unit/coordinator/test_feedback_bus.py -v
pytest tests/unit/coordinator/test_feedback_integration.py -v
pytest tests/unit/coordinator/test_http_broadcast.py -v
```
- [ ] All existing tests pass
- [ ] No import errors
- [ ] No test logic changes (only imports/calculations)

---

### Phase 4 Validation (Full Test Suite)

```powershell
# Run ALL tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=market_data_store --cov=datastore

# Check for failures
# Expected: 100% pass rate (no regressions)
```

- [ ] All unit tests pass (20+ tests)
- [ ] All integration tests pass
- [ ] All contract tests pass (new)
- [ ] Code coverage remains high (>85%)
- [ ] No flaky tests

---

## Phase 5: Integration & Documentation (Target: 4 hours)

### 5.1 Full Integration Testing

**Manual Testing Checklist:**

- [ ] Start services:
  ```powershell
  # Start DB
  docker-compose up -d postgres

  # Start FastAPI
  uvicorn datastore.service.app:app --reload --port 8081
  ```

- [ ] Test health endpoints:
  ```powershell
  curl http://localhost:8081/healthz | jq
  curl http://localhost:8081/readyz | jq
  ```

- [ ] Test feedback flow:
  ```python
  # Run demo script
  python examples/run_coordinator_demo.py
  # Observe feedback events logged
  ```

- [ ] Test metrics:
  ```powershell
  curl http://localhost:8081/metrics
  # Verify coordinator metrics present
  ```

- [ ] **Test backward compatibility:**
  - [ ] Old health consumer script (expects `{"ok": True}`) still works
  - [ ] Feedback events JSON parseable by old consumers

---

### 5.2 Update Documentation

#### CHANGELOG.md

- [ ] Create or update `CHANGELOG.md`:
  ```markdown
  # Changelog

  ## [0.4.0] - 2025-10-XX

  ### Added
  - Core v1.1.0 telemetry contract adoption
  - Health endpoints return structured `HealthStatus` DTO
  - Contract tests for schema compliance

  ### Changed
  - `FeedbackEvent` and `BackpressureLevel` imported from `market_data_core.telemetry`
  - `/healthz` and `/readyz` return Core `HealthStatus` (backward compatible)
  - Version bump to 0.4.0

  ### Fixed
  - Added missing `ADMIN_TOKEN` field to Settings class

  ### Deprecated
  - Local `FeedbackEvent` and `BackpressureLevel` definitions
  ```
- [ ] Commit: `docs: add v0.4.0 CHANGELOG entry`

---

#### README.md

- [ ] Update version references (line 105):
  ```markdown
  ### 🏷️ Current Release: [v0.4.0]

  **What's included:**
  - ✅ Core v1.1.0 telemetry contract adoption
  - ✅ Standardized HealthStatus and FeedbackEvent DTOs
  - ✅ All v0.3.0 features retained
  ```

- [ ] Update installation examples to reference v0.4.0

- [ ] Commit: `docs: update README for v0.4.0 release`

---

### 5.3 Version Tagging

- [ ] Ensure `pyproject.toml` has `version = "0.4.0"`
- [ ] Commit: `chore: bump version to 0.4.0`
- [ ] Tag release:
  ```powershell
  git tag -a v0.4.0 -m "Release v0.4.0: Core v1.1.0 contract adoption"
  ```

---

### Phase 5 Validation (Final Checks)

**Pre-Release Checklist:**

- [ ] All tests pass (100%)
- [ ] No linter errors (`ruff check .`)
- [ ] No type errors (if using mypy)
- [ ] Documentation complete (CHANGELOG, README)
- [ ] Version bumped to 0.4.0 in all locations
- [ ] Git tagged with v0.4.0
- [ ] CI pipeline passes (if configured)
- [ ] Manual testing successful
- [ ] Backward compatibility verified
- [ ] Rollback plan documented

---

## Post-Implementation

### Deployment Validation

After deploying to staging/production:

- [ ] Health endpoint returns Core DTO:
  ```bash
  curl https://store.example.com/healthz | jq '.service'
  # Expected: "market-data-store"
  ```

- [ ] Feedback events flow correctly (monitor logs/metrics)

- [ ] No errors in application logs

- [ ] Prometheus metrics remain stable

- [ ] Grafana dashboards show expected data

---

### Rollback Testing (Before Production)

**Test rollback procedure in staging:**

```powershell
# Rollback to v0.3.0
git checkout v0.3.0
pip install -e .

# Restart services
# Verify services work

# Redeploy v0.4.0
git checkout v0.4.0
pip install -e .

# Verify rollback/upgrade cycle works
```

- [ ] Rollback completes in < 5 minutes
- [ ] Services functional after rollback
- [ ] No data loss during rollback
- [ ] Upgrade from rollback works

---

### Success Metrics (Track for 1 Week)

- [ ] Zero incidents related to DTO changes
- [ ] No consumer breakage reported
- [ ] Health checks responding correctly
- [ ] Feedback flow operational
- [ ] Performance stable (no regressions)
- [ ] CI contract tests passing

---

## Troubleshooting Guide

### Common Issues

**Issue 1: Import errors after Phase 2**

**Symptom:**
```
ModuleNotFoundError: No module named 'market_data_core'
```

**Solution:**
```powershell
pip install market-data-core>=1.1.0
pip install -e .
```

---

**Issue 2: FeedbackEvent constructor TypeError**

**Symptom:**
```
TypeError: __init__() got an unexpected keyword argument 'source'
```

**Solution:**
- Core FeedbackEvent doesn't have `source` field
- Remove `source="store"` from queue.py line 114

---

**Issue 3: Test failures due to missing `utilization`**

**Symptom:**
```
AttributeError: 'FeedbackEvent' object has no attribute 'utilization'
```

**Solution:**
- Core DTO lacks `utilization` property
- Replace `event.utilization` with `event.queue_size / event.capacity`
- Update tests: `test_feedback_event_utilization()`, `test_feedback_event_queue_utilization()`

---

**Issue 4: Health endpoint 500 error**

**Symptom:**
```
ValidationError: HealthStatus missing required field
```

**Solution:**
- Check Core HealthStatus required fields match your constructor
- Verify `ts=time.time()` is present
- Check `HealthComponent` state values are valid

---

**Issue 5: Tests fail with schema mismatch**

**Symptom:**
```
AssertionError: HealthStatus.state expected 'healthy', got 'degraded'
```

**Solution:**
- Check DB is running (for health tests)
- Mock DB failures correctly in tests
- Verify component state logic

---

## Sign-Off

### Phase Completion

- [ ] **Phase 1 Complete** - Foundation (4h) - Signed: __________ Date: __________
- [ ] **Phase 2 Complete** - Feedback Contracts (6h) - Signed: __________ Date: __________
- [ ] **Phase 3 Complete** - Health Contracts (4h) - Signed: __________ Date: __________
- [ ] **Phase 4 Complete** - Contract Tests (6h) - Signed: __________ Date: __________
- [ ] **Phase 5 Complete** - Integration & Docs (4h) - Signed: __________ Date: __________

### Final Approval

- [ ] **Tech Lead Approval** - Signed: __________ Date: __________
- [ ] **Core Team Approval** - Signed: __________ Date: __________
- [ ] **QA Approval** - Signed: __________ Date: __________
- [ ] **Ready for Production** - Signed: __________ Date: __________

---

**Document Version:** 1.0
**Last Updated:** 2025-10-17
**Implementation Status:** ⏳ Not Started
**Target Completion:** __________ (fill in date)
