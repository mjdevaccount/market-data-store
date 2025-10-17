# Phase 8.0 Store v0.4.0 — File Change Map

**Purpose:** Detailed file-by-file breakdown of changes required for Core v1.1.0 contract adoption
**Cross-reference:** See `PHASE_8.0_STORE_VIABILITY_ASSESSMENT.md` for context

---

## Files Requiring Changes

### Category: Configuration (2 files)

#### 1. `pyproject.toml`

**Change Type:** ✅ **Addition** (no breaking changes)
**Complexity:** LOW

**Before:**
```toml
[project]
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "sqlalchemy>=2.0",
  "asyncpg>=0.29",
  "alembic>=1.13",
  "psycopg[binary]>=3.2",
  "psycopg-pool>=3.2",
  "typer>=0.12",
  "pydantic>=2.7",
  "pydantic-settings>=2.0",
  "python-dotenv>=1.0",
  "prometheus-client>=0.20",
  "loguru>=0.7",
]
```

**After:**
```toml
[project]
version = "0.4.0"  # ← CHANGE from "0.3.0"

dependencies = [
  "market-data-core>=1.1.0",  # ← ADD at top
  "fastapi>=0.115",
  # ... rest unchanged
]
```

**Testing:**
```powershell
pip install -e .
python -c "import market_data_core; print(market_data_core.__version__)"
```

---

#### 2. `requirements.txt`

**Change Type:** ✅ **Addition**
**Complexity:** LOW

**Before:**
```txt
# Core dependencies for market-data-store control-plane
# Generated from pyproject.toml dependencies

# Web framework
fastapi>=0.115
...
```

**After:**
```txt
# Core dependencies for market-data-store control-plane
# Generated from pyproject.toml dependencies

# Core contracts
market-data-core>=1.1.0  # ← ADD

# Web framework
fastapi>=0.115
...
```

---

### Category: Infrastructure (2 files)

#### 3. `src/datastore/config.py`

**Change Type:** 🐛 **Bug Fix** + ✅ **Addition**
**Complexity:** LOW
**Lines Affected:** 5-9

**Current (BUGGY):**
```python
class Settings(BaseSettings):
    DATABASE_URL: str
    ADMIN_DATABASE_URL: str
    APP_PORT: int = 8081
    ALEMBIC_INI: str = "alembic.ini"
    # ❌ MISSING: admin_token field (referenced in app.py:37)
```

**Fixed:**
```python
class Settings(BaseSettings):
    DATABASE_URL: str
    ADMIN_DATABASE_URL: str
    ADMIN_TOKEN: str = "changeme"  # ← ADD (default for dev)
    APP_PORT: int = 8081
    ALEMBIC_INI: str = "alembic.ini"
```

**Rationale:** `app.py:37` references `settings.admin_token` but field doesn't exist

**Environment Variable:** `ADMIN_TOKEN=<secret>` in `.env`

---

#### 4. `src/datastore/service/app.py`

**Change Type:** ⚠️ **Major Refactor** (response model change)
**Complexity:** MEDIUM
**Lines Affected:** 1-2, 58-77

**Section A: Imports**

**Before:**
```python
from fastapi import FastAPI, Response, status, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from prometheus_client import (...)
from loguru import logger
import time
from datastore.config import get_settings
```

**After:**
```python
from fastapi import FastAPI, Response, status, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from prometheus_client import (...)
from loguru import logger
import time
from datastore.config import get_settings

# ← ADD Core imports
from market_data_core.telemetry import HealthStatus, HealthComponent
```

**Section B: Health Endpoint (lines 58-61)**

**Before:**
```python
@app.get("/healthz")
def healthz():
    STORE_UP.set(1)
    return {"ok": True}  # ← Plain dict
```

**After:**
```python
@app.get("/healthz", response_model=HealthStatus)
async def healthz():
    """Health check using Core v1.1.0 HealthStatus."""
    STORE_UP.set(1)

    # Check database connectivity
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

    # Build components
    components = [
        HealthComponent(name="database", state=db_state),
        HealthComponent(name="prometheus", state="healthy"),
    ]

    # Determine overall state
    overall_state = "degraded" if any(c.state != "healthy" for c in components) else "healthy"

    return HealthStatus(
        service="market-data-store",
        state=overall_state,
        components=components,
        version="0.4.0",
        ts=time.time(),
    )
```

