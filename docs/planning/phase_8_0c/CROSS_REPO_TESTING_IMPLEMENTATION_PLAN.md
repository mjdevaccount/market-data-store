# Cross-Repo Contract Testing — Implementation Plan

**Repository:** `market-data-store`
**Core Target:** v1.1.1
**Estimated Time:** 2.5 hours
**Risk Level:** Low

---

## Pre-Implementation Checklist

Before starting, verify:

- [ ] Core v1.1.1 CHANGELOG reviewed (check for breaking changes)
- [ ] Virtual environment activated (`.venv`)
- [ ] Git branch is clean (`git status`)
- [ ] All existing tests pass (`pytest tests/unit/ -v`)

---

## Phase 1: Core v1.1.1 Upgrade & Validation (30 min)

### 1.1 Inspect Core v1.1.1 Changes

**Goal:** Identify any breaking changes between v1.1.0 → v1.1.1

**Commands:**
```bash
# Check Core changelog/releases
gh release view v1.1.1 --repo mjdevaccount/market-data-core

# Or inspect git diff
git clone --depth 1 --branch v1.1.1 https://github.com/mjdevaccount/market-data-core.git /tmp/core-v1.1.1
git clone --depth 1 --branch v1.1.0 https://github.com/mjdevaccount/market-data-core.git /tmp/core-v1.1.0

diff -r /tmp/core-v1.1.0/src/market_data_core/telemetry/ \
        /tmp/core-v1.1.1/src/market_data_core/telemetry/
```

**What to Look For:**
- `FeedbackEvent` signature changes (fields added/removed/renamed)
- `BackpressureLevel` enum value changes
- `HealthStatus` or `HealthComponent` schema changes
- New required fields (would break Store)

**Decision Point:**
- ✅ No breaking changes → Proceed with upgrade
- ❌ Breaking changes found → Pause, coordinate with Core team

---

### 1.2 Update Dependency

**File:** `pyproject.toml`

**Change:**
```diff
  dependencies = [
-   "market-data-core @ git+https://github.com/mjdevaccount/market-data-core.git@v1.1.0",
+   "market-data-core @ git+https://github.com/mjdevaccount/market-data-core.git@v1.1.1",
    "fastapi>=0.115",
    ...
  ]
```

**Commands:**
```bash
# Update pyproject.toml (use search_replace tool)
# Then reinstall
pip install -e . --force-reinstall --no-deps
pip freeze | grep market-data-core
# Should show: market-data-core @ git+https://...@v1.1.1
```

---

### 1.3 Validate Existing Tests

**Run all contract-related tests:**

```bash
# Contract schemas
pytest tests/unit/test_contract_schemas.py -v

# Health contracts
pytest tests/integration/test_health_contract.py -v

# Feedback integration
pytest tests/unit/coordinator/test_feedback_integration.py -v
```

**Expected Output:**
```
tests/unit/test_contract_schemas.py::test_feedback_event_extends_core PASSED
tests/unit/test_contract_schemas.py::test_feedback_event_schema_roundtrip PASSED
...
========================= 26 passed in 1.23s =========================
```

**If Tests Fail:**
1. Capture error message
2. Identify which Core field/schema changed
3. Determine if Store code needs updating or if Core has bug
4. Escalate to Core team if needed

**Commit:**
```bash
git add pyproject.toml
git commit -m "build: upgrade market-data-core to v1.1.1"
```

**Deliverables:**
- [ ] Core v1.1.1 installed
- [ ] All 26 contract tests pass
- [ ] All 9 health integration tests pass
- [ ] Commit pushed

---

## Phase 2: Test Reorganization (45 min)

### 2.1 Create Contract Test Directory

**Structure:**
```
tests/
└── contracts/
    ├── __init__.py
    ├── test_feedback_event_contracts.py
    └── test_health_contracts.py
```

**Commands:**
```bash
mkdir -p tests/contracts
```

---

### 2.2 Create `tests/contracts/__init__.py`

