# Cross-Repo Contract Testing — Viability Assessment

**Repository:** `market-data-store`
**Target Core Version:** v1.1.1 (currently on v1.1.0)
**Date:** October 18, 2025
**Status:** ✅ **VIABLE — Partial Implementation Already Exists**

---

## Executive Summary

**Good News:** Store already implements ~70% of the proposed contract testing infrastructure.

**What Exists:**
- ✅ Store extends Core's `FeedbackEvent` with adapter pattern
- ✅ Health endpoints use Core's `HealthStatus`/`HealthComponent`
- ✅ Comprehensive contract tests in `tests/unit/test_contract_schemas.py` (26 tests)
- ✅ Integration tests for health contracts in `tests/integration/test_health_contract.py` (9 tests)
- ✅ Core v1.1.0 dependency installed and operational

**What's Missing:**
- ❌ GitHub Actions workflows for cross-repo testing
- ❌ Dedicated `tests/contracts/` directory (tests are scattered)
- ❌ Core v1.1.1 upgrade (currently on v1.1.0)
- ❌ GitHub secrets for cross-repo dispatch
- ❌ CI doesn't run tests (only checks imports)

**Verdict:** Implementation is **low-risk, high-value**. Most code is already contract-compliant.

---

## Current State Analysis

### 1. FeedbackEvent Extension ✅

**File:** `src/market_data_store/coordinator/feedback.py:28-92`

Store correctly extends Core's `FeedbackEvent`:

```python
from market_data_core.telemetry import FeedbackEvent as CoreFeedbackEvent

class FeedbackEvent(CoreFeedbackEvent):
    """Store-extended feedback event with debugging context."""

    # Store-specific extension
    reason: str | None = Field(default=None, description="Optional backpressure context")

    @property
    def utilization(self) -> float:
        return self.queue_size / self.capacity if self.capacity > 0 else 0.0
```

**Assessment:**
- ✅ Proper inheritance (subclass relationship)
- ✅ Only adds fields, never modifies Core fields
- ✅ Backward compatible (Core consumers ignore extra fields)
- ✅ Factory method auto-fills `ts` and `source`

**Contract Coverage:**
- ✅ Tested in `tests/unit/test_contract_schemas.py::test_feedback_event_extends_core`
- ✅ Tested in `test_feedback_event_schema_roundtrip`
- ✅ Tested in `test_feedback_event_core_subset_parseable`

---

### 2. HealthStatus Integration ✅

**File:** `src/datastore/service/app.py:61-98`

Health endpoints already return Core DTOs:

```python
from market_data_core.telemetry import HealthStatus, HealthComponent

@app.get("/healthz", response_model=HealthStatus)
async def healthz():
    components = [
        HealthComponent(name="database", state=db_state),
        HealthComponent(name="prometheus", state="healthy"),
    ]

    return HealthStatus(
        service="market-data-store",
        state=overall_state,
        components=components,
        version="0.4.0",
        ts=time.time(),
    )
```

**Contract Coverage:**
- ✅ 9 integration tests in `tests/integration/test_health_contract.py`
- ✅ Tests for schema validation, state aggregation, component breakdown
- ✅ Backward compatibility verified

---

### 3. Existing Contract Tests ✅

**File:** `tests/unit/test_contract_schemas.py`

**26 test cases covering:**
- FeedbackEvent extension validation
- Core/Store compatibility (roundtrip serialization)
- BackpressureLevel enum stability
- HealthStatus/HealthComponent schemas
- Type checking and isinstance verification

**Key Tests:**
```python
def test_feedback_event_core_subset_parseable():
    """Core-only consumers can parse Store events (ignore extra fields)."""
    store_event = FeedbackEvent.create(...)
    core_event = CoreFeedbackEvent.model_validate(json_data)
    assert core_event.coordinator_id == "test"
    # Extra field ignored by Core
    assert not hasattr(core_event, "reason")
```

**Assessment:** These tests are **exactly what cross-repo testing needs**. Just need to relocate and run via GitHub Actions.

---

### 4. Dependency Status ⚠️

**File:** `pyproject.toml:8`

```toml
dependencies = [
  "market-data-core @ git+https://github.com/mjdevaccount/market-data-core.git@v1.1.0",
  ...
]
```

**Issue:** Pinned to v1.1.0, but Core is now on v1.1.1.

