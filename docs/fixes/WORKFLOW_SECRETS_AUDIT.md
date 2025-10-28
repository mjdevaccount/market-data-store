# Workflow Secrets Audit

## Summary

All GitHub workflow files have been analyzed and **the secret naming inconsistency has been FIXED**. ✅

---

## ✅ ISSUE RESOLVED

### PyPI Token Secret Name - Now Consistent

All workflows now use **`PYPI_API_TOKEN`** consistently:

| Workflow | Line | Secret Name Used |
|----------|------|------------------|
| `.github/workflows/release.yml` | 61 | `secrets.PYPI_API_TOKEN` ✅ |
| `.github/workflows/auto_release_on_merge.yml` | 74 | `secrets.PYPI_API_TOKEN` ✅ |

**Status:** Fixed - All workflows now reference the correct secret that exists in the repository.

---

## Current Repository Secrets

These secrets are configured and used correctly:

### 1. ✅ PYPI_API_TOKEN

**Purpose:** Publish packages to PyPI
**Status:** ✅ Configured (updated ~19 hours ago)
**Used in:**
- `.github/workflows/release.yml` (line 61) - Tag-triggered releases
- `.github/workflows/auto_release_on_merge.yml` (line 74) - Auto-releases on dependency updates

### 2. ✅ REPO_TOKEN

**Purpose:** Create PRs and trigger repository dispatch events
**Status:** ✅ Configured (updated ~4 days ago)
**Used in:**
- `.github/workflows/auto_release_on_merge.yml` (line 99) - Notify infra repo
- `.github/workflows/on_core_release.yml` (lines 62, 92) - Create PRs and enable auto-merge

**Required Permissions:**
- `contents: write`
- `pull-requests: write`
- `actions: write`

### 3. ✅ TEST_PYPI_API_TOKEN

**Purpose:** Publish to Test PyPI (for testing releases)
**Status:** ✅ Configured (updated ~19 hours ago)
**Used in:** Not currently used in workflows (available for future test releases)

---

## Workflows That DON'T Use Secrets

These workflows work without any secrets:

✅ `.github/workflows/ci.yml` - Basic CI tests
✅ `.github/workflows/registry_contracts.yml` - Contract tests (public Registry)
✅ `.github/workflows/_contracts_reusable.yml` - Reusable contract tests
✅ `.github/workflows/_pulse_reusable.yml` - Reusable pulse tests
✅ `.github/workflows/dispatch_contracts.yml` - Manual contract trigger
✅ `.github/workflows/dispatch_pulse.yml` - Manual pulse trigger

---

## Workflow Secret Usage Details

### release.yml (Tag-triggered PyPI release)
```yaml
Line 61: TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}  ✅ FIXED
```

### auto_release_on_merge.yml (Auto-release on dependency update)
```yaml
Line 74:  TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}  ✅
Line 99:  token: ${{ secrets.REPO_TOKEN }}  ✅
```

### on_core_release.yml (Respond to Core release)
```yaml
Line 62:  token: ${{ secrets.REPO_TOKEN }}  ✅
Line 92:  token: ${{ secrets.REPO_TOKEN }}  ✅
```

---

## Changes Made

**Date:** October 22, 2025

1. ✅ Audited all workflow files for secret usage
2. ✅ Identified inconsistency: `PYPI_TOKEN` vs `PYPI_API_TOKEN`
3. ✅ Checked repository secrets via `gh secret list`
4. ✅ Updated `.github/workflows/release.yml` to use `PYPI_API_TOKEN`
5. ✅ Verified all secrets are correctly referenced

**All workflows should now work correctly!** 🎉