**File:** `tests/contracts/__init__.py`

```python
"""
Cross-repo contract tests for market-data-store.

These tests validate Store's compatibility with Core DTOs.
Triggered by Core repo via GitHub Actions workflow dispatch.

**Focus Areas:**
- FeedbackEvent extension maintains Core compatibility
- HealthStatus/HealthComponent schemas correct
- Enum values stable (BackpressureLevel)

**Run Locally:**
    pytest tests/contracts/ -v

**Run via GitHub Actions:**
    gh workflow run dispatch_contracts.yml -f core_ref=v1.1.1

**Design Principles:**
- Keep tests lean (<30s total runtime)
- Focus on contract boundaries, not Store internals
- No database or external service dependencies
- Pure schema validation and type checking
"""
```

---

### 2.3 Create `tests/contracts/test_feedback_event_contracts.py`

**File:** `tests/contracts/test_feedback_event_contracts.py`

**Content:** Extract lean tests from `tests/unit/test_contract_schemas.py`

```python
"""
FeedbackEvent cross-repo contract tests.

Validates Store's extended FeedbackEvent maintains Core compatibility.
"""

import time
from market_data_core.telemetry import (
    FeedbackEvent as CoreFeedbackEvent,
    BackpressureLevel,
)
from market_data_store.coordinator import FeedbackEvent


def test_store_feedback_extends_core():
    """Store FeedbackEvent is-a Core FeedbackEvent (subclass)."""
    assert issubclass(FeedbackEvent, CoreFeedbackEvent)


def test_core_can_parse_store_events():
    """Core consumers can parse Store events (ignore extra fields)."""
    # Store creates event with extra 'reason' field
    store_event = FeedbackEvent.create(
        coordinator_id="test-coord",
        queue_size=80,
        capacity=100,
        level=BackpressureLevel.soft,
        reason="high_watermark",  # Store-specific
    )

    # Serialize
    json_data = store_event.model_dump()

    # Core consumer deserializes (ignores 'reason')
    core_event = CoreFeedbackEvent.model_validate(json_data)

    # Core sees all required fields
    assert core_event.coordinator_id == "test-coord"
    assert core_event.queue_size == 80
    assert core_event.capacity == 100
    assert core_event.level == BackpressureLevel.soft
    assert core_event.source == "store"

    # Extra field not visible to Core
    assert not hasattr(core_event, "reason")


def test_store_event_roundtrip():
    """Store event serializes and deserializes correctly."""
    event = FeedbackEvent.create(
        coordinator_id="test",
        queue_size=500,
        capacity=1000,
        level=BackpressureLevel.hard,
        reason="circuit_open",
    )

    # Roundtrip
    json_str = event.model_dump_json()
    restored = FeedbackEvent.model_validate_json(json_str)

    # Verify all fields preserved
    assert restored.coordinator_id == event.coordinator_id
    assert restored.queue_size == event.queue_size
    assert restored.capacity == event.capacity
    assert restored.level == event.level
    assert restored.reason == event.reason
    assert restored.source == "store"


def test_backpressure_level_enum_stable():
    """BackpressureLevel enum values must never change (breaking)."""
    # These values are part of the contract — changing them breaks pipelines
    assert BackpressureLevel.ok.value == "ok"
    assert BackpressureLevel.soft.value == "soft"
    assert BackpressureLevel.hard.value == "hard"

    # Must serialize as strings
    import json

    payload = json.dumps({"level": BackpressureLevel.hard.value})
    assert "hard" in payload


def test_feedback_factory_auto_fills_required_fields():
    """FeedbackEvent.create() auto-fills Core-required 'ts' and 'source'."""
    before = time.time()
    event = FeedbackEvent.create(
        coordinator_id="test",
        queue_size=50,
        capacity=100,
        level=BackpressureLevel.ok,
    )
    after = time.time()

    # Auto-filled 'ts'
    assert before <= event.ts <= after

    # Auto-filled 'source'
    assert event.source == "store"


def test_isinstance_compatibility():
    """Store event passes isinstance checks for Core type."""
    store_event = FeedbackEvent.create(
        coordinator_id="test",
        queue_size=10,
        capacity=100,
        level=BackpressureLevel.ok,
    )

    # Type compatibility
    assert isinstance(store_event, CoreFeedbackEvent)
    assert isinstance(store_event, FeedbackEvent)
```