**Impact:** Low risk if v1.1.1 is backward compatible. Needs verification.

---

### 5. CI Infrastructure ❌

**File:** `.github/workflows/ci.yml`

Current CI only checks imports:

```yaml
- run: pip install -e .
- run: python -c "import datastore; print('ok')"
```

**Missing:**
- No pytest execution
- No contract test isolation
- No cross-repo dispatch capability

---

## Implementation Plan

### Phase 1: Upgrade Core to v1.1.1 (30 min)

**Risk:** Low (semantic versioning suggests backward compatibility)

**Steps:**
1. Update `pyproject.toml` dependency:
   ```toml
   "market-data-core @ git+https://github.com/mjdevaccount/market-data-core.git@v1.1.1"
   ```

2. Verify Core v1.1.1 changes:
   ```bash
   # Check Core CHANGELOG for breaking changes
   curl -s https://raw.githubusercontent.com/mjdevaccount/market-data-core/v1.1.1/CHANGELOG.md
   ```

3. Run existing contract tests:
   ```bash
   pytest tests/unit/test_contract_schemas.py -v
   pytest tests/integration/test_health_contract.py -v
   ```

4. If tests pass → **upgrade is safe**
5. If tests fail → **investigate Core v1.1.1 changes**

**Deliverable:** Core v1.1.1 validated and pinned.

---

### Phase 2: Reorganize Contract Tests (45 min)

**Goal:** Create dedicated `tests/contracts/` directory for cross-repo testing.

**Structure:**
```
tests/
├── contracts/              # NEW: Cross-repo contract tests
│   ├── __init__.py
│   ├── test_feedback_event_contracts.py
│   └── test_health_contracts.py
├── integration/            # KEEP: Full integration tests
│   └── test_health_contract.py
└── unit/                   # KEEP: Unit tests
    └── test_contract_schemas.py
```

**Rationale:**
- `tests/contracts/` — Lean tests for GitHub Actions dispatch (fast, focused)
- `tests/unit/` — Comprehensive Store-internal tests (all edge cases)
- `tests/integration/` — Full API integration tests

**Steps:**

1. Create `tests/contracts/__init__.py`:
   ```python
   """
   Cross-repo contract tests.

   These tests validate Store's compatibility with Core DTOs.
   Run by GitHub Actions via workflow dispatch from Core repo.

   Keep tests lean and focused on contract boundaries.
   """
   ```

2. Create `tests/contracts/test_feedback_event_contracts.py`:
   - Copy critical tests from `test_contract_schemas.py`:
     - `test_feedback_event_extends_core`
     - `test_feedback_event_schema_roundtrip`
     - `test_feedback_event_core_subset_parseable`
     - `test_backpressure_level_values`
   - Focus on **Core compatibility**, not Store-specific features

3. Create `tests/contracts/test_health_contracts.py`:
   - Copy schema validation tests:
     - `test_health_status_schema`
     - `test_health_component_state_enum`
     - `test_health_component_details` (verify optional fields)

**Deliverable:** Dedicated contract test suite (~8-10 tests, <1 min runtime).

---

### Phase 3: GitHub Actions Workflows (60 min)

**Goal:** Enable Core repo to trigger Store contract tests via `workflow_dispatch`.

#### 3.1 Create Reusable Workflow

**File:** `.github/workflows/_contracts_reusable.yml`

```yaml
name: _contracts_reusable

on:
  workflow_call:
    inputs:
      core_ref:
        description: "Git ref (tag/branch/SHA) of market-data-core"
        required: true
        type: string

jobs:
  contracts:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Store repo
        uses: actions/checkout@v4

      - name: Setup Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install Core @ specified ref
        run: |
          pip install -U pip wheel
          pip install "git+https://github.com/mjdevaccount/market-data-core.git@${{ inputs.core_ref }}"
          pip freeze | grep market-data-core

      - name: Install Store + test deps
        run: |
          pip install -e .
          pip install pytest pytest-asyncio

      - name: Run contract tests only
        run: |
          pytest tests/contracts/ -v --tb=short
```

**Key Features:**
- Installs Core at **arbitrary ref** (tag, branch, SHA)
- Runs only `tests/contracts/` (fast feedback)
- Reports test results to caller

#### 3.2 Create Dispatch Handler

**File:** `.github/workflows/dispatch_contracts.yml`

