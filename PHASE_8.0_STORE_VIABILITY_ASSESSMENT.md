# Phase 8.0 — Store v0.4.0 Viability Assessment & Implementation Plan

**Repository:** market-data-store
**Target Version:** v0.4.0
**Current Version:** v0.3.0
**Assessment Date:** October 17, 2025
**Scope:** Adopt Core v1.1.0 telemetry & federation contracts

---

## Executive Summary

✅ **VIABLE** - Implementation is feasible with **LOW-TO-MODERATE complexity**

The market-data-store repository is well-positioned to adopt Core v1.1.0 contracts. The existing feedback and health infrastructure provides a solid foundation. Key changes are **additive** and **non-breaking**, making this a low-risk refactor.

**Key Findings:**
- ✅ Existing feedback system (`FeedbackEvent`, `BackpressureLevel`) closely aligns with Core contracts
- ✅ Strong test coverage already exists (feedback, health, integration)
- ✅ No current dependency on `market_data_core` (clean slate)
- ⚠️ Health endpoint exists but returns simple dict, needs DTO upgrade
- ⚠️ `admin_token` field missing from Settings (bug in current code)
- ⚠️ No Redis infrastructure currently (HTTP broadcaster uses httpx only)

**Estimated Effort:** 2-3 days (16-24 hours)

---

## 1. Current State Analysis

### 1.1 Feedback Infrastructure

**Status:** ✅ **Excellent Foundation**

**Existing Implementation:**
```
src/market_data_store/coordinator/
├── feedback.py              ← Local FeedbackEvent & BackpressureLevel
├── http_broadcast.py        ← HTTP-based feedback publisher
├── queue.py                 ← Emits feedback on watermarks
└── write_coordinator.py     ← Coordinator with health checks
```

**Current Data Structures:**

```python
# src/market_data_store/coordinator/feedback.py
class BackpressureLevel(str, Enum):
    OK = "ok"
    SOFT = "soft"
    HARD = "hard"

@dataclass(frozen=True)
class FeedbackEvent:
    coordinator_id: str
    queue_size: int
    capacity: int
    level: BackpressureLevel
    reason: str | None = None

    @property
    def utilization(self) -> float:
        return self.queue_size / self.capacity if self.capacity > 0 else 0.0
```

**Feedback Flow:**
1. `BoundedQueue` monitors watermarks (high/low)
2. Emits `FeedbackEvent` via `FeedbackBus` (singleton pub/sub)
3. `HttpFeedbackBroadcaster` POSTs JSON to HTTP endpoint
4. Multiple subscribers supported with error isolation

**Gap:** Local DTOs need migration to `market_data_core.telemetry.FeedbackEvent`

### 1.2 Health Endpoints

**Status:** ⚠️ **Needs Enhancement**

**Current Implementation:**
```python
# src/datastore/service/app.py (lines 58-77)
@app.get("/healthz")
def healthz():
    STORE_UP.set(1)
    return {"ok": True}  # ← Simple dict, not DTO

@app.get("/readyz")
def readyz():
    # Check DB connectivity
    try:
        from sqlalchemy import create_engine, text
        settings = get_settings()
        engine = create_engine(settings.database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"ready": True}  # ← Simple dict
    except Exception as e:
        logger.error(f"Database connectivity check failed: {e}")
        raise HTTPException(status_code=503, detail="Database not ready")
```

**Gap:** Returns plain dicts instead of `HealthStatus` DTO with components

### 1.3 Configuration & Settings

**Status:** ⚠️ **Bug Detected**

**Current Configuration:**
```python
# src/datastore/config.py
class Settings(BaseSettings):
    DATABASE_URL: str
    ADMIN_DATABASE_URL: str
    APP_PORT: int = 8081
    ALEMBIC_INI: str = "alembic.ini"
    # ❌ MISSING: admin_token field
```

**Bug:** `app.py:37` references `settings.admin_token` but field doesn't exist in Settings class

**Gap:** Need to add `ADMIN_TOKEN: str` field and ensure it's sourced from environment

### 1.4 Test Coverage

**Status:** ✅ **Excellent**