**Test Count:** 6 tests
**Runtime:** ~0.5s

---

### 2.4 Create `tests/contracts/test_health_contracts.py`

**File:** `tests/contracts/test_health_contracts.py`

```python
"""
HealthStatus/HealthComponent cross-repo contract tests.

Validates Store's health endpoints return Core-compatible DTOs.
"""

import time
from market_data_core.telemetry import HealthStatus, HealthComponent


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
        ts=time.time(),
    )

    # Serialize
    json_str = health.model_dump_json()

    # Deserialize
    restored = HealthStatus.model_validate_json(json_str)

    assert restored.service == "market-data-store"
    assert restored.state == "degraded"
    assert len(restored.components) == 2
    assert restored.version == "0.4.0"


def test_health_component_states():
    """HealthComponent accepts all Core state enum values."""
    valid_states = ["healthy", "degraded", "unhealthy"]

    for state in valid_states:
        component = HealthComponent(name="test", state=state)
        assert component.state == state


def test_health_component_optional_details():
    """HealthComponent supports optional details dict."""
    component = HealthComponent(
        name="queue",
        state="degraded",
        details={"size": "950", "capacity": "1000"},
    )

    assert component.details["size"] == "950"
    assert component.details["capacity"] == "1000"

    # Serialize with details
    json_str = component.model_dump_json()
    restored = HealthComponent.model_validate_json(json_str)

    assert restored.details == component.details


def test_health_status_timestamp_type():
    """HealthStatus.ts is float (UNIX timestamp)."""
    health = HealthStatus(
        service="store",
        state="healthy",
        components=[],
        version="0.4.0",
        ts=time.time(),
    )

    assert isinstance(health.ts, float)
    assert health.ts > 0
```

**Test Count:** 4 tests
**Runtime:** ~0.2s

---

### 2.5 Validate Contract Tests

**Run new contract tests:**

```bash
pytest tests/contracts/ -v
```

**Expected Output:**
```
tests/contracts/test_feedback_event_contracts.py::test_store_feedback_extends_core PASSED
tests/contracts/test_feedback_event_contracts.py::test_core_can_parse_store_events PASSED
tests/contracts/test_feedback_event_contracts.py::test_store_event_roundtrip PASSED
tests/contracts/test_feedback_event_contracts.py::test_backpressure_level_enum_stable PASSED
tests/contracts/test_feedback_event_contracts.py::test_feedback_factory_auto_fills_required_fields PASSED
tests/contracts/test_feedback_event_contracts.py::test_isinstance_compatibility PASSED
tests/contracts/test_health_contracts.py::test_health_status_schema PASSED
tests/contracts/test_health_contracts.py::test_health_component_states PASSED
tests/contracts/test_health_contracts.py::test_health_component_optional_details PASSED
tests/contracts/test_health_contracts.py::test_health_status_timestamp_type PASSED

========================= 10 passed in 0.78s =========================
```

**Verify old tests still pass:**

```bash
pytest tests/unit/test_contract_schemas.py -v
```

**Commit:**
```bash
git add tests/contracts/
git commit -m "test: add dedicated cross-repo contract test suite"
```

**Deliverables:**
- [ ] `tests/contracts/` directory created
- [ ] 10 contract tests passing
- [ ] Tests run in <1 second
- [ ] Original tests unchanged

---

## Phase 3: GitHub Actions Workflows (60 min)

