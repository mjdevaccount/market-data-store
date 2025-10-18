# Cross-Repo Contract Testing — Executive Summary

**Date:** October 18, 2025
**Repository:** `market-data-store`
**Status:** ✅ **VIABLE & RECOMMENDED**

---

## TL;DR

Store already implements **~70% of the proposed cross-repo testing infrastructure**. The remaining 30% is low-risk workflow automation.

**Recommendation:** ✅ **PROCEED** — Estimated 2.5 hours for full implementation.

---

## What Already Works ✅

1. **Store extends Core's `FeedbackEvent` correctly** (adapter pattern)
   - Adds `reason` and `utilization` fields
   - Maintains full Core compatibility
   - 26 contract tests validate this

2. **Health endpoints use Core DTOs**
   - `/healthz` returns `HealthStatus`
   - `/readyz` returns `HealthStatus`
   - 9 integration tests verify compliance

3. **Core v1.1.0 dependency installed**
   - Pinned in `pyproject.toml`
   - All imports working
   - No breaking changes detected

---

## What's Missing ❌

1. **Core v1.1.1 upgrade** (currently on v1.1.0)
2. **GitHub Actions workflows** for cross-repo testing
3. **Dedicated `tests/contracts/` directory** (tests exist but scattered)
4. **Documentation** for contract testing system

---

## Risk Assessment

| Risk Level | Item | Mitigation |
|------------|------|------------|
| **Low** | Core v1.1.1 upgrade | Verify CHANGELOG first, rollback if needed |
| **Low** | Workflow creation | Standard patterns, no special permissions |
| **Low** | Test reorganization | Copy existing tests, no new logic |
| **Zero** | Breaking changes | All contracts already validated |

---

## Implementation Plan (2.5 hours)

### Phase 1: Core v1.1.1 Upgrade (30 min)
- Update `pyproject.toml` dependency
- Verify no breaking changes
- Run all existing tests

### Phase 2: Test Reorganization (45 min)
- Create `tests/contracts/` directory
- Extract 10 lean tests from existing suite
- Validate <1s runtime

### Phase 3: GitHub Actions (60 min)
- Create `_contracts_reusable.yml` (reusable workflow)
- Create `dispatch_contracts.yml` (manual dispatch handler)
- Enhance `ci.yml` to run contract tests

### Phase 4: Documentation (30 min)
- Configure `REPO_TOKEN` secret
- Update README with contract testing section
- Document workflow usage

---

## Key Decisions

### ✅ Use Adapter Pattern (Already Implemented)
Store extends Core DTOs rather than replacing them. This allows:
- Store-specific fields (`reason`, `utilization`)
- Full Core compatibility (Core consumers ignore extra fields)
- Zero breaking changes

### ✅ Separate Contract Tests
Create `tests/contracts/` for cross-repo testing:
- **contracts/**: Lean, fast (<1s), run by Core repo
- **unit/**: Comprehensive, Store-internal
- **integration/**: Full E2E

### ✅ Manual Workflow Dispatch First
Start with manual triggering, automate later:
1. Test with `gh workflow run dispatch_contracts.yml -f core_ref=v1.1.1`
2. Once stable, Core repo can automate dispatch

---

## Success Criteria

- [ ] Core v1.1.1 installed without errors
- [ ] 10 contract tests passing in <1 second
- [ ] 3 GitHub workflows created and functional
- [ ] Manual workflow dispatch succeeds
- [ ] CI runs contract tests on every push
- [ ] Documentation updated in README

---

## Files to Create/Modify

**Created (5 files):**
- `tests/contracts/__init__.py`
- `tests/contracts/test_feedback_event_contracts.py`
- `tests/contracts/test_health_contracts.py`
- `.github/workflows/_contracts_reusable.yml`
- `.github/workflows/dispatch_contracts.yml`

**Modified (3 files):**
- `pyproject.toml` (Core version: v1.1.0 → v1.1.1)
- `.github/workflows/ci.yml` (add contract test step)
- `README.md` (add contract testing section)

**Total Lines:** ~400 lines added

---

## Open Questions

1. **What changed in Core v1.1.1?**
   - **Action:** Review Core CHANGELOG before upgrading
   - **Risk:** Low (semantic versioning suggests no breaking changes)

2. **Do we need cross-version testing?**
   - **Answer:** Not initially. Start with v1.1.1 only, expand later if needed

3. **Should workflows auto-run on Core releases?**
   - **Answer:** Phase 2 feature. Start with manual dispatch, automate once stable

---

## Detailed Documentation

For full details, see:
- **`CROSS_REPO_TESTING_EVALUATION.md`** — Comprehensive viability assessment
- **`CROSS_REPO_TESTING_IMPLEMENTATION_PLAN.md`** — Step-by-step implementation guide

---

## Next Steps

**If approved:**
1. Review this summary + evaluation doc
2. Start with Phase 1 (Core v1.1.1 verification)
3. If Phase 1 succeeds → proceed with Phases 2-4
4. If Phase 1 fails → coordinate with Core team

**Awaiting decision to proceed with implementation.**

---

## Appendix: Current vs. Proposed State

### Current State
```
market-data-store/
├── src/
│   └── market_data_store/coordinator/
│       └── feedback.py              # ✅ Extends Core.FeedbackEvent
├── tests/
│   ├── unit/
│   │   └── test_contract_schemas.py # ✅ 26 contract tests
│   └── integration/
│       └── test_health_contract.py  # ✅ 9 health tests
├── .github/workflows/
│   └── ci.yml                       # ⚠️ Only checks imports
└── pyproject.toml                   # ⚠️ Core v1.1.0 (outdated)
```

### Proposed State
```
market-data-store/
├── src/
│   └── market_data_store/coordinator/
│       └── feedback.py              # ✅ No changes needed
├── tests/
│   ├── contracts/                   # ✨ NEW: Cross-repo tests
│   │   ├── __init__.py
│   │   ├── test_feedback_event_contracts.py
│   │   └── test_health_contracts.py
│   ├── unit/
│   │   └── test_contract_schemas.py # ✅ Keep existing
│   └── integration/
│       └── test_health_contract.py  # ✅ Keep existing
├── .github/workflows/
│   ├── _contracts_reusable.yml      # ✨ NEW: Reusable workflow
│   ├── dispatch_contracts.yml       # ✨ NEW: Manual dispatch
│   └── ci.yml                       # ✅ Enhanced
└── pyproject.toml                   # ✅ Updated to v1.1.1
```

**Key Insight:** Most code already exists, just needs organization + automation.
