# Release v0.6.2 - API Export Fix

**Release Date:** October 21, 2025
**Type:** Patch Release
**Priority:** High (Fixes orchestrator v0.8.1 compatibility)

---

## 🐛 Critical Fix

### Issue #11: FeedbackBus Import Error

**Problem:**
Orchestrator v0.8.1 crashed at runtime with `ImportError: cannot import name 'FeedbackBus' from 'market_data_store'`

**Root Cause:**
`FeedbackBus` and related coordinator components existed in the store but were **not exported** from the top-level `market_data_store` package. They were only accessible via:
```python
from market_data_store.coordinator import FeedbackBus  # ✅ Worked
from market_data_store import FeedbackBus              # ❌ Failed
```

**Solution:**
Added top-level exports in `src/market_data_store/__init__.py` for:
- `FeedbackBus` - In-process pub/sub bus for backpressure events
- `FeedbackEvent` - Store-extended feedback event (extends Core)
- `feedback_bus()` - Singleton accessor function
- `BackpressureLevel` - Enum for backpressure severity (ok/soft/hard)
- `WriteCoordinator` - Main coordinator class

---

## 📦 What's Changed

### Exports Added
Now supports both import styles:
```python
# Option 1: Top-level import (NEW in v0.6.2)
from market_data_store import FeedbackBus, FeedbackEvent, BackpressureLevel

# Option 2: Submodule import (still works)
from market_data_store.coordinator import FeedbackBus, FeedbackEvent
```

### Compatibility Impact
- ✅ **Orchestrator v0.8.1+:** Fixed - can now import from top-level
- ✅ **Backward Compatible:** Existing submodule imports still work
- ✅ **No Breaking Changes:** Pure additive change

---

## 🔧 Technical Details

### Files Changed
1. **`src/market_data_store/__init__.py`**
   - Added imports from `market_data_store.coordinator`
   - Added `__all__` list for explicit public API
   - Updated `__version__` to `"0.6.2"`

2. **`pyproject.toml`**
   - Version bump: `0.6.1` → `0.6.2`

3. **`src/datastore/service/app.py`**
   - Version strings updated to `0.6.2`

### Exported API Surface
```python
__all__ = [
    "FeedbackBus",      # In-process event bus
    "FeedbackEvent",    # Backpressure event DTO
    "feedback_bus",     # Singleton accessor
    "BackpressureLevel", # Enum (ok/soft/hard)
    "WriteCoordinator",  # Main coordinator
]
```

---

## 🚀 Upgrade Guide

### For Orchestrator (and other consumers)

**Before (v0.6.1 - would fail):**
```python
from market_data_store import FeedbackBus  # ImportError!
```

**After (v0.6.2 - works):**
```python
from market_data_store import FeedbackBus, feedback_bus, BackpressureLevel

# Use the singleton
bus = feedback_bus()
bus.subscribe(my_handler)
```

**Migration:**
```bash
# Update dependency
pip install market-data-store>=0.6.2,<1.0.0
```

### For Store Users

No changes required - this is a pure additive fix.

---

## ✅ Verification

### Import Test
```python
# Test all new exports
from market_data_store import (
    FeedbackBus,
    FeedbackEvent,
    feedback_bus,
    BackpressureLevel,
    WriteCoordinator,
)

# Verify singleton
bus = feedback_bus()
assert isinstance(bus, FeedbackBus)
print("✅ All imports successful!")
```

### Orchestrator Compatibility
```python
# Orchestrator v0.8.1 code now works:
from market_data_store import FeedbackBus, feedback_bus

class StoreIntegration:
    def __init__(self):
        self.bus = feedback_bus()
        self.bus.subscribe(self._on_feedback)

    async def _on_feedback(self, event):
        # Handle backpressure...
        pass
```

---

## 📊 Release Checklist

- [x] Version bumped to 0.6.2
- [x] Top-level exports added
- [x] Import test passes
- [x] Backward compatibility verified
- [x] Release notes created
- [ ] Tag created (v0.6.2)
- [ ] PyPI published
- [ ] GitHub Release created

---

## 🐛 Related Issues

- **Issue #11:** FeedbackBus Import Error in Orchestrator v0.8.1
- **Affected Versions:** v0.6.0, v0.6.1
- **Fixed In:** v0.6.2

---

## 📝 Notes

### Why This Matters
The Store provides critical backpressure coordination primitives that downstream services (Pipeline, Orchestrator) need to import. Without top-level exports, consumers had to know the internal module structure, violating encapsulation.

### Design Decision
We chose to **export from top-level** rather than fix orchestrator imports because:
1. **User-Friendly:** Simpler imports for consumers
2. **Encapsulation:** Hide internal module structure
3. **Standard Practice:** Most Python packages export public API at top-level
4. **Backward Compatible:** Doesn't break existing code

### Future Considerations
In v1.0.0, we should:
- Document public API contract
- Add `py.typed` for type checking support
- Consider namespace packages for clearer structure

---

## 🎉 Summary

**v0.6.2 fixes orchestrator compatibility by exporting coordinator components at the top-level package.**

**Install:**
```bash
pip install market-data-store==0.6.2
```

**PyPI:** https://pypi.org/project/market-data-store/0.6.2/
**GitHub:** https://github.com/mjdevaccount/market-data-store/releases/tag/v0.6.2

---

**Full Changelog:** https://github.com/mjdevaccount/market-data-store/compare/v0.6.1...v0.6.2