### 3.1 Create Reusable Workflow

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
    timeout-minutes: 5

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
          echo "=== Installed Core version ==="
          pip freeze | grep market-data-core

      - name: Install Store + test dependencies
        run: |
          pip install -e .
          pip install pytest pytest-asyncio

      - name: Run contract tests
        run: |
          pytest tests/contracts/ -v --tb=short --color=yes

      - name: Report results
        if: always()
        run: |
          echo "::notice::Contract tests completed for Core ref ${{ inputs.core_ref }}"
```

**Key Features:**
- Timeout after 5 minutes (prevent hanging)
- Cache pip dependencies for speed
- Echo Core version for debugging
- Run only `tests/contracts/` (fast feedback)
- Report results even on failure

---

### 3.2 Create Dispatch Handler

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
        default: "v1.1.1"

jobs:
  run-contracts:
    name: "Run contract tests vs Core ${{ inputs.core_ref }}"
    uses: ./.github/workflows/_contracts_reusable.yml
    with:
      core_ref: ${{ inputs.core_ref }}
```

**Usage:**

Manually trigger:
```bash
gh workflow run dispatch_contracts.yml -f core_ref=v1.1.1
```

From Core repo (after setting `REPO_TOKEN`):
```bash
gh workflow run dispatch_contracts.yml \
  --repo mjdevaccount/market-data-store \
  --ref master \
  -f core_ref=v1.2.0-rc1
```

---

### 3.3 Enhance Main CI

**File:** `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [master, main]
  pull_request:
    branches: [master, main]

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: 'pip'

      - name: Install dependencies
        run: |
          python -m pip install -U pip wheel
          pip install -e .
          pip install pytest pytest-asyncio httpx

      - name: Import check
        run: python -c "import datastore; print('✅ Import OK')"

      - name: Run contract tests
        run: |
          echo "=== Contract Tests (Core compatibility) ==="
          pytest tests/contracts/ -v --tb=short

      - name: Run unit tests
        run: |
          echo "=== Unit Tests ==="
          pytest tests/unit/ -v --tb=short

      # Optional: Integration tests (requires DB)
      # - name: Run integration tests
      #   run: pytest tests/integration/ -v
```

**Improvements:**
- Runs contract tests on every push/PR
- Separates contract vs unit test output
- Caches pip for faster runs
- Timeout prevents infinite hangs

---

### 3.4 Test Workflow Locally

**Using `act` (GitHub Actions local runner):**

```bash
# Install act (if not already)
# brew install act  # macOS
# choco install act-cli  # Windows

# Run contract tests locally
act workflow_dispatch -j run-contracts -P ubuntu-latest=ghcr.io/catthehacker/ubuntu:act-latest
```

**Or test workflow logic manually:**

```bash
# Simulate what workflow does
pip install "git+https://github.com/mjdevaccount/market-data-core.git@v1.1.1"
pip install -e .
pip install pytest pytest-asyncio
pytest tests/contracts/ -v
```

---

### 3.5 Commit Workflows

```bash
git add .github/workflows/
git commit -m "ci: add cross-repo contract testing workflows"
```

**Deliverables:**
- [ ] `_contracts_reusable.yml` created
- [ ] `dispatch_contracts.yml` created
- [ ] `ci.yml` enhanced to run contract tests
- [ ] Workflows tested locally or via manual dispatch

---

## Phase 4: Secrets & Documentation (30 min)

### 4.1 Configure GitHub Secret

**Purpose:** Allow Core repo to trigger Store workflows via API.

**Steps:**

```bash
# Set secret in Store repo
gh secret set REPO_TOKEN --body "iamalive" --repo mjdevaccount/market-data-store

# Verify
gh secret list --repo mjdevaccount/market-data-store
```

**Note:** Core repo will need this token to authenticate when dispatching workflows.

---

### 4.2 Update README

**File:** `README.md`

Add section after "Testing":