**Section C: Readiness Endpoint (lines 64-77)**

**Before:**
```python
@app.get("/readyz")
def readyz():
    # Check DB connectivity
    try:
        from sqlalchemy import create_engine, text
        settings = get_settings()
        engine = create_engine(settings.database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"ready": True}  # ← Plain dict
    except Exception as e:
        logger.error(f"Database connectivity check failed: {e}")
        raise HTTPException(status_code=503, detail="Database not ready")
```

**After:**
```python
@app.get("/readyz", response_model=HealthStatus)
async def readyz():
    """Readiness check using Core v1.1.0 HealthStatus."""
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

**Backward Compatibility:** ✅ YES
- Old consumers expecting `{"ok": True}` will still work (they'll ignore extra fields)
- New consumers can parse full `HealthStatus` DTO

---

### Category: Coordinator (3 files)

#### 5. `src/market_data_store/coordinator/feedback.py`

**Change Type:** ⚠️ **Major Refactor** (DTO replacement)
**Complexity:** MEDIUM
**Lines Affected:** 10-50 (entire DTO section)

**Strategy:** Deprecate local DTOs, import from Core

**Before:**
```python
"""
Backpressure feedback system for write coordinator.
...
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol
from loguru import logger


class BackpressureLevel(str, Enum):
    """Backpressure severity levels."""
    OK = "ok"
    SOFT = "soft"
    HARD = "hard"


@dataclass(frozen=True)
class FeedbackEvent:
    """Immutable backpressure feedback event."""
    coordinator_id: str
    queue_size: int
    capacity: int
    level: BackpressureLevel
    reason: str | None = None

    @property
    def utilization(self) -> float:
        """Queue utilization as percentage (0.0 to 1.0)."""
        return self.queue_size / self.capacity if self.capacity > 0 else 0.0


class FeedbackSubscriber(Protocol):
    """Protocol for feedback event subscribers."""
    async def __call__(self, event: FeedbackEvent) -> None:
        ...
```

**After (Option A: Direct Import - if Core DTO is compatible):**
```python
"""
Backpressure feedback system for write coordinator.