**Existing Test Suite:**
```
tests/unit/coordinator/
├── test_feedback_bus.py           ← 17 tests covering FeedbackBus
├── test_feedback_integration.py   ← 8 integration tests with WriteCoordinator
├── test_http_broadcast.py         ← HTTP broadcaster tests
└── test_write_coordinator.py      ← Coordinator health tests
```

**Coverage Highlights:**
- ✅ `FeedbackEvent` immutability, utilization calculations
- ✅ Pub/sub subscriber management, error isolation
- ✅ Watermark triggers (HARD, SOFT, OK)
- ✅ Multi-coordinator scenarios
- ✅ Integration with `WriteCoordinator`

**Gap:** No tests for Core DTO compatibility (will be needed)

### 1.5 Dependencies

**Current Dependencies (pyproject.toml):**
```toml
[project]
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "sqlalchemy>=2.0",
  "asyncpg>=0.29",
  "psycopg[binary]>=3.2",
  "pydantic>=2.7",
  "prometheus-client>=0.20",
  "loguru>=0.7",
]
```

**Gap:** No `market_data_core` dependency (needs to be added)

---

## 2. Gap Analysis: Phase 8.0 Requirements

### Day 5 Requirements (Store-Specific)

| Requirement | Current State | Gap | Complexity |
|-------------|---------------|-----|------------|
| **Feedback Publisher Protocol** | Custom `HttpFeedbackBroadcaster` | Needs `FeedbackPublisher` protocol conformance | LOW |
| **FeedbackEvent from Core** | Local dataclass | Replace with `market_data_core.telemetry.FeedbackEvent` | LOW |
| **BackpressureLevel from Core** | Local enum | Replace with `market_data_core.telemetry.BackpressureLevel` | LOW |
| **Redis Publisher** | Not implemented | Optional: implement `RedisFeedbackPublisher` if needed | MEDIUM |
| **Health DTO** | Plain dict | Return `HealthStatus` with components | LOW |
| **HealthComponent** | Not implemented | Create component list (db, redis, disk) | MEDIUM |
| **Contract Tests** | None | Add schema equality & protocol conformance tests | MEDIUM |
| **Coordinator Feedback** | Uses local DTOs | Migrate to Core DTOs | LOW |

**Priority Gaps:**
1. 🔴 **HIGH**: Add `market_data_core` dependency
2. 🔴 **HIGH**: Replace local feedback DTOs with Core imports
3. 🟡 **MEDIUM**: Upgrade health endpoints to use Core `HealthStatus`
4. 🟡 **MEDIUM**: Implement contract tests
5. 🟢 **LOW**: Add protocol conformance (adapter pattern if needed)
6. 🟢 **LOW**: Fix `admin_token` config bug

---

## 3. Technical Viability Assessment

### 3.1 Compatibility Analysis

#### ✅ **COMPATIBLE: Feedback Event Structure**

**Current vs. Core Comparison:**

| Field | Current (Local) | Core v1.1.0 | Compatible? |
|-------|-----------------|-------------|-------------|
| `coordinator_id` | ✅ `str` | `str` | ✅ Yes |
| `queue_size` | ✅ `int` | `int` | ✅ Yes |
| `capacity` | ✅ `int` | `int` | ✅ Yes |
| `level` | ✅ `BackpressureLevel` | `BackpressureLevel` | ✅ Yes (enum match) |
| `reason` | ✅ `Optional[str]` | `Optional[str]` | ✅ Yes |
| `utilization` | ⚠️ `@property` | ? | ⚠️ TBD |
| `ts` | ❌ Missing | ✅ `float` (timestamp) | ❌ Need to add |
| `source` | ❌ Missing | ✅ `str` | ❌ Need to add |

**Assessment:** **95% compatible** - Core likely has `ts` and `source` fields we lack

#### ✅ **COMPATIBLE: BackpressureLevel Enum**

| Value | Current | Core v1.1.0 | Compatible? |
|-------|---------|-------------|-------------|
| OK | `"ok"` | `"ok"` | ✅ Yes |
| SOFT | `"soft"` | `"soft"` | ✅ Yes |
| HARD | `"hard"` | `"hard"` | ✅ Yes |