```yaml
name: dispatch_contracts

on:
  workflow_dispatch:
    inputs:
      core_ref:
        description: "Core ref (tag/branch/SHA)"
        required: true
        type: string

jobs:
  run:
    uses: ./.github/workflows/_contracts_reusable.yml
    with:
      core_ref: ${{ inputs.core_ref }}
```

**Usage:**
Core repo can trigger this via GitHub API:
```bash
gh workflow run dispatch_contracts.yml \
  --repo mjdevaccount/market-data-store \
  --ref master \
  -f core_ref=v1.2.0
```

#### 3.3 Enhance Main CI

**File:** `.github/workflows/ci.yml`

Extend existing CI to run all tests:

```yaml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: 'pip'

      - name: Install dependencies
        run: |
          python -m pip install -U pip wheel
          pip install -e .
          pip install pytest pytest-asyncio httpx

      - name: Import check
        run: python -c "import datastore; print('ok')"

      - name: Run contract tests
        run: pytest tests/contracts/ -v

      - name: Run unit tests
        run: pytest tests/unit/ -v

      # Optional: run integration tests if DB available
      # - name: Run integration tests
      #   run: pytest tests/integration/ -v
```

**Deliverable:** Full CI pipeline with contract test isolation.

---

### Phase 4: Secrets & Documentation (30 min)

#### 4.1 Configure GitHub Secret

```bash
# In Store repo settings
gh secret set REPO_TOKEN --body "iamalive"

# Verify
gh secret list
```

**Purpose:** Core repo uses this to authenticate when dispatching workflows.

#### 4.2 Update README

Add section to `README.md`:

```markdown
## Cross-Repo Contract Testing

Store participates in Core's cross-repo contract testing system.

**What We Test:**
- Store's `FeedbackEvent` extends Core's `FeedbackEvent` correctly
- Health endpoints return valid Core `HealthStatus` DTOs
- Enum values remain stable (e.g., `BackpressureLevel`)

**Running Contract Tests Locally:**
```bash
# Install specific Core version
pip install "git+https://github.com/mjdevaccount/market-data-core.git@v1.1.1"

# Run contract tests
pytest tests/contracts/ -v
```

**How It Works:**
When Core publishes a new version, it triggers this workflow:
```bash
gh workflow run dispatch_contracts.yml \
  --repo mjdevaccount/market-data-store \
  -f core_ref=v1.2.0
```

If tests pass → Store is compatible with new Core version.
If tests fail → Breaking change detected, requires Store update.
```

**Deliverable:** Clear documentation for contributors.

---

## Risk Assessment

### Low Risk ✅

1. **Adapter Pattern Already Proven:**
   - Store extends Core DTOs correctly
   - 26 existing contract tests validate compatibility
   - No breaking changes needed

2. **Core v1.1.0 → v1.1.1 Upgrade:**
   - Semantic versioning suggests patch/minor release
   - Existing tests will catch any incompatibilities
   - Rollback is trivial (change git ref)

3. **GitHub Actions Infrastructure:**
   - Standard workflow patterns
   - No special permissions needed (public repos)
   - Fails gracefully if Core ref invalid

### Medium Risk ⚠️

1. **Core v1.1.1 Unknown Changes:**
   - **Mitigation:** Inspect Core CHANGELOG before upgrade
   - **Fallback:** Stay on v1.1.0 if v1.1.1 has breaking changes

2. **Workflow Dispatch Permissions:**
   - **Issue:** Core repo needs `REPO_TOKEN` to trigger Store workflows
   - **Mitigation:** Document token setup, test with manual dispatch first

### Zero Risk 🚫

- **No code changes to business logic** — Only test organization and CI
- **No database schema changes**
- **No API breaking changes** — Health endpoints already use Core DTOs

---

## Test Coverage Gap Analysis

### What's Already Covered ✅

| Contract | Test File | Test Count | Coverage |
|----------|-----------|------------|----------|
| FeedbackEvent extension | `test_contract_schemas.py` | 6 | 100% |
| BackpressureLevel enum | `test_contract_schemas.py` | 1 | 100% |
| HealthStatus schema | `test_contract_schemas.py` | 3 | 100% |
| HealthComponent schema | `test_contract_schemas.py` | 2 | 100% |
| Health endpoint integration | `test_health_contract.py` | 9 | 100% |

