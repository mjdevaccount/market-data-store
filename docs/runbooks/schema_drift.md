# Schema Drift Resolution Runbook

**Service:** market-data-store
**Component:** Schema Drift Detection (Phase 11.1)
**Severity:** Low to Medium
**On-Call:** Store Team

---

## 📋 Overview

This runbook guides you through resolving schema drift alerts when Store's local schema fixtures diverge from the live Schema Registry.

**What is Schema Drift?**
- Store maintains local copies of schemas in `tests/fixtures/schemas/`
- Registry hosts the canonical schemas at https://schema-registry-service.fly.dev
- Drift occurs when SHA256 hashes don't match

**Why It Matters:**
- Ensures Store's extended models (e.g., `FeedbackEvent`) remain compatible with Core
- Prevents runtime failures from schema mismatches
- Enables safe schema evolution across repos

---

## 🚨 Alert Types

### 1. CriticalSchemaDriftSustained

**Severity:** Warning
**Condition:** FeedbackEvent schema drifted >30 minutes
**Impact:** Moderate - May indicate breaking change incoming

**Alert Example:**
```
FeedbackEvent schema drift sustained >30m
Repo: market-data-store
Schema: telemetry.FeedbackEvent
Track: v1
Last detected: 2025-10-18T14:30:00Z
```

### 2. SchemaDriftActive

**Severity:** Info
**Condition:** Any schema drifted >1 hour
**Impact:** Low - Informational

### 3. HighDriftRate

**Severity:** Warning
**Condition:** Multiple schemas drifting rapidly (>0.1 drifts/sec over 15m)
**Impact:** Medium - May indicate Registry bulk update

---

## 🔍 Investigation Steps

### Step 1: Check Current Drift Status

```bash
# SSH to Store environment (or check CI logs)
cd /path/to/market-data-store

# Activate venv
.\.venv\Scripts\Activate.ps1  # Windows
source .venv/bin/activate      # Linux/Mac

# Run drift check
python scripts/check_schema_drift.py \
  --track v1 \
  --registry-url https://schema-registry-service.fly.dev \
  --output drift_report.json

# Review report
cat drift_report.json | jq '.'
```

**Expected Output:**
```json
{
  "track": "v1",
  "total_schemas": 3,
  "synced": 2,
  "drifted": 1,
  "schemas": [
    {
      "schema": "telemetry.FeedbackEvent",
      "status": "drift",
      "local_sha": "abc123def456",
      "registry_sha": "xyz789abc123",
      "local_version": "1.0.0",
      "registry_version": "1.1.0"
    }
  ]
}
```

### Step 2: Compare Schema Contents

```bash
# Fetch current Registry schema
python scripts/fetch_registry_schemas.py \
  --track v1 \
  --output /tmp/registry_schemas

# Compare with local
diff tests/fixtures/schemas/telemetry.FeedbackEvent.json \
     /tmp/registry_schemas/telemetry.FeedbackEvent.json
```

**Look for:**
- Added required fields (BREAKING)
- Removed fields (BREAKING)
- Added optional fields (SAFE)
- Changed field types (BREAKING)
- Documentation changes (SAFE)

### Step 3: Check Registry Changelog

```bash
# Query Registry for recent changes
curl https://schema-registry-service.fly.dev/schemas/v1/telemetry.FeedbackEvent | jq '.version, .updated_at'

# Check Core repo for related commits
# https://github.com/mjdevaccount/market-data-core/commits/master
```

### Step 4: Review Store's Extended Model

```bash
# Check Store's FeedbackEvent extension
cat src/market_data_store/coordinator/feedback.py | grep -A 20 "class FeedbackEvent"
```

**Verify:**
- Store only adds optional fields (never removes Core fields)
- Store's extensions use `Field(default=...)` for backward compatibility
- No conflicting field names

---

## ✅ Resolution Procedures

### Scenario A: Registry Updated (Expected Change)

**Situation:** Core published new schema version; Store needs to sync.

**Steps:**