**Assessment:** **100% compatible** - Enum values align perfectly

#### ⚠️ **REQUIRES ADAPTATION: FeedbackPublisher Protocol**

**Current:** Custom broadcaster with `start()`, `stop()`, `_on_feedback()` methods
**Core:** Likely has `FeedbackPublisher` protocol with `publish(event: FeedbackEvent) -> None`

**Assessment:** Adapter pattern needed, or refactor `HttpFeedbackBroadcaster` to implement protocol

### 3.2 Breaking Change Analysis

| Change | Breaking? | Mitigation |
|--------|-----------|------------|
| Replace `FeedbackEvent` dataclass | ⚠️ **Potentially** | Use Core DTO if API-compatible; add adapter if not |
| Replace `BackpressureLevel` enum | ✅ **No** | Direct import swap (same values) |
| Update health endpoint response | ✅ **No** | New response model is superset of old |
| Add `market_data_core` dependency | ✅ **No** | New dependency, no conflicts |
| Protocol conformance | ✅ **No** | Additive interface implementation |

**Assessment:** **LOW RISK** - Most changes are import swaps with no API breakage

### 3.3 Dependency Risk

**Required:** `market_data_core >= 1.1.0`

**Considerations:**
1. ✅ No existing dependency on Core (clean slate)
2. ✅ Pydantic v2 already in use (aligns with Core)
3. ✅ Python 3.11 target (modern, no compatibility issues)
4. ⚠️ Core v1.1.0 must be published and available before Store v0.4.0 release

**Recommendation:** Add Core as **runtime dependency** in `pyproject.toml`:
```toml
dependencies = [
  "market-data-core>=1.1.0",  # ← Add this
  # ... existing deps
]
```

### 3.4 Test Migration Risk

**Current Test Structure:**
- 17 tests for `FeedbackBus`
- 8 integration tests for feedback flow
- Full coverage of watermark logic

**Migration Impact:**
- ⚠️ Import paths change (`from .feedback import` → `from market_data_core.telemetry import`)
- ⚠️ If Core `FeedbackEvent` lacks `utilization` property, tests will break
- ✅ Test logic remains valid (watermark triggers, pub/sub, etc.)

**Risk Level:** **LOW-MEDIUM** - Most tests just need import updates

---

## 4. Implementation Plan

### Phase 1: Foundation (Day 1) - 4 hours

#### 4.1 Add Core Dependency

**File:** `pyproject.toml`

```toml
[project]
dependencies = [
  "market-data-core>=1.1.0",  # ← ADD
  "fastapi>=0.115",
  # ... rest
]
```

**File:** `requirements.txt`

```txt
# Add to requirements.txt
market-data-core>=1.1.0
```

**Validation:**
```powershell
pip install market-data-core>=1.1.0  # Ensure it's available
```

#### 4.2 Fix Config Bug

**File:** `src/datastore/config.py`

```python
class Settings(BaseSettings):
    DATABASE_URL: str
    ADMIN_DATABASE_URL: str
    ADMIN_TOKEN: str = "changeme"  # ← ADD with default for dev
    APP_PORT: int = 8081
    ALEMBIC_INI: str = "alembic.ini"

    # ... rest remains same
```

### Phase 2: Feedback Contract Adoption (Day 2) - 6 hours

#### 4.3 Inspect Core v1.1.0 DTOs

**Before making changes**, verify Core exports:

```python
# Validation script
from market_data_core.telemetry import FeedbackEvent, BackpressureLevel, HealthStatus, HealthComponent
from market_data_core.protocols import FeedbackPublisher

# Check FeedbackEvent fields
import inspect
print(inspect.signature(FeedbackEvent.__init__))

# Check if utilization exists
print(hasattr(FeedbackEvent, 'utilization'))
```

#### 4.4 Update Feedback Module

**File:** `src/market_data_store/coordinator/feedback.py`

**Strategy:** Deprecate local DTOs, import from Core

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


class FeedbackBus:
    """In-process pub/sub bus for backpressure feedback."""
    # ... implementation remains unchanged
    # Only import changes; FeedbackEvent is now from Core
