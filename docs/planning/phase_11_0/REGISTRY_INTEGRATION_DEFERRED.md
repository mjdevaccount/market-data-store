# Phase 11.0 - Schema Registry Integration (DEFERRED)

**Status:** ⏸️ Deferred
**Decision Date:** October 18, 2025
**Review Date:** November 15, 2025
**Owner:** Store Team

---

## 📊 Executive Summary

Schema Registry integration is **viable but NOT urgent**. We're deferring to let the infrastructure mature and Store v0.5.0 stabilize.

---

## ✅ What Exists (As of Oct 2025)

| Component | Status | Notes |
|-----------|--------|-------|
| Schema Registry Service | ✅ Local (v0.1.0) | http://localhost:8000 only |
| Core Schema Export | ✅ Complete | 38 schemas (19 v1 + 19 v2) |
| GitHub Artifacts | ✅ Available | 90-day retention |
| `telemetry.FeedbackEvent` | ✅ Both tracks | v1 and v2 exported |
| Core CI/CD | ✅ Working | Auto-export on tag push |

## ❌ What Doesn't Exist Yet

| Component | Status | Impact |
|-----------|--------|--------|
| Public Registry Deployment | ❌ Not deployed | Can't access from CI/prod |
| `core-registry-client` SDK | ❌ Doesn't exist | Would need raw HTTP |
| Production URL | ❌ Not set | No public endpoint |
| API Stability | ⚠️ Alpha | Breaking changes expected |

---

## 🤔 Why We're Waiting

### Technical Reasons

1. **Store Just Shipped v0.5.0** (Oct 17, 2025)
   - Major Pulse integration feature
   - Tests were flaky (just fixed)
   - Need stabilization period

2. **Registry Infrastructure Not Ready**
   - No public deployment
   - No client SDK
   - API still alpha

3. **Low Immediate Value**
   - Store only extends ONE Core schema
   - Current testing works fine
   - No schema drift issues

### Strategic Reasons

1. **Let Pipeline Team Go First**
   - They have more schemas to validate
   - Let them find the rough edges
   - Learn from their experience

2. **Avoid Double Work**
   - Option C (CI-only) = 6-8 hours
   - Full integration later = 20-40 hours
   - Doing both = 26-48 hours total
   - Better to wait and do full integration once

3. **Registry Will Mature**
   - Client SDK will be built
   - Public deployment will happen
   - API will stabilize
   - Documentation will improve

---

## 📅 When To Revisit

**Triggers to re-evaluate:**

- [ ] Registry deployed to production URL
- [ ] `core-registry-client` SDK published
- [ ] Pipeline successfully integrated
- [ ] Store v0.5.0 stable for 2+ weeks
- [ ] Core v2 schema migration starts
- [ ] Schema drift causes test failures

**Target Review Date:** November 15, 2025

---

## 🎯 Integration Options (When Ready)

### Option A: CI-Only Integration
**Effort:** 6-8 hours
**Value:** Medium (contract validation)
**Risk:** Low
**Dependencies:** None (uses GitHub Artifacts)

**Scope:**
- Download schemas from Core GitHub releases
- Run contract tests in CI
- No runtime integration

**Best for:** Quick wins before Registry deployment

### Option B: Full Integration
**Effort:** 20-40 hours
**Value:** High (full validation)
**Risk:** Medium
**Dependencies:** Registry deployed, SDK exists

**Scope:**
- CI contract tests
- Runtime schema validation
- Version negotiation
- Caching and monitoring

**Best for:** After Registry is production-ready

---

## 📋 Pre-Integration Checklist

Before starting integration, verify:

### Infrastructure
- [ ] Registry deployed to public URL
- [ ] Registry URL is stable (not changing)
- [ ] Registry accessible from GitHub Actions
- [ ] Registry has SLA/uptime guarantees

### SDK & Tooling
- [ ] `core-registry-client` package exists
- [ ] SDK installable via pip
- [ ] SDK documentation complete
- [ ] Example code available

### Schemas
- [ ] Core exports schemas consistently
- [ ] `telemetry.FeedbackEvent` in v1 and v2
- [ ] Schema index queryable
- [ ] Version negotiation works

### Team Readiness
- [ ] Store v0.5.0 stable in production
- [ ] 20-40 hours available for full integration
- [ ] No other critical priorities
- [ ] Team trained on Registry concepts

---

## 🔗 References

### Documentation
- **Integration Guide:** See user-provided guide (markdown in context)
- **Core Phase 11.0B:** Completion report in Core repo
- **Registry Service:** https://github.com/mjdevaccount/schema-registry-service

### Related Phases
- **Phase 10.1:** Pulse Integration (v0.5.0) - Just shipped
- **Phase 11.0A:** Schema export (Core side) - Complete
- **Phase 11.0B:** Registry artifacts (Core side) - Complete
- **Phase 11.0C:** Downstream integration (this phase) - Deferred

### Key Schemas
- `telemetry.FeedbackEvent` - Store extends this for Pulse
- `telemetry.HealthStatus` - Store publishes health
- `telemetry.RateAdjustment` - Future backpressure response

---

## 📞 Point of Contact

**Store Team:** Ready when infrastructure is
**Core Team:** Monitor for Registry deployment announcements
**Pipeline Team:** Will likely integrate first

---

## 🎬 Next Steps (When Resuming)

1. **Verify Prerequisites** (30 min)
   ```bash
   # Test Registry availability
   curl https://registry.yourdomain.com/health

   # Test SDK installation
   pip install core-registry-client

   # Verify schemas
   python -c "from core_registry_client import RegistryClient; ..."
   ```

2. **Choose Integration Path**
   - If full runtime needed → Option B (20-40 hours)
   - If just CI validation → Option A (6-8 hours)

3. **Follow Integration Guide**
   - User-provided guide is comprehensive
   - Adapt "openbb" references to "market_data"
   - Start with CI, add runtime later

---

**Decision:** Wait for Registry infrastructure maturity. Revisit in 2-4 weeks.

**Signed off:** AI Assistant (Oct 18, 2025)
**Review by:** November 15, 2025