```markdown
## Cross-Repo Contract Testing

Store participates in Core's cross-repo contract testing system to ensure compatibility with `market-data-core` DTOs.

### What We Test

- **FeedbackEvent:** Store's extended `FeedbackEvent` maintains backward compatibility with Core's base class
- **HealthStatus:** Health endpoints return valid Core DTOs
- **Enum Stability:** `BackpressureLevel` values remain stable

### Running Contract Tests Locally

```bash
# Install specific Core version
pip install "git+https://github.com/mjdevaccount/market-data-core.git@v1.1.1"

# Run contract tests
pytest tests/contracts/ -v

# Should complete in <1 second with 10 tests passing
```

### How Cross-Repo Testing Works

When Core publishes a new version, it triggers Store's contract tests:

```bash
gh workflow run dispatch_contracts.yml \
  --repo mjdevaccount/market-data-store \
  -f core_ref=v1.2.0
```

**If tests pass:** Store is compatible with new Core version
**If tests fail:** Breaking change detected — Store needs update

### Test Organization

```
tests/
├── contracts/           # Cross-repo contract tests (fast, lean)
├── unit/                # Store-internal unit tests (comprehensive)
└── integration/         # Full API integration tests (E2E)
```

**contracts/**: Run by Core repo, focus on DTO compatibility
**unit/**: Run by Store CI, cover all Store features
**integration/**: Run by Store CI, validate full stack
```

---

### 4.3 Document Workflow Dispatch

**File:** `.github/workflows/README.md` (new file)

```markdown
# GitHub Actions Workflows

## Contract Testing

### `_contracts_reusable.yml`

Reusable workflow for running contract tests against a specific Core version.

**Inputs:**
- `core_ref` (required): Git ref of market-data-core (tag, branch, or SHA)

**Usage:**
Called by other workflows. Not triggered directly.

---

### `dispatch_contracts.yml`

Manual workflow dispatch handler for contract testing.

**Trigger:**
```bash
gh workflow run dispatch_contracts.yml -f core_ref=v1.1.1
```

**Use Cases:**
- Test Store against unreleased Core version (branch, RC tag)
- Verify compatibility before upgrading Core dependency
- Debug contract test failures

**From Core Repo:**
Core can trigger this workflow after publishing a new version:

```bash
gh workflow run dispatch_contracts.yml \
  --repo mjdevaccount/market-data-store \
  --ref master \
  -f core_ref=v1.2.0
```

Requires `REPO_TOKEN` secret configured.

---

### `ci.yml`

Main CI pipeline.

**Triggers:**
- Push to `master`/`main`
- Pull requests

**Jobs:**
1. Import check
2. Contract tests (`tests/contracts/`)
3. Unit tests (`tests/unit/`)

**Runtime:** ~2-3 minutes
```

---

### 4.4 Commit Documentation

```bash
git add README.md .github/workflows/README.md
git commit -m "docs: document cross-repo contract testing system"
```

**Deliverables:**
- [ ] `REPO_TOKEN` secret configured
- [ ] README documents contract testing
- [ ] Workflow README explains dispatch mechanism
- [ ] Contributors understand local testing process

---

## Post-Implementation Validation

### Test Manual Workflow Dispatch

```bash
# Trigger workflow manually
gh workflow run dispatch_contracts.yml -f core_ref=v1.1.1

# Watch progress
gh run watch

# View results
gh run list --workflow=dispatch_contracts.yml
```

**Expected Output:**
```
✓ master dispatch_contracts Contract tests vs Core v1.1.1  10s (ID 123456789)
```

---

### Test CI on Push

```bash
# Make trivial change
echo "# Test CI" >> README.md
git add README.md
git commit -m "test: verify CI runs contract tests"
git push

# Watch CI
gh run watch
```

**Expected Output:**
```
✓ master CI Import check         ... 2s
✓ master CI Contract tests       ... 5s
✓ master CI Unit tests           ... 45s
```

---

### Verify Contract Test Isolation

**Goal:** Ensure contract tests don't depend on Store internals.

```bash
# Run only contract tests (no other dependencies)
pytest tests/contracts/ -v --co  # Collect tests only

# Should show 10 tests, no import errors
```

---

## Rollback Plan

If anything goes wrong:

### Phase 1 Rollback (Core v1.1.1)

```bash
# Revert to v1.1.0
git revert <commit-sha>
pip install -e . --force-reinstall
pytest tests/unit/test_contract_schemas.py -v
```

### Phase 2 Rollback (Test Reorganization)

```bash
# Delete contracts directory
rm -rf tests/contracts/
git checkout tests/contracts/  # If committed
```

### Phase 3 Rollback (Workflows)

```bash
# Delete workflows
rm .github/workflows/_contracts_reusable.yml
rm .github/workflows/dispatch_contracts.yml
git checkout .github/workflows/ci.yml  # Restore original
```

**No rollback needed for Phase 4** (docs/secrets don't affect functionality).

---

## Success Metrics

**Phase 1:**
- ✅ Core v1.1.1 installed without errors
- ✅ All 35+ existing tests pass

**Phase 2:**
- ✅ 10 contract tests created
- ✅ Tests run in <1 second
- ✅ No test duplication (lean tests only)

**Phase 3:**
- ✅ Workflows lint successfully (`yamllint .github/workflows/*.yml`)
- ✅ Manual dispatch succeeds
- ✅ CI runs on push

**Phase 4:**
- ✅ Secret configured
- ✅ Documentation clear and accurate

---

## Troubleshooting

### Core v1.1.1 Install Fails

**Error:** `ERROR: Could not find a version that satisfies the requirement...`

**Solution:**
```bash
# Check if v1.1.1 tag exists
gh release view v1.1.1 --repo mjdevaccount/market-data-core

# If tag missing, stay on v1.1.0
```

---

### Contract Tests Fail with Import Error

**Error:** `ModuleNotFoundError: No module named 'market_data_store'`

**Solution:**
```bash
# Reinstall Store in editable mode
pip install -e .

# Verify
python -c "from market_data_store.coordinator import FeedbackEvent; print('OK')"
```

---

### GitHub Actions Workflow Syntax Error

**Error:** `Invalid workflow file...`

**Solution:**
```bash
# Validate YAML syntax
yamllint .github/workflows/_contracts_reusable.yml

# Or use GitHub's API
gh workflow list  # Will show syntax errors
```

---

### Workflow Dispatch Fails (Permission Denied)

**Error:** `Resource not accessible by integration`

**Solution:**
```bash
# Ensure REPO_TOKEN is set
gh secret list --repo mjdevaccount/market-data-store

# Re-create if missing
gh secret set REPO_TOKEN --body "iamalive"
```

---

## Appendix: File Change Summary

| File | Change Type | Lines Changed |
|------|-------------|---------------|
| `pyproject.toml` | Modified | 1 line (Core version) |
| `tests/contracts/__init__.py` | Created | ~20 lines (docstring) |
| `tests/contracts/test_feedback_event_contracts.py` | Created | ~120 lines (6 tests) |
| `tests/contracts/test_health_contracts.py` | Created | ~80 lines (4 tests) |
| `.github/workflows/_contracts_reusable.yml` | Created | ~40 lines |
| `.github/workflows/dispatch_contracts.yml` | Created | ~20 lines |
| `.github/workflows/ci.yml` | Modified | +25 lines |
| `README.md` | Modified | +40 lines |
| `.github/workflows/README.md` | Created | ~60 lines |

**Total New Files:** 5
**Total Modified Files:** 3
**Total Lines Added:** ~400

---

## Final Checklist

- [ ] Phase 1: Core v1.1.1 validated and installed
- [ ] Phase 2: 10 contract tests created and passing
- [ ] Phase 3: 3 workflows created and tested
- [ ] Phase 4: Documentation updated, secret configured
- [ ] All commits pushed to master
- [ ] CI runs successfully on push
- [ ] Manual workflow dispatch tested
- [ ] README updated with contract testing section
- [ ] Rollback plan documented (this document)

**Estimated Completion Time:** 2.5 hours
**Actual Time:** _____ (fill in after completion)