NOTE: As of v0.4.0, FeedbackEvent and BackpressureLevel are imported from
market_data_core.telemetry. Local definitions are DEPRECATED.
"""

from __future__ import annotations
from typing import Protocol
from loguru import logger

# Import from Core v1.1.0
from market_data_core.telemetry import (
    FeedbackEvent,
    BackpressureLevel,
)

# Re-export for backward compatibility
__all__ = ["FeedbackEvent", "BackpressureLevel", "FeedbackSubscriber", "FeedbackBus", "feedback_bus"]


class FeedbackSubscriber(Protocol):
    """Protocol for feedback event subscribers."""
    async def __call__(self, event: FeedbackEvent) -> None:
        ...

# FeedbackBus class remains unchanged (lines 65-142)
```

**After (Option B: Adapter - if Core DTO lacks utilization):**
```python
from market_data_core.telemetry import (
    FeedbackEvent as CoreFeedbackEvent,
    BackpressureLevel,
)

# Extend Core DTO with store-specific property
@dataclass
class FeedbackEvent(CoreFeedbackEvent):
    """Store-specific feedback event extending Core DTO."""
    @property
    def utilization(self) -> float:
        return self.queue_size / self.capacity if self.capacity > 0 else 0.0
```

**Decision:** Requires Core v1.1.0 schema inspection (see Assessment Q1)

**Testing Impact:**
- 17 tests in `test_feedback_bus.py` need import path updates
- If `utilization` removed, 2-3 tests need inline calculation

---

#### 6. `src/market_data_store/coordinator/queue.py`

**Change Type:** ⚠️ **Import Change** + 🔧 **Field Addition**
**Complexity:** MEDIUM
**Lines Affected:** 7, 108-117

**Section A: Imports (line 7)**

**Before:**
```python
from .feedback import BackpressureLevel, FeedbackEvent, feedback_bus
```

**After:**
```python
from market_data_core.telemetry import BackpressureLevel, FeedbackEvent
from .feedback import feedback_bus  # Keep bus from local module
```

**Section B: Feedback Emission (lines 108-117)**

**Before:**
```python
async def _emit_feedback(self, level: BackpressureLevel, reason: str | None = None) -> None:
    """Emit feedback event to FeedbackBus."""
    event = FeedbackEvent(
        coordinator_id=self._coord_id,
        queue_size=self._size,
        capacity=self._capacity,
        level=level,
        reason=reason,
    )
    await feedback_bus().publish(event)
```

**After (add `ts` and `source` fields if Core requires them):**
```python
async def _emit_feedback(self, level: BackpressureLevel, reason: str | None = None) -> None:
    """Emit feedback event to FeedbackBus."""
    import time
    event = FeedbackEvent(
        coordinator_id=self._coord_id,
        queue_size=self._size,
        capacity=self._capacity,
        level=level,
        reason=reason,
        source="store",      # ← ADD if Core expects it
        ts=time.time(),      # ← ADD if Core expects it
    )
    await feedback_bus().publish(event)
```

**Testing Impact:**
- No test changes needed (internal implementation)

---

#### 7. `src/market_data_store/coordinator/http_broadcast.py`

**Change Type:** ⚠️ **Import Change** (minor)
**Complexity:** LOW
**Lines Affected:** 15

**Before:**
```python
from .feedback import FeedbackEvent, feedback_bus
```

**After:**
```python
from market_data_core.telemetry import FeedbackEvent
from .feedback import feedback_bus
```

**Remainder:** Lines 111-118 (payload construction) remain unchanged
- Payload dict construction uses `event.level.value` which still works
- If Core DTO has extra fields, they're not serialized (no impact)

---

#### 8. `src/market_data_store/coordinator/__init__.py` (Optional)

**Change Type:** ⚠️ **Import Update**
**Complexity:** LOW
**Lines Affected:** 26-32

**Before:**
```python
from .feedback import (
    BackpressureLevel,
    FeedbackEvent,
    FeedbackSubscriber,
    FeedbackBus,
    feedback_bus,
)
```

**After (expose Core DTOs):**
```python
from market_data_core.telemetry import BackpressureLevel, FeedbackEvent
from .feedback import (
    FeedbackSubscriber,
    FeedbackBus,
    feedback_bus,
)
```

**Rationale:** Make it clear to consumers that DTOs come from Core

---

### Category: New Files (Optional)

#### 9. `src/market_data_store/coordinator/redis_publisher.py` (NEW)

**Change Type:** ✅ **New Feature** (optional)
**Complexity:** MEDIUM
**Lines:** ~100

**Purpose:** Implement `FeedbackPublisher` protocol with Redis backend

**Full Implementation:** (See Assessment Phase 2, section 4.6)

**Key Points:**
- Conforms to `market_data_core.protocols.FeedbackPublisher`
- Uses `redis.asyncio` for async publishing
- Graceful degradation if Redis unavailable
- JSON serialization via `event.model_dump_json()`

**Decision:** Implement if Phase 8.0 requires Redis publisher; otherwise defer

---

### Category: Tests (8 files)

#### 10-16. Test Files Requiring Import Updates

**Change Type:** ⚠️ **Import Path Change**
**Complexity:** LOW (mechanical changes)

**Files:**
1. `tests/unit/coordinator/test_feedback_bus.py` (lines 8-13)
2. `tests/unit/coordinator/test_feedback_integration.py` (lines 11-15)
3. `tests/unit/coordinator/test_http_broadcast.py` (needs inspection)
4. `tests/unit/coordinator/test_queue_watermarks.py` (needs inspection)

**Pattern:**

**Before:**
```python
from market_data_store.coordinator.feedback import (
    BackpressureLevel,
    FeedbackEvent,
    feedback_bus,
)
```

**After:**
```python
from market_data_core.telemetry import BackpressureLevel, FeedbackEvent
from market_data_store.coordinator.feedback import feedback_bus
```

**Additional Changes (if Core FeedbackEvent lacks `utilization`):**

In `test_feedback_bus.py`, lines 42-50:

**Before:**
```python
def test_feedback_event_utilization():
    event = FeedbackEvent(...)
    assert event.utilization == 0.75  # 75%
```

**After:**
```python
def test_feedback_event_utilization():
    event = FeedbackEvent(...)
    utilization = event.queue_size / event.capacity  # ← Inline calculation
    assert utilization == 0.75  # 75%
```

---

#### 17. `tests/unit/test_contract_schemas.py` (NEW)

**Change Type:** ✅ **New Test File**
**Complexity:** MEDIUM
**Lines:** ~100

**Purpose:** Validate Core v1.1.0 contract compliance

**Coverage:**
- ✅ `FeedbackEvent` JSON roundtrip
- ✅ `BackpressureLevel` enum values
- ✅ `HealthStatus` schema validation
- ✅ `HealthComponent` state enum

**Full Implementation:** (See Assessment Phase 4, section 4.8)

---

#### 18. `tests/unit/test_feedback_publisher_contract.py` (NEW)

**Change Type:** ✅ **New Test File**
**Complexity:** MEDIUM
**Lines:** ~50

**Purpose:** Validate protocol conformance for publishers

**Coverage:**
- ✅ `HttpFeedbackBroadcaster` protocol methods
- ✅ `RedisFeedbackPublisher` protocol conformance (if implemented)

**Full Implementation:** (See Assessment Phase 4, section 4.8)

---

#### 19. `tests/integration/test_health_contract.py` (NEW)

**Change Type:** ✅ **New Test File**
**Complexity:** MEDIUM
**Lines:** ~80

**Purpose:** Integration tests for health endpoint contract

**Coverage:**
- ✅ `/healthz` returns `HealthStatus` DTO
- ✅ `/readyz` returns `HealthStatus` DTO
- ✅ Degraded state when components fail

**Full Implementation:** (See Assessment Phase 4, section 4.8)

---

### Category: Documentation (3 files)

#### 20. `CHANGELOG.md` (Create or Update)

**Change Type:** ✅ **Addition**
**Complexity:** LOW

**Content:**
```markdown
# Changelog

## [0.4.0] - 2025-10-XX

### Added
- Core v1.1.0 contract adoption for telemetry DTOs
- Health endpoints now return structured `HealthStatus` DTO
- Contract tests for schema compliance
- (Optional) `RedisFeedbackPublisher` implementation

### Changed
- `FeedbackEvent` and `BackpressureLevel` now imported from `market_data_core.telemetry`
- Health endpoints (`/healthz`, `/readyz`) return Core `HealthStatus` instead of plain dict
- Version bump to 0.4.0

### Fixed
- Added missing `ADMIN_TOKEN` field to `Settings` class

### Deprecated
- Local `FeedbackEvent` and `BackpressureLevel` definitions (use Core imports)

## [0.3.0] - 2024-XX-XX
...
```

---

#### 21. `README.md`

**Change Type:** ⚠️ **Update** (version references)
**Complexity:** LOW
**Lines Affected:** 105, 150+

**Changes:**
- Update "Current Release" section to v0.4.0
- Add Core v1.1.0 contract adoption to features list
- Update installation examples to reference v0.4.0

**Before:**
```markdown
### 🏷️ Current Release: [v0.3.0]
```

**After:**
```markdown
### 🏷️ Current Release: [v0.4.0]

**What's included:**
- ✅ Core v1.1.0 telemetry contract adoption
- ✅ Standardized `HealthStatus` and `FeedbackEvent` DTOs
- ✅ All v0.3.0 features retained
```

---

#### 22. `PHASE_8.0_STORE_VIABILITY_ASSESSMENT.md` (This Document)

**Change Type:** ✅ **New Documentation**
**Purpose:** Implementation plan and viability analysis

---

## Summary Statistics

### Files by Change Type

| Type | Count | Files |
|------|-------|-------|
| ✅ **New** | 5 | `redis_publisher.py`, 3 test files, `CHANGELOG.md` |
| ⚠️ **Modified** | 10 | Config, health endpoint, 3 coordinator files, 4 test files, `README.md` |
| 🐛 **Bug Fix** | 1 | `config.py` (admin_token) |
| 🔧 **Dependency** | 2 | `pyproject.toml`, `requirements.txt` |

**Total Files:** 18 (5 new, 13 modified)

### Complexity Distribution

| Complexity | Count | Notes |
|------------|-------|-------|
| **LOW** | 11 | Import changes, config fixes, doc updates |
| **MEDIUM** | 7 | DTO replacements, health endpoint refactor, new tests |
| **HIGH** | 0 | No high-complexity changes |

### Risk Profile by File

| File | Risk | Reason |
|------|------|--------|
| `feedback.py` | 🟡 MEDIUM | DTO replacement affects 8 files |
| `app.py` (health) | 🟡 MEDIUM | Response model change (but backward compatible) |
| `queue.py` | 🟢 LOW | Internal implementation, well-tested |
| Test files | 🟢 LOW | Import updates, existing logic valid |
| Config files | 🟢 LOW | Additive changes only |

---

## Change Validation Checklist

After implementing changes, validate:

### Phase 1: Foundation
- [ ] `pip install -e .` succeeds
- [ ] `import market_data_core` works
- [ ] `settings.admin_token` accessible (config bug fixed)

### Phase 2: Feedback Contracts
- [ ] `from market_data_core.telemetry import FeedbackEvent` works
- [ ] `BoundedQueue._emit_feedback()` creates valid Core DTO
- [ ] Existing feedback integration tests pass

### Phase 3: Health Contracts
- [ ] `curl http://localhost:8081/healthz` returns `HealthStatus` JSON
- [ ] Response includes `components` array
- [ ] Degraded state triggers when DB fails

### Phase 4: Contract Tests
- [ ] `pytest tests/unit/test_contract_schemas.py` passes
- [ ] `pytest tests/unit/test_feedback_publisher_contract.py` passes
- [ ] `pytest tests/integration/test_health_contract.py` passes

### Phase 5: Integration
- [ ] All existing tests pass (no regressions)
- [ ] `pytest tests/ -v` shows 100% pass rate
- [ ] Manual testing confirms feedback flow works
- [ ] Documentation updated (CHANGELOG, README)

---

## Rollback Plan

If Core integration fails:

### Immediate Rollback (< 5 minutes)

```powershell
# Revert to v0.3.0
git checkout v0.3.0

# Rebuild environment
.\.venv\Scripts\Activate.ps1
pip install -e .

# Restart services
# (no database changes, so no migration rollback needed)
```

### Selective Rollback (per component)

| Component | Rollback Action |
|-----------|-----------------|
| **Feedback DTOs** | Restore local `FeedbackEvent` from `feedback.py` |
| **Health Endpoint** | Revert to plain dict responses |
| **Dependencies** | Remove `market-data-core` from `pyproject.toml` |
| **Tests** | Revert import paths |

**No data loss risk:** All changes are code-only (no schema migrations)

---

## Cross-Repository Dependencies

### Upstream (Store depends on)
- ✅ **Core v1.1.0** - Must be published before Store v0.4.0

### Downstream (depends on Store)
- ⚠️ **Pipeline** - Will consume Store feedback events (Phase 8.0 Day 3-4)
- ⚠️ **Orchestrator** - Will consume Store health checks (Phase 8.0 Day 1-2)

**Deployment Order:**
1. Core v1.1.0 (contracts published)
2. **Store v0.4.0** ← This implementation
3. Pipeline v0.9.0 (consumes Store feedback)
4. Orchestrator v0.4.0 (consumes Store health)

**Critical:** Store v0.4.0 can be deployed independently; it emits Core-compatible DTOs that old consumers can still parse (backward compatible)

---

**Document Version:** 1.0
**Last Updated:** 2025-10-17
**Related:** `PHASE_8.0_STORE_VIABILITY_ASSESSMENT.md`
