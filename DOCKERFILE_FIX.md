# Critical Dockerfile Fix - Store v0.6.0

**Issue:** ModuleNotFoundError at runtime
**Root Cause:** Package installation before source code copy
**Status:** ✅ FIXED
**Commit:** `267945e`

---

## 🐛 The Problem

### Before (Broken):
```dockerfile
# Copy dependency files
COPY pyproject.toml README.md ./

# Install Python dependencies as root (for system packages)
RUN pip install --no-cache-dir -U pip wheel && \
    pip install --no-cache-dir -e .  # ❌ Nothing to install yet!

# Copy application code
COPY src/ ./src/  # ❌ Too late! pip already ran
```

**Error at Runtime:**
```
ModuleNotFoundError: No module named 'datastore'
ModuleNotFoundError: No module named 'market_data_store'
```

### Why It Failed:
1. `pip install -e .` ran **before** `src/` was copied
2. pyproject.toml references `src/` packages that don't exist yet
3. Package metadata created but no actual modules installed
4. Container starts, import fails

---

## ✅ The Fix

### After (Working):
```dockerfile
# Copy dependency files and source code
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini ./

# Install Python dependencies and package (as root)
RUN pip install --no-cache-dir -U pip wheel && \
    pip install --no-cache-dir .  # ✅ Source exists, install works!
```

### What Changed:
1. ✅ Copy **all** files first (source + config)
2. ✅ Then run `pip install .` (non-editable for production)
3. ✅ Package properly installed with all modules
4. ✅ Runtime imports work correctly

---

## 🎯 Key Improvements

### 1. Correct Order
- **Old:** Config → Install → Source ❌
- **New:** Config + Source → Install ✅

### 2. Production Install
- **Old:** `pip install -e .` (editable, needs source files)
- **New:** `pip install .` (installed to site-packages)

### 3. Benefits
- ✅ Modules properly installed in site-packages
- ✅ No dependency on /app/src at runtime
- ✅ Cleaner for production deployment
- ✅ Works with non-root user

---

## 🧪 Verification

### Test the Fix:
```bash
# Build the image
docker build -t store-test .

# Run and test imports
docker run --rm store-test python -c "
import datastore
import market_data_store
from market_data_store.coordinator import WriteCoordinator
from market_data_store.sinks import BarsSink
print('✅ All imports working!')
"

# Test the actual service
docker run --rm -p 8082:8082 \
  -e DATABASE_URL=postgresql://postgres:postgres@localhost:5432/market_data \
  store-test
```

---

## 📋 Applies To

This same fix should be applied to:
- ✅ **market-data-store** (Fixed: `267945e`)
- ⚠️ **market-data-core** (Needs same fix)
- ⚠️ **market-data-pipeline** (Check if needed)
- ⚠️ **market-data-orchestrator** (Check if needed)

---

## 🔍 Pattern to Avoid

### ❌ Wrong Order:
```dockerfile
COPY pyproject.toml ./
RUN pip install .        # Fails - no source yet
COPY src/ ./src/
```

### ✅ Correct Order:
```dockerfile
COPY pyproject.toml ./
COPY src/ ./src/         # Source first
RUN pip install .        # Then install
```

### ⚡ Optimized (Multi-stage):
```dockerfile
# Stage 1: Build dependencies
FROM python:3.11-slim AS deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir -r <(pip freeze)

# Stage 2: Install app
FROM python:3.11-slim AS app
COPY --from=deps /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY . .
RUN pip install --no-cache-dir --no-deps .
```

---

## 🎓 Lesson Learned

**Always copy source code before installing local packages!**

The order matters:
1. COPY source files
2. RUN pip install
3. Then set permissions, switch users, etc.

---

## 📊 Impact

### Before Fix:
- ❌ Docker image builds successfully
- ❌ Container starts
- ❌ Runtime crashes with ModuleNotFoundError
- ❌ Debugging required (non-obvious)

### After Fix:
- ✅ Docker image builds successfully
- ✅ Container starts
- ✅ Runtime imports work
- ✅ Service functional

---

**Status:** ✅ **RESOLVED**
**Commit:** 267945e
**Branch:** master
**Pushed:** Yes