1. **Fetch Updated Schemas:**
   ```bash
   python scripts/fetch_registry_schemas.py \
     --track v1 \
     --output tests/fixtures/schemas
   ```

2. **Run Contract Tests:**
   ```bash
   pytest tests/contracts/test_registry_schemas.py -v
   ```

3. **If Tests Pass:**
   ```bash
   git add tests/fixtures/schemas/
   git commit -m "fix: sync schemas with Registry v1.X.X"
   git push
   ```

4. **If Tests Fail:**
   - Review failures: likely Store's extension is incompatible
   - Update `src/market_data_store/coordinator/feedback.py`
   - Re-run tests
   - Commit both schema and code changes

5. **Verify Drift Resolved:**
   ```bash
   python scripts/check_schema_drift.py --track v1
   # Should show: "✅ All schemas synced"
   ```

**Time Estimate:** 15-30 minutes

---

### Scenario B: Store Out of Sync (Unintentional)

**Situation:** Local fixtures were manually edited or corrupted.

**Steps:**

1. **Verify Registry is Authoritative:**
   ```bash
   # Check Registry health
   curl https://schema-registry-service.fly.dev/health

   # Check Core repo for corresponding schema
   # https://github.com/mjdevaccount/market-data-core/blob/master/schemas/...
   ```

2. **Force Sync from Registry:**
   ```bash
   # Backup current fixtures
   cp -r tests/fixtures/schemas tests/fixtures/schemas.backup

   # Re-fetch from Registry
   python scripts/fetch_registry_schemas.py \
     --track v1 \
     --output tests/fixtures/schemas \
     --force  # Overwrite existing
   ```

3. **Run Full Test Suite:**
   ```bash
   pytest tests/ -v
   ```

4. **Commit Fix:**
   ```bash
   git add tests/fixtures/schemas/
   git commit -m "fix: restore schemas from Registry (corrupted local copy)"
   git push
   ```

**Time Estimate:** 10-15 minutes

---

### Scenario C: Registry Error (Potential Regression)

**Situation:** Registry published incorrect schema; Store is actually correct.

**Steps:**

1. **Verify Store is Correct:**
   ```bash
   # Compare with Core source of truth
   cd /path/to/market-data-core
   git log --oneline -- schemas/v1/telemetry.FeedbackEvent.schema

   # Check if recent Core commit matches Store's local copy
   ```

2. **If Registry is Wrong:**
   - **Escalate to Core/Registry team immediately**
   - Create GitHub issue: https://github.com/mjdevaccount/market-data-core/issues/new
   - Ping #core-team in Slack

3. **Temporary Workaround:**
   ```bash
   # Disable drift alerts temporarily (Prometheus)
   # Add silence in Prometheus UI:
   #   Matchers: alertname="CriticalSchemaDriftSustained", schema="telemetry.FeedbackEvent"
   #   Duration: 4 hours
   ```

4. **Once Registry Fixed:**
   - Re-fetch schemas
   - Verify drift cleared
   - Remove Prometheus silence

**Time Estimate:** 1-4 hours (depends on Core team response)

---

### Scenario D: Breaking Change in Registry

**Situation:** Registry published a breaking change; Store needs urgent update.

**Steps:**

1. **Assess Impact:**
   ```bash
   # Check which Store models use the changed schema
   grep -r "FeedbackEvent" src/market_data_store/ tests/

   # Review Store's usage patterns
   ```

2. **Update Store Code:**
   ```python
   # Example: Registry added required field "new_field"
   # Update Store's FeedbackEvent extension:

   class FeedbackEvent(CoreFeedback):
       reason: str | None = Field(default=None, description="...")
       new_field: str = Field(default="default_value", description="...")  # ADD THIS
   ```

3. **Update Tests:**
   ```python
   # Update fixtures in tests/
   # Add new_field to all FeedbackEvent test cases
   ```

4. **Comprehensive Testing:**
   ```bash
   pytest tests/ -v --tb=short
   ```