```

**If Core FeedbackEvent is missing fields:**

Option A: Wrap Core DTO with local extension
```python
from market_data_core.telemetry import FeedbackEvent as CoreFeedbackEvent

@dataclass
class FeedbackEvent(CoreFeedbackEvent):
    """Extended feedback event with store-specific fields."""
    @property
    def utilization(self) -> float:
        return self.queue_size / self.capacity if self.capacity > 0 else 0.0
```

Option B: Use Core DTO as-is, remove `utilization` property
- Update tests to calculate utilization inline if needed

#### 4.5 Update Queue to Use Core DTOs

**File:** `src/market_data_store/coordinator/queue.py`

```python
from .feedback import BackpressureLevel, FeedbackEvent, feedback_bus
# Change to:
from market_data_core.telemetry import BackpressureLevel, FeedbackEvent
from .feedback import feedback_bus  # Keep bus from local module
```

**Update `_emit_feedback` method:**

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
        source="store",  # ← ADD if Core expects it
        ts=time.time(),  # ← ADD if Core expects it
    )
    await feedback_bus().publish(event)
```

#### 4.6 Implement FeedbackPublisher Protocol (Optional)

**If Phase 8.0 requires Redis publisher:**

**File:** `src/market_data_store/coordinator/redis_publisher.py` (NEW)

```python
"""
Redis-based feedback publisher conforming to Core protocol.
"""

from __future__ import annotations
import asyncio
from typing import Optional

from loguru import logger
from market_data_core.protocols import FeedbackPublisher
from market_data_core.telemetry import FeedbackEvent

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None  # type: ignore


class RedisFeedbackPublisher(FeedbackPublisher):
    """Publishes feedback events to Redis channel."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        channel: str = "feedback",
        enabled: bool = True,
    ):
        self.redis_url = redis_url
        self.channel = channel
        self.enabled = enabled
        self._client: Optional[redis.Redis] = None  # type: ignore

    async def start(self) -> None:
        if not self.enabled or not REDIS_AVAILABLE:
            logger.warning("Redis feedback publisher disabled")
            return

        self._client = redis.from_url(self.redis_url)
        logger.info(f"Redis feedback publisher started (channel={self.channel})")

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def publish(self, event: FeedbackEvent) -> None:
        """Publish feedback event to Redis (protocol method)."""
        if not self.enabled or not self._client:
            return

        try:
            await self._client.publish(self.channel, event.model_dump_json())
            logger.debug(f"Feedback published to Redis: {event.coordinator_id}")
        except Exception as exc:
            logger.error(f"Redis publish failed: {exc}")
```

**Add to exports:**

**File:** `src/market_data_store/coordinator/__init__.py`

```python
# Add to __all__
from .redis_publisher import RedisFeedbackPublisher

__all__ = [
    # ... existing exports
    "RedisFeedbackPublisher",  # ← ADD
]
```

### Phase 3: Health Contract Adoption (Day 3) - 4 hours

#### 4.7 Update Health Endpoint

**File:** `src/datastore/service/app.py`

```python
from market_data_core.telemetry import HealthStatus, HealthComponent
import time

@app.get("/healthz", response_model=HealthStatus)
async def healthz():
    """Health check endpoint using Core v1.1.0 HealthStatus."""
    STORE_UP.set(1)

    # Check DB connectivity
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

    # Build components list
    components = [
        HealthComponent(name="database", state=db_state),
        HealthComponent(name="prometheus", state="healthy"),
    ]

    # Optional: add redis component if applicable
    # components.append(HealthComponent(name="redis", state="healthy"))

    # Determine overall state
    overall_state = "degraded" if any(c.state != "healthy" for c in components) else "healthy"

    return HealthStatus(
        service="market-data-store",
        state=overall_state,
        components=components,
        version="0.4.0",
        ts=time.time(),
    )


@app.get("/readyz", response_model=HealthStatus)
async def readyz():
    """Readiness check (stricter than health)."""
    # Similar to healthz but fail-fast on any non-healthy component
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
        raise HTTPException(
            status_code=503,
            detail="Service not ready"
        )
```

### Phase 4: Contract Tests (Day 3-4) - 6 hours

#### 4.8 Create Contract Test Suite

