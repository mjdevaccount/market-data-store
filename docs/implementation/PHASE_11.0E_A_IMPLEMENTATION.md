# Phase 11.0E-A: Schema Registry Integration - Store Side

**Repository:** `market-data-store`
**Implementation Date:** October 18, 2025
**Status:** ✅ COMPLETE
**Registry URL:** https://schema-registry-service.fly.dev

---

## 📋 Executive Summary

Store has successfully integrated with the live Schema Registry Service to fetch and validate schemas in CI/CD. This ensures Store's extended models remain compatible with Core schemas as they evolve from v1 to v2.

---

## ✅ Deliverables

| Component | Status | Details |
|-----------|--------|---------|
| **Schema Fetch Script** | ✅ Complete | `scripts/fetch_registry_schemas.py` |
| **Contract Tests** | ✅ 10/10 Passing | `tests/contracts/test_registry_schemas.py` |
| **CI Workflow** | ✅ Complete | `.github/workflows/registry_contracts.yml` |
| **SDK Integration** | ✅ Complete | `core-registry-client` installed |
| **Dependencies Updated** | ✅ Complete | `pyproject.toml` with SDK |
| **Documentation** | ✅ Complete | This file |

---

## 🎯 What We Accomplished

### 1. Schema Fetch Script ✅

Created `scripts/fetch_registry_schemas.py` to:
- Connect to live Registry at https://schema-registry-service.fly.dev
- Fetch critical schemas (`FeedbackEvent`, `HealthStatus`, `HealthComponent`)
- Support both v1 (stable) and v2 (preview) tracks
- Save schemas locally for testing
- Generate metadata JSON with fetch timestamp

**Usage:**
```bash
python scripts/fetch_registry_schemas.py --track v1 --output tests/fixtures/schemas
```

**Output:**
```
📡 Connecting to Registry: https://schema-registry-service.fly.dev
🎯 Track: v1
📂 Output: tests\fixtures\schemas

✅ Registry healthy: 2 tracks available
📋 19 schemas available in v1 track

  ✅ telemetry.FeedbackEvent @ v1.2.7-timezone-fix
  ✅ telemetry.HealthStatus @ v1.2.7-timezone-fix
  ✅ telemetry.HealthComponent @ v1.2.7-timezone-fix

📊 Results: 3 fetched, 0 failed
✅ Saved metadata to tests\fixtures\schemas\_metadata.json
```

### 2. Contract Tests ✅

Created `tests/contracts/test_registry_schemas.py` with 10 comprehensive tests:

1. ✅ `test_registry_schemas_available` - Verify critical schemas fetched
2. ✅ `test_metadata_present` - Verify metadata exists
3. ✅ `test_feedback_event_v1_compatible` - Store FeedbackEvent validates against Registry v1
4. ✅ `test_feedback_event_core_fields` - Store includes all Core required fields
5. ✅ `test_backpressure_level_enum_stable` - Enum values match Registry schema
6. ✅ `test_store_extension_backward_compatible` - Core can deserialize Store events
7-9. ✅ `test_feedback_event_all_levels_valid[ok/soft/hard]` - All levels validate
10. ✅ `test_utilization_property` - Store's computed property works

**Test Results:**
```bash
pytest tests/contracts/test_registry_schemas.py -v
```
```
10 passed in 1.43s ✅
```

### 3. CI Integration ✅

Created `.github/workflows/registry_contracts.yml` with:
- **Dual-track testing**: v1 (required) + v2 (continue-on-error)
- **Nightly runs**: Catch schema drift automatically
- **Fail-open**: Registry unavailability doesn't block builds
- **Artifact upload**: Schemas preserved for 30 days

**Workflow Matrix:**
| Track | Status | Behavior |
|-------|--------|----------|
| v1 | Required | Fail if incompatible |
| v2 | Preview | Allow failure during migration |

### 4. Dependency Management ✅

Updated `pyproject.toml`:
```toml
[project.optional-dependencies]
dev = [
  "core-registry-client @ git+https://github.com/mjdevaccount/schema-registry-service.git#subdirectory=client_sdk",
  "jsonschema>=4.0",
]
```

Installed SDK:
```bash
pip install git+https://github.com/mjdevaccount/schema-registry-service.git#subdirectory=client_sdk
```

---

## 🔧 Technical Details

### Schema Validation Flow

```
1. CI triggered (PR/push/nightly)
   │
2. Install core-registry-client SDK
   │
3. Fetch schemas from Registry
   │  └─> GET https://schema-registry-service.fly.dev/schemas/{track}/{name}
   │
4. Save schemas locally
   │  └─> tests/fixtures/schemas/{name}.json
   │
5. Run contract tests
   │  └─> pytest tests/contracts/
   │
6. Validate Store models against Registry schemas
   │  └─> jsonschema validation
   │
7. Upload schemas as artifacts (30-day retention)
```

