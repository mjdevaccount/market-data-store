# Release v0.6.3 - PostgreSQL Connectivity Fix

**Release Date:** October 21, 2025
**Tag:** v0.6.3
**Type:** Hotfix

## Overview
Critical hotfix to resolve PostgreSQL database connectivity issue discovered by the validation framework during integration testing.

## Issue #19: Missing psycopg2 Module

### Problem
The store service was failing to connect to PostgreSQL with error:
```
ModuleNotFoundError: No module named 'psycopg2'
```

### Root Cause
- SQLAlchemy's `create_engine()` defaults to using `psycopg2` for synchronous PostgreSQL connections
- `requirements.txt` only included `psycopg[binary,pool]>=3.2` (psycopg3)
- Module name for psycopg3 is `psycopg`, not `psycopg2`
- Health check endpoints (`/health`, `/readyz`) use synchronous SQLAlchemy connections

### Solution
Added `psycopg2-binary>=2.9` to `requirements.txt` to provide the expected PostgreSQL adapter.

## Changes

### requirements.txt
```diff
# Database
sqlalchemy>=2.0
asyncpg>=0.29
+psycopg2-binary>=2.9
psycopg[binary,pool]>=3.2
alembic>=1.13
```

### Version Bumps
- FastAPI app version: `0.6.2` → `0.6.3`
- Health endpoint version: `0.6.2` → `0.6.3`

## Validation Results

**Before v0.6.3:**
- Issues found: 19
- Issues resolved: 18
- Active blockers: 1 ❌

**After v0.6.3:**
- Issues found: 19
- Issues resolved: 19 ✅
- Active blockers: 0 ✅

## Testing Recommendations

1. **Build Docker image:**
   ```bash
   docker build -t market-data-store:v0.6.3 .
   ```

2. **Test database connectivity:**
   ```bash
   curl http://localhost:8082/health
   ```

   Expected response:
   ```json
   {
     "service": "market-data-store",
     "state": "healthy",
     "components": [
       {"name": "database", "state": "healthy"},
       {"name": "prometheus", "state": "healthy"}
     ],
     "version": "0.6.3",
     "ts": 1234567890.123
   }
   ```

3. **Verify readiness:**
   ```bash
   curl http://localhost:8082/readyz
   ```

## Deployment Notes

- **Breaking changes:** None
- **Migration required:** No
- **Rollback safe:** Yes
- **Dependencies:** Adds psycopg2-binary package

## Integration Impact

This fix enables the store service to:
- ✅ Connect to PostgreSQL databases
- ✅ Pass health checks
- ✅ Pass readiness probes
- ✅ Integrate with infra hub validation framework

## Credits

**Discovered by:** Validation Framework (Integration Testing)
**Issue type:** Runtime dependency missing
**Severity:** Critical (service non-functional without fix)

---

**Validation Framework Success Story**

This issue demonstrates the value of comprehensive integration testing. The store passed all unit tests but failed when connecting to a real PostgreSQL database. The validation framework caught this before production deployment.

🎯 **All 19 validation issues now resolved!**
