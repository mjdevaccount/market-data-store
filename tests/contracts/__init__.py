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