### Core Extended Model: FeedbackEvent

Store extends Core's `FeedbackEvent` with additional metadata:

```python
from market_data_core.telemetry import FeedbackEvent as CoreFeedback

class FeedbackEvent(CoreFeedback):
    """Store's extended FeedbackEvent with additional metadata."""
    reason: str | None = Field(default=None, description="Store-specific context")

    @property
    def utilization(self) -> float:
        """Computed queue utilization (Store extension)."""
        return self.queue_size / self.capacity if self.capacity > 0 else 0.0
```

**Backward Compatibility:**
- Store → Core: ✅ Core can deserialize Store events (ignores `reason`)
- Core → Store: ✅ Store can deserialize Core events (`reason` defaults to None)
- JSON Schema: ✅ Store events validate against Registry v1 schema

---

## 📊 Validation Results

### Local Testing
```bash
# Fetch schemas
python scripts/fetch_registry_schemas.py --track v1 --output tests/fixtures/schemas
# ✅ 3 schemas fetched (FeedbackEvent, HealthStatus, HealthComponent)

# Run tests
pytest tests/contracts/ -v
# ✅ 10/10 tests passing
```

### Registry Health
```bash
curl https://schema-registry-service.fly.dev/health
```
```json
{
  "status": "healthy",
  "timestamp": "2025-10-18T19:34:05.648589Z",
  "checks": {},
  "version": "0.1.0"
}
```

### Schema Metadata
```json
{
  "registry_url": "https://schema-registry-service.fly.dev",
  "track": "v1",
  "fetched_at": "2025-10-18T19:36:14.558446+00:00",
  "schemas_fetched": 3,
  "schemas_failed": 0,
  "failed_schemas": []
}
```

---

## 🚀 Next Steps

### Immediate (Completed)
- [x] Schema fetch script working
- [x] Contract tests passing (10/10)
- [x] CI workflow configured
- [x] SDK dependency added
- [x] Documentation complete

### Future (Phase 11.0E-B: Pipeline, Phase 11.0E-C: Orchestrator)
- [ ] Pipeline integrates with Registry (consumes FeedbackEvent, RateAdjustment schemas)
- [ ] Orchestrator metrics dashboard (schema count, last sync)
- [ ] Runtime schema validation (optional, fail-open)
- [ ] v2 migration when Core stabilizes

### Optional Enhancements
- [ ] Schema caching at runtime (~/.cache/core_registry_client/)
- [ ] Runtime validation middleware (FastAPI)
- [ ] Schema negotiation (prefer v2, fallback v1)
- [ ] Prometheus metrics (schema_fetch_total, schema_validation_total)

---

## 📦 Files Changed

### Created (6)
1. `scripts/fetch_registry_schemas.py` - Schema fetch CLI
2. `tests/contracts/__init__.py` - Contract tests package
3. `tests/contracts/test_registry_schemas.py` - 10 validation tests
4. `.github/workflows/registry_contracts.yml` - CI workflow
5. `tests/fixtures/schemas/*.json` - Fetched v1 schemas (3 files)
6. `PHASE_11.0E_A_IMPLEMENTATION.md` - This file

### Modified (2)
1. `pyproject.toml` - Added `core-registry-client` to dev dependencies
2. `docs/planning/phase_11_0/REGISTRY_INTEGRATION_DEFERRED.md` - Updated status (deferred → implementing)

---

## 🎯 Exit Criteria

All exit criteria for Phase 11.0E-A met:

- ✅ Store pulls v1 schemas successfully from live Registry
- ✅ Contract tests validate Store's FeedbackEvent against Registry
- ✅ CI workflow runs on PR/push/nightly
- ✅ Dual-track support (v1 required, v2 preview)
- ✅ Fail-open behavior (Registry down doesn't block builds)
- ✅ Documentation complete

---

## 📞 Support

**Registry Service:** https://schema-registry-service.fly.dev
**SDK Source:** https://github.com/mjdevaccount/schema-registry-service/tree/main/client_sdk
**Store Repo:** https://github.com/mjdevaccount/market-data-store

**Questions?** Check `.github/workflows/registry_contracts.yml` for workflow details or `scripts/fetch_registry_schemas.py --help` for CLI usage.

---

**Phase 11.0E-A Status:** ✅ COMPLETE
**Implemented:** October 18, 2025
**Next Phase:** 11.0E-B (Pipeline Integration)