5. **Emergency Deploy:**
   ```bash
   git add -A
   git commit -m "URGENT: adapt to FeedbackEvent breaking change (Registry v1.X.X)"
   git push
   # Trigger immediate deployment
   ```

**Time Estimate:** 1-3 hours (depending on change complexity)

---

## 🛠️ Tools & Commands

### Quick Drift Check
```bash
python scripts/check_schema_drift.py --track v1 | tail -10
```

### Fetch Latest Schemas
```bash
python scripts/fetch_registry_schemas.py --track v1
```

### Compare Specific Schema
```bash
diff <(curl -s https://schema-registry-service.fly.dev/schemas/v1/telemetry.FeedbackEvent | jq '.content') \
     <(cat tests/fixtures/schemas/telemetry.FeedbackEvent.json | jq '.')
```

### Check Prometheus Metrics
```bash
# Drift count per schema
curl -s 'http://prometheus:9090/api/v1/query?query=schema_drift_total' | jq '.data.result'

# Last drift timestamp
curl -s 'http://prometheus:9090/api/v1/query?query=schema_drift_last_detected_timestamp' | jq '.data.result'
```

### Manual Pulse Event Emission (Testing)
```bash
# Test drift reporter locally
python -c "
import asyncio
from market_data_store.telemetry.drift_reporter import DriftReporter, SchemaSnapshot
from market_data_store.pulse.config import PulseConfig

async def test():
    config = PulseConfig(enabled=True, backend='inmem')
    reporter = DriftReporter(pulse_config=config)
    await reporter.start()

    snap = SchemaSnapshot('test.schema', 'v1', 'local_hash', '1.0.0')
    await reporter.detect_and_emit_drift(snap, 'registry_hash', '1.1.0')

    await reporter.stop()

asyncio.run(test())
"
```

---

## 📊 Post-Incident Review

After resolving drift:

1. **Update Drift Log:**
   ```bash
   # Document in docs/incidents/drift_YYYYMMDD.md
   ```

2. **Review Metrics:**
   - How long was drift active?
   - How many alerts fired?
   - Time to resolution?

3. **Process Improvements:**
   - Could drift have been prevented?
   - Should alert thresholds change?
   - Documentation gaps?

4. **Communicate:**
   - Update team in #store-team Slack
   - If breaking change: notify dependent teams

---

## 🚨 Emergency Contacts

| Role | Contact | Method |
|------|---------|--------|
| **Registry On-Call** | Registry Team | PagerDuty (if configured) |
| **Core Schema Owner** | @core-maintainer | GitHub + Slack #core-team |
| **Store Team Lead** | @store-lead | Slack #store-team |
| **DevOps** | @devops | Slack #infrastructure |

---

## 📚 Related Documentation

- [Phase 11.1 Implementation](../../PHASE_11.1_STORE_IMPLEMENTATION.md)
- [Go-Live Checklist](../../PHASE_11.1_STORE_GO_LIVE_CHECKLIST.md)
- [Prometheus Alert Rules](../alerts/prometheus_drift_alerts.yml)
- [Registry API Docs](https://schema-registry-service.fly.dev/docs)
- [Contract Tests](../../tests/contracts/test_registry_schemas.py)

---

## 🎓 Training Resources

**New to Schema Drift?**
1. Read: [Phase 11.1 Implementation](../../PHASE_11.1_STORE_IMPLEMENTATION.md)
2. Watch: Internal "Schema Evolution" training video
3. Practice: Run `check_schema_drift.py` locally
4. Shadow: Observe veteran resolving drift incident

**Key Concepts:**
- **SHA256 Hash:** Cryptographic fingerprint of schema content
- **Track:** Schema version line (v1 stable, v2 preview)
- **Drift:** Mismatch between local and Registry hashes
- **Fail-Open:** System continues operating even if Registry is down

---

**Runbook Version:** 1.0
**Last Updated:** October 18, 2025
**Next Review:** After first major drift incident
**Feedback:** Open PR against this file or ping #store-team