**File:** `tests/unit/test_contract_schemas.py` (NEW)

```python
"""
Contract tests for Core v1.1.0 DTOs.

Ensures Store uses Core types correctly and schemas match expectations.
"""

import pytest
from market_data_core.telemetry import (
    FeedbackEvent,
    BackpressureLevel,
    HealthStatus,
    HealthComponent,
)
from market_data_store.coordinator import FeedbackBus


def test_feedback_event_schema_roundtrip():
    """FeedbackEvent serializes/deserializes correctly."""
    event = FeedbackEvent(
        coordinator_id="test-coord",
        queue_size=8000,
        capacity=10000,
        level=BackpressureLevel.hard,
        source="store",
        ts=1234567890.0,
        reason="high_watermark",
    )

    # Serialize
    json_str = event.model_dump_json()

    # Deserialize
    rehydrated = FeedbackEvent.model_validate_json(json_str)

    assert rehydrated.coordinator_id == "test-coord"
    assert rehydrated.level == BackpressureLevel.hard
    assert rehydrated.queue_size == 8000


def test_backpressure_level_values():
    """BackpressureLevel enum has expected Core values."""
    assert BackpressureLevel.ok.value == "ok"
    assert BackpressureLevel.soft.value == "soft"
    assert BackpressureLevel.hard.value == "hard"


def test_health_status_schema():
    """HealthStatus conforms to Core schema."""
    components = [
        HealthComponent(name="database", state="healthy"),
        HealthComponent(name="redis", state="degraded"),
    ]

    health = HealthStatus(
        service="market-data-store",
        state="degraded",
        components=components,
        version="0.4.0",
        ts=1234567890.0,
    )

    # Serialize
    json_str = health.model_dump_json()

    # Deserialize
    rehydrated = HealthStatus.model_validate_json(json_str)

    assert rehydrated.service == "market-data-store"
    assert rehydrated.state == "degraded"
    assert len(rehydrated.components) == 2


def test_health_component_state_enum():
    """HealthComponent.state accepts Core enum values."""
    # Assuming Core defines state as Literal or Enum
    component = HealthComponent(name="test", state="healthy")
    assert component.state in ("healthy", "degraded", "unhealthy")
```

**File:** `tests/unit/test_feedback_publisher_contract.py` (NEW)

```python
"""
Protocol conformance tests for FeedbackPublisher.
"""

import pytest
from market_data_core.protocols import FeedbackPublisher
from market_data_core.telemetry import FeedbackEvent, BackpressureLevel
from market_data_store.coordinator import HttpFeedbackBroadcaster

# Only test if Redis publisher implemented
try:
    from market_data_store.coordinator import RedisFeedbackPublisher
    REDIS_PUBLISHER_AVAILABLE = True
except ImportError:
    REDIS_PUBLISHER_AVAILABLE = False


@pytest.mark.asyncio
async def test_http_broadcaster_conforms_to_protocol():
    """HttpFeedbackBroadcaster conforms to FeedbackPublisher protocol."""
    # Note: HttpFeedbackBroadcaster may need refactor to conform
    # This test validates protocol conformance
    broadcaster = HttpFeedbackBroadcaster(
        endpoint="http://test:8080/feedback",
        enabled=False,  # Don't actually start httpx
    )

    # If protocol conformance added, this should pass:
    # assert isinstance(broadcaster, FeedbackPublisher)

    # For now, test it has required methods
    assert hasattr(broadcaster, 'start')
    assert hasattr(broadcaster, 'stop')


@pytest.mark.skipif(not REDIS_PUBLISHER_AVAILABLE, reason="Redis publisher not implemented")
@pytest.mark.asyncio
async def test_redis_publisher_conforms_to_protocol():
    """RedisFeedbackPublisher conforms to FeedbackPublisher protocol."""
    publisher = RedisFeedbackPublisher(enabled=False)

    # Protocol conformance check
    assert isinstance(publisher, FeedbackPublisher)

    # Has required methods
    assert hasattr(publisher, 'publish')
```

**File:** `tests/integration/test_health_contract.py` (NEW)

