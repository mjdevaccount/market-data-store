# Changelog

All notable changes to the market-data-store project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2025-10-17

### Added
- **Core v1.1.0 Contract Adoption** - Phase 8.0 implementation
  - Extended `FeedbackEvent` from `market_data_core.telemetry.FeedbackEvent` with Store-specific fields:
    - `reason`: Optional context string for debugging (e.g., "queue_recovered", "circuit_open")
    - `utilization`: Computed property for queue usage percentage (0.0-1.0)
  - `FeedbackEvent.create()` factory method that auto-fills `ts` (timestamp) and `source` ("store")
  - Health endpoints (`/healthz`, `/readyz`) now return Core `HealthStatus` DTO with component breakdown
  - Contract tests for schema compliance (`test_contract_schemas.py`)
  - Health endpoint integration tests (`test_health_contract.py`)
  - Missing `ADMIN_TOKEN` field to `Settings` class (bug fix)

### Changed
- **Breaking (Minor):** `FeedbackEvent` now inherits from Core DTO instead of standalone dataclass
  - *Migration:* Use `FeedbackEvent.create()` factory or provide `ts` and `source` parameters
  - *Compatibility:* Store events remain parseable by Core-only consumers (extra fields ignored)
- `BackpressureLevel` imported directly from `market_data_core.telemetry` (no local definition)
- Health endpoints return structured `HealthStatus` DTO instead of plain dict
  - *Backward Compatible:* Old consumers can parse response (extra fields ignored)
- Version bump from 0.3.0 to 0.4.0
- FastAPI app version updated to "0.4.0"

### Fixed
- Added missing `ADMIN_TOKEN` field to `Settings` class
  - Previously caused AttributeError when accessing `settings.admin_token`
  - Now defaults to "changeme" for development (override in production via env var)

### Deprecated
- Direct construction of `FeedbackEvent` without `ts` and `source` fields
  - Use `FeedbackEvent.create()` factory method instead

### Migration Guide

#### For Store Developers
```python
# Old (v0.3.0)
from market_data_store.coordinator import BackpressureLevel, FeedbackEvent
event = FeedbackEvent(
    coordinator_id="test",
    queue_size=50,
    capacity=100,
    level=BackpressureLevel.HARD,
    reason="high_watermark",
)

# New (v0.4.0) - Recommended
from market_data_core.telemetry import BackpressureLevel
from market_data_store.coordinator import FeedbackEvent
event = FeedbackEvent.create(
    coordinator_id="test",
    queue_size=50,
    capacity=100,
    level=BackpressureLevel.hard,  # Note: lowercase
    reason="high_watermark",
)

# New (v0.4.0) - Direct construction (advanced)
import time
event = FeedbackEvent(
    coordinator_id="test",
    queue_size=50,
    capacity=100,
    level=BackpressureLevel.hard,
    source="store",
    ts=time.time(),
    reason="high_watermark",
)
```

#### For Health Endpoint Consumers
```python
# Old (v0.3.0)
response = requests.get("http://store:8081/healthz")
data = response.json()
# {"ok": True}

# New (v0.4.0)
response = requests.get("http://store:8081/healthz")
health = HealthStatus.model_validate(response.json())
# {
#   "service": "market-data-store",
#   "state": "healthy",
#   "components": [
#     {"name": "database", "state": "healthy"},
#     {"name": "prometheus", "state": "healthy"}
#   ],
#   "version": "0.4.0",
#   "ts": 1697654400.0
# }

# Backward Compatible - old code still works:
data = response.json()  # Extra fields ignored
```

### Technical Details

#### Adapter Pattern
Store v0.4.0 uses the adapter pattern to extend Core v1.1.0 contracts while preserving Store-specific domain extensions. This maintains:
- **Upward compatibility:** Store events conform to Core schema (is-a relationship)
- **Downward extension:** Store retains `reason` and `utilization` for debugging and monitoring
- **Forward compatibility:** Core-compatible consumers parse Store events without modification

#### Contract Compliance
- `FeedbackEvent` extends `market_data_core.telemetry.FeedbackEvent` (validated by `isinstance()` checks)
- `BackpressureLevel` enum values match Core exactly (`ok`, `soft`, `hard`)
- `HealthStatus` and `HealthComponent` use Core DTOs directly (100% compatible)
- JSON serialization includes all Core fields + Store extensions

### Dependencies
- **Added:** `market-data-core @ git+https://github.com/mjdevaccount/market-data-core.git@v1.1.0`

### Testing
- All existing tests pass with updated imports
- Contract tests validate Core schema compatibility
- Health endpoint integration tests ensure DTO compliance
- Adapter pattern tested via `isinstance()` and JSON roundtrip

---

## [0.3.0] - 2025-XX-XX
*(Previous releases documented below)*

### Added
- Write coordinator with backpressure feedback (Phase 4.2)
- Async sinks layer for high-throughput ingestion
- HTTP feedback broadcaster
- Dead Letter Queue (DLQ) for error handling
- Prometheus metrics integration

---

## [0.2.0] - 2025-XX-XX

### Added
- MDS client library (sync/async APIs)
- RLS (Row Level Security) support
- TimescaleDB policies and aggregates
- Comprehensive CLI (`mds` command)

---

## [0.1.0] - 2025-XX-XX

### Added
- Initial release
- FastAPI control-plane endpoints
- Alembic migrations
- Basic health checks
- Admin token authentication

---

**Links:**
- [Core v1.1.0 Release](https://github.com/mjdevaccount/market-data-core/releases/tag/v1.1.0)
- [Phase 8.0 Implementation Plan](PHASE_8.0_STORE_REVISED_ASSESSMENT.md)