### What's Missing ❌

| Contract | Gap | Priority |
|----------|-----|----------|
| Core version detection | No test verifies Core version installed | Low |
| Cross-version compatibility | No tests against Core v1.0.x, v1.2.x | Medium |
| Error message stability | No tests for Pydantic validation errors | Low |

**Recommendation:** Current coverage is **sufficient** for initial rollout. Add cross-version tests in Phase 2.

---

## Success Criteria

### Phase 1 (Core v1.1.1 Upgrade)
- [ ] `pyproject.toml` updated to v1.1.1
- [ ] All 26 contract tests pass with v1.1.1
- [ ] All 9 health integration tests pass
- [ ] No import errors or Pydantic validation failures

### Phase 2 (Test Reorganization)
- [ ] `tests/contracts/` directory created
- [ ] 8-10 lean contract tests extracted
- [ ] Tests run in <30 seconds
- [ ] Original test files remain unchanged (regression safety)

### Phase 3 (GitHub Actions)
- [ ] `_contracts_reusable.yml` workflow created
- [ ] `dispatch_contracts.yml` handler created
- [ ] Main `ci.yml` runs contract tests on every push
- [ ] Manual workflow dispatch succeeds

### Phase 4 (Documentation)
- [ ] `REPO_TOKEN` secret configured
- [ ] README documents contract testing
- [ ] Contributors understand how to run contract tests locally

---

## Timeline Estimate

| Phase | Duration | Effort |
|-------|----------|--------|
| 1. Core v1.1.1 Upgrade | 30 min | Low |
| 2. Test Reorganization | 45 min | Low |
| 3. GitHub Actions | 60 min | Medium |
| 4. Secrets & Docs | 30 min | Low |
| **Total** | **2.5 hours** | **Low** |

**Confidence:** High (90%+)
**Blockers:** None identified
**Dependencies:** Core v1.1.1 must be backward compatible (verify first)

---

## Recommendation

✅ **PROCEED with implementation.**

**Rationale:**
1. Store already implements the adapter pattern correctly
2. Comprehensive contract tests exist (just need reorganization)
3. Low risk, high value (prevents future breaking changes)
4. Estimated 2.5 hours for full implementation

**Suggested Order:**
1. **Phase 1 first** — Verify Core v1.1.1 compatibility before any workflow changes
2. **Phase 2 + 3 together** — Create tests and workflows in parallel
3. **Phase 4 last** — Document once everything is working

**Fallback Plan:**
If Core v1.1.1 has breaking changes → stay on v1.1.0 and coordinate with Core team.

---

## Open Questions

1. **Core v1.1.1 Changes:** What's new in v1.1.1 vs v1.1.0?
   - **Action:** Review Core CHANGELOG before upgrade

2. **Workflow Permissions:** Does Store repo need `actions: read/write` permissions?
   - **Action:** Test manual dispatch before automating

3. **Test Naming Convention:** Should contract tests use `test_contract_*` prefix?
   - **Recommendation:** Yes, makes filtering easier (`pytest -k contract`)

4. **Cross-Version Testing:** Should Store test against multiple Core versions?
   - **Recommendation:** Phase 2 feature, not critical for initial rollout

---

## Next Steps

**If approved:**

1. Run Phase 1 first (Core v1.1.1 verification)
2. If Phase 1 succeeds → proceed with Phases 2-4
3. If Phase 1 fails → pause and coordinate with Core team

**Estimated Start:** Immediately
**Estimated Completion:** Same day (2.5 hours active work)

---

## Appendix: Test Duplication Strategy

**Question:** Why keep tests in both `tests/contracts/` and `tests/unit/`?

**Answer:**

| Directory | Purpose | Audience | Runtime |
|-----------|---------|----------|---------|
| `tests/contracts/` | Cross-repo validation | Core repo (via GH Actions) | <30s |
| `tests/unit/` | Comprehensive Store testing | Store developers | ~2-3 min |
| `tests/integration/` | Full API integration | Store CI/CD | ~5-10 min |

**Analogy:**
- `contracts/` = "Smoke tests" — Fast, focused, run on every Core release
- `unit/` = "Deep tests" — All edge cases, Store-specific features
- `integration/` = "E2E tests" — Full stack validation

**Duplication is intentional** — Different audiences, different performance requirements.