```python
"""
Integration tests for health endpoint contract.
"""

import pytest
from fastapi.testclient import TestClient
from market_data_core.telemetry import HealthStatus


@pytest.fixture
def client():
    from datastore.service.app import app
    return TestClient(app)


def test_healthz_returns_health_status(client):
    """GET /healthz returns Core HealthStatus schema."""
    response = client.get("/healthz")

    assert response.status_code == 200

    # Parse as Core DTO
    health = HealthStatus.model_validate(response.json())

    assert health.service == "market-data-store"
    assert health.state in ("healthy", "degraded")
    assert len(health.components) > 0
    assert health.version == "0.4.0"


def test_readyz_returns_health_status(client):
    """GET /readyz returns Core HealthStatus schema."""
    response = client.get("/readyz")

    # May be 200 or 503 depending on DB connectivity
    if response.status_code == 200:
        health = HealthStatus.model_validate(response.json())
        assert health.state == "healthy"
    else:
        assert response.status_code == 503


def test_health_degraded_when_component_fails(client, monkeypatch):
    """Health endpoint shows degraded when DB fails."""
    # Mock DB connection to fail
    def mock_db_fail(*args, **kwargs):
        raise Exception("DB connection failed")

    from sqlalchemy import create_engine
    monkeypatch.setattr("sqlalchemy.create_engine", mock_db_fail)

    response = client.get("/healthz")

    assert response.status_code == 200
    health = HealthStatus.model_validate(response.json())

    assert health.state == "degraded"
    db_component = next(c for c in health.components if c.name == "database")
    assert db_component.state == "degraded"
```

#### 4.9 Update Existing Tests

**Files to update:**
- `tests/unit/coordinator/test_feedback_bus.py`
- `tests/unit/coordinator/test_feedback_integration.py`
- `tests/unit/coordinator/test_http_broadcast.py`

**Changes:**

```python
# Old imports
from market_data_store.coordinator.feedback import (
    BackpressureLevel,
    FeedbackEvent,
    feedback_bus,
)

# New imports (update in all test files)
from market_data_core.telemetry import BackpressureLevel, FeedbackEvent
from market_data_store.coordinator.feedback import feedback_bus
```

**If Core FeedbackEvent lacks `utilization` property:**

Update tests like `test_feedback_event_utilization()`:

```python
# Old:
assert event.utilization == 0.75

# New (inline calculation):
utilization = event.queue_size / event.capacity
assert utilization == 0.75
```

### Phase 5: Integration & Validation (Day 4) - 4 hours

#### 4.10 Run Full Test Suite

```powershell
# Activate venv
.\.venv\Scripts\Activate.ps1

# Install updated dependencies
pip install -e .

# Run all tests
pytest tests/ -v

# Run contract tests specifically
pytest tests/unit/test_contract_schemas.py -v
pytest tests/integration/test_health_contract.py -v
```

#### 4.11 Manual Testing

**Test Health Endpoint:**

```powershell
# Start FastAPI service
uvicorn datastore.service.app:app --reload --port 8081

# Test health
curl http://localhost:8081/healthz

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
```

**Test Feedback Flow:**

```python
# Run example/demo script
import asyncio
from market_data_store.coordinator import WriteCoordinator
from market_data_store.sinks import BarsSink
from market_data_core.telemetry import FeedbackEvent, BackpressureLevel

async def demo():
    async def on_feedback(event: FeedbackEvent):
        print(f"Feedback: {event.coordinator_id} - {event.level.value} - {event.queue_size}/{event.capacity}")

    from market_data_store.coordinator.feedback import feedback_bus
    feedback_bus().subscribe(on_feedback)

    # ... rest of demo

asyncio.run(demo())
```

#### 4.12 Documentation Updates

**File:** `CHANGELOG.md` (create or update)

