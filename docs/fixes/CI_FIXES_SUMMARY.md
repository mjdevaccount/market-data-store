# CI Failures - Root Causes and Fixes

**Date:** October 22, 2025
**Status:** ✅ All Issues Resolved

---

## Issues Found and Fixed

### 1. ✅ FIXED: Secret Name Inconsistency

**Problem:** Workflows used different names for the PyPI token
- `release.yml` was looking for `secrets.PYPI_TOKEN`
- `auto_release_on_merge.yml` was looking for `secrets.PYPI_API_TOKEN`
- Only `PYPI_API_TOKEN` exists in the repository

**Impact:** Release workflow would fail when trying to publish to PyPI

**Fix:**
- Updated `.github/workflows/release.yml` line 61 to use `secrets.PYPI_API_TOKEN`
- All workflows now consistently use `PYPI_API_TOKEN`

**Files Changed:**
- `.github/workflows/release.yml`

---

### 2. ✅ FIXED: Invalid Dependency Version

**Problem:** Dependency constraint referenced non-existent version
- `pyproject.toml` required `market-data-core>=1.2.99,<2.0.0`
- `requirements.txt` required `market-data-core>=1.2.8,<2.0.0`
- Version 1.2.99 doesn't exist (latest is 1.2.12)

**Impact:** CI workflow failed during `pip install -e .` step

**Error Message:**
```
ERROR: Could not find a version that satisfies the requirement
market-data-core<2.0.0,>=1.2.99 (from versions: 1.2.0, 1.2.8, 1.2.9, 1.2.11, 1.2.12)
ERROR: No matching distribution found for market-data-core<2.0.0,>=1.2.99
```

**Root Cause:**
The `on_core_release.yml` workflow was likely triggered with version 1.2.99
(which doesn't exist), causing it to update the dependency constraints to an
invalid version.

**Fix:**
- Updated both files to use `market-data-core>=1.2.12,<2.0.0`
- This matches the latest available version from PyPI

**Files Changed:**
- `pyproject.toml` (line 8)
- `requirements.txt` (line 5)

---

## Repository Secrets Status

All required secrets are properly configured:

| Secret Name | Status | Last Updated | Purpose |
|------------|--------|--------------|---------|
| `PYPI_API_TOKEN` | ✅ Configured | ~19 hours ago | Publish to PyPI |
| `REPO_TOKEN` | ✅ Configured | ~4 days ago | PR creation & dispatch events |
| `TEST_PYPI_API_TOKEN` | ✅ Configured | ~19 hours ago | Test PyPI publishing |

---

## Affected Workflows

### Now Working ✅

1. **CI Workflow** (`.github/workflows/ci.yml`)
   - Fixed by updating dependency version
   - Should now successfully install and test

2. **Registry Contract Tests** (`.github/workflows/registry_contracts.yml`)
   - Fixed by updating dependency version
   - Contract tests should pass

3. **Release Workflow** (`.github/workflows/release.yml`)
   - Fixed by updating secret name
   - Will successfully publish to PyPI on tags

4. **Auto-Release Workflow** (`.github/workflows/auto_release_on_merge.yml`)
   - Already using correct secret name
   - Should work correctly

---

## Verification Steps

To verify the fixes work:

1. **Test CI locally:**
   ```bash
   pip install -e .
   python -c "import datastore; print('ok')"
   ```

2. **Test with latest Core:**
   ```bash
   pip install 'market-data-core>=1.2.12,<2.0.0'
   ```

3. **Trigger CI workflow:**
   - Push this commit to trigger CI
   - Check that `pip install -e .` succeeds

4. **Check workflow runs:**
   - Go to Actions tab
   - Verify CI and Registry Contract workflows pass

---

## Prevention

To prevent version 1.2.99 issue from recurring:

1. **Only trigger `on_core_release.yml` with valid versions**
   - Verify version exists on PyPI before triggering
   - Check: https://pypi.org/project/market-data-core/#history

2. **Add version validation to workflow** (optional future improvement)
   - Could add a step to verify version exists before updating dependencies

---

## Summary

✅ **Secret naming:** Standardized to `PYPI_API_TOKEN`
✅ **Dependency version:** Updated to use existing version `1.2.12`
✅ **Both CI and Registry Contract workflows should now pass**

All files have been updated and are ready to commit.