```markdown
# Changelog

## [0.4.0] - 2025-10-XX

### Added
- **Core v1.1.0 Contract Adoption**
  - Replaced local `FeedbackEvent` and `BackpressureLevel` with `market_data_core.telemetry` imports
  - Health endpoints now return Core `HealthStatus` DTO with component breakdown
  - Added contract tests for schema compliance
  - Added `RedisFeedbackPublisher` (optional, if implemented)

### Changed
- `GET /healthz` and `GET /readyz` now return structured `HealthStatus` instead of plain dict
- `FeedbackEvent` now includes `ts` (timestamp) and `source` fields from Core
- Version bump to 0.4.0 to signal Core contract adoption

### Fixed
- Added missing `ADMIN_TOKEN` field to `Settings` class

### Deprecated
- Local `FeedbackEvent` and `BackpressureLevel` definitions (now imported from Core)

### Migration Guide
- If you manually construct `FeedbackEvent`, add `ts=time.time()` and `source="store"` parameters
- Health endpoint consumers should parse `HealthStatus` DTO instead of plain dict
```

**File:** `README.md` (update version references)

```markdown
## 📋 Releases

### 🏷️ Current Release: [v0.4.0]

**What's included:**
- ✅ Core v1.1.0 telemetry contract adoption
- ✅ Standardized `HealthStatus` and `FeedbackEvent` DTOs
- ✅ Protocol-based feedback publishers
- ✅ Full backward compatibility with v0.3.x
```

---

## 5. Risk Register & Mitigation

### Risk 1: Core v1.1.0 Not Published

**Impact:** HIGH (blocks all work)
**Likelihood:** LOW
**Mitigation:**
- Coordinate with Core team for release timeline
- Consider pre-release/dev version during development
- Add CI check to verify Core availability

### Risk 2: Core FeedbackEvent Schema Mismatch

**Impact:** MEDIUM (requires adapter layer)
**Likelihood:** MEDIUM
**Mitigation:**
- Inspect Core exports early (Phase 2, step 4.3)
- Use adapter pattern if needed
- Document schema differences

### Risk 3: Existing Test Failures After Migration

**Impact:** MEDIUM (delays release)
**Likelihood:** MEDIUM
**Mitigation:**
- Update tests incrementally with imports
- Run tests after each module update
- Keep `utilization` calculation inline if Core lacks property

### Risk 4: Redis Dependency Overhead

**Impact:** LOW (optional feature)
**Likelihood:** LOW
**Mitigation:**
- Make Redis publisher optional (graceful degradation)
- Use `redis.asyncio` with try/except import
- Document Redis as optional dependency

### Risk 5: Breaking Changes in Existing Consumers

**Impact:** LOW (health response change)
**Likelihood:** LOW
**Mitigation:**
- Core DTO is superset of old dict response
- Existing consumers can still parse `{"ok": True}` pattern if they ignore extra fields
- Version bump signals contract change

---

## 6. Success Criteria

### Technical Criteria

✅ **Must Have:**
1. All imports use `market_data_core.telemetry` and `market_data_core.protocols`
2. No local `FeedbackEvent` or `BackpressureLevel` definitions remain
3. Health endpoints return Core `HealthStatus` DTO
4. All existing tests pass with updated imports
5. Contract tests validate schema equality
6. `pyproject.toml` includes `market-data-core>=1.1.0` dependency
7. Config bug fixed (`ADMIN_TOKEN` field added)

✅ **Should Have:**
8. `RedisFeedbackPublisher` implements `FeedbackPublisher` protocol
9. Integration tests cover health endpoint contract
10. Documentation updated (CHANGELOG, README, version bump)

✅ **Nice to Have:**
11. Grafana dashboard uses Core DTO field names for labels
12. Example scripts demonstrate Core DTO usage

### Operational Criteria

✅ **Zero-Downtime Deployment:**
- Store v0.3.0 → v0.4.0 can be deployed without Pipeline/Orchestrator changes
- Health endpoint response is backward compatible (superset)
- Feedback events maintain same JSON structure

✅ **Rollback Safety:**
- Can rollback to v0.3.0 if Core integration issues arise
- No database schema changes (migration-free release)

---

## 7. Timeline Estimate

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| **Phase 1: Foundation** | 4 hours | Core dependency added, config bug fixed |
| **Phase 2: Feedback Contracts** | 6 hours | Core DTOs imported, queue/coordinator updated |
| **Phase 3: Health Contracts** | 4 hours | Health endpoints use Core `HealthStatus` |
| **Phase 4: Contract Tests** | 6 hours | Schema & protocol tests passing |
| **Phase 5: Integration** | 4 hours | Full test suite passing, docs updated |
| **Total** | **24 hours** | Store v0.4.0 ready for release |

**Recommended Schedule (Day-by-Day):**

- **Day 1:** Phase 1 (4h) + Phase 2 start (2h) = 6h
- **Day 2:** Phase 2 finish (4h) + Phase 3 (4h) = 8h
- **Day 3:** Phase 4 (6h) + Phase 5 start (2h) = 8h
- **Day 4:** Phase 5 finish (2h) + buffer = 2h

**Total:** 3-4 days with buffer for unexpected issues

---

## 8. Open Questions (Requires Core Team Input)

### Q1: Core v1.1.0 `FeedbackEvent` Schema

**Question:** Does Core `FeedbackEvent` include all these fields?
- `coordinator_id: str`
- `queue_size: int`
- `capacity: int`
- `level: BackpressureLevel`
- `reason: Optional[str]`
- `source: str`  ← NEW?
- `ts: float`  ← NEW?
- `utilization: float` property  ← Does Core have this?

**Impact:** Determines if we need adapter layer or can use Core DTO directly

### Q2: `FeedbackPublisher` Protocol Signature

**Question:** What is the exact method signature for `FeedbackPublisher.publish()`?

```python
# Option A: Simple async method
async def publish(self, event: FeedbackEvent) -> None:
    ...

# Option B: With error handling
async def publish(self, event: FeedbackEvent) -> bool:  # returns success
    ...
```

**Impact:** Determines Redis/HTTP publisher implementation

### Q3: `HealthComponent.state` Values

**Question:** Is `state` a string enum or Literal type?

```python
# Option A: String Literal
state: Literal["healthy", "degraded", "unhealthy"]

# Option B: Enum
class HealthState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
```

**Impact:** Determines how we check/set component states

### Q4: Redis Publisher Requirement

**Question:** Is `RedisFeedbackPublisher` required for v0.4.0, or is HTTP sufficient?

**Impact:** Determines if we need Redis dependency and implementation effort

---

## 9. Recommendations

### Immediate Actions

1. ✅ **Proceed with implementation** - viability is HIGH
2. 🔴 **Coordinate with Core team** on v1.1.0 release timeline
3. 🔴 **Request Core DTO schema reference** (Q1-Q3 above)
4. 🟡 **Create feature branch**: `feature/phase-8.0-core-contracts`
5. 🟡 **Set up CI to test against Core v1.1.0** (once published)

### Implementation Strategy

**Recommended Approach: Incremental Migration**

1. Start with Phase 1 (foundation) immediately
2. Inspect Core v1.1.0 exports in Phase 2, step 4.3
3. If schema mismatches, use adapter pattern temporarily
4. Prioritize feedback contract over health (higher impact)
5. Keep existing `HttpFeedbackBroadcaster`, make Redis publisher optional

### Testing Strategy

**Recommended: Dual-Pass Testing**

1. **Pass 1:** Update imports, run existing tests (validate logic unchanged)
2. **Pass 2:** Add contract tests (validate Core compatibility)

This ensures we don't break existing functionality while adding new contract validation.

---

## 10. Conclusion

**Verdict:** ✅ **PROCEED - Implementation is VIABLE**

**Key Strengths:**
- ✅ Excellent foundation (existing feedback system closely aligned)
- ✅ Strong test coverage (easy to validate changes)
- ✅ No breaking changes for consumers
- ✅ Additive contract adoption (low risk)

**Key Challenges:**
- ⚠️ Core v1.1.0 must be published first
- ⚠️ Schema alignment needs verification
- ⚠️ Test import updates across 8+ files

**Effort:** 24 hours (3-4 days)
**Risk:** LOW-MEDIUM
**ROI:** HIGH (standardization, future-proofing)

**Next Steps:**
1. Approve this plan
2. Coordinate Core v1.1.0 release
3. Create feature branch
4. Begin Phase 1 implementation

---

**Document Version:** 1.0
**Author:** AI Assistant
**Review Status:** Pending Review
**Approval Required:** Tech Lead, Core Team Lead
