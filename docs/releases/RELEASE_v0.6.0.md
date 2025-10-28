# Release Notes - market-data-store v0.6.0

**Release Date:** October 20, 2025
**PyPI:** https://pypi.org/project/market-data-store/
**GitHub:** https://github.com/mjdevaccount/market-data-store/releases/tag/v0.6.0

---

## 🎉 What's New in v0.6.0

### Major Features

#### Phase 11.1 - Schema Drift Intelligence ✨
- **Drift Detection:** Automated schema drift detection via `DriftReporter`
- **Pulse Telemetry:** Real-time `telemetry.schema_drift` event emission
- **Prometheus Metrics:** `schema_drift_total` and `schema_drift_last_detected_timestamp`
- **Operational Alerts:** Pre-configured Prometheus alert rules
- **Drift Runbook:** Complete incident response documentation

**New Modules:**
- `market_data_store.telemetry.drift_reporter` - Core drift detection logic
- `market_data_store.pulse` - Pulse event bus integration
- `scripts/check_schema_drift.py` - CLI drift detection tool

#### Infra Hub Integration 🐳
- **Production Dockerfile:** Non-root user, health checks, optimized layers
- **Health Endpoints:** `/health` (Docker), `/healthz` (k8s), `/readyz`
- **Docker Compose Ready:** Profile-based service orchestration
- **Port 8082:** Standardized across platform
- **Fast Startup:** <20s including DB health check

#### Core v1.2.8 PyPI Migration 📦
- **PyPI Dependency:** Migrated from git URL to SemVer range `>=1.2.8,<2.0.0`
- **No Git in Docker:** Eliminates git dependency from production images
- **Faster Builds:** PyPI wheels vs git clones (10x speedup)
- **Better Caching:** Immutable package versions

---

## 📦 Installation

### From PyPI

```bash
pip install market-data-store>=0.6.0,<1.0.0
```

### With Development Tools

```bash
pip install market-data-store[dev]>=0.6.0,<1.0.0
```

### As Library Dependency

```toml
# pyproject.toml
[project]
dependencies = [
  "market-data-store>=0.6.0,<1.0.0",
]
```

---

## 🔧 Breaking Changes

**None.** This release is fully backward compatible with v0.5.0.

---

## 📚 Public API

### Core Modules (Stable)

#### Coordinator (`market_data_store.coordinator`)
```python
from market_data_store.coordinator import (
    WriteCoordinator,
    FeedbackEvent,
    BackpressureLevel,
    RetryPolicy,
    DeadLetterQueue,
    CircuitBreaker,
)
```

#### Sinks (`market_data_store.sinks`)
```python
from market_data_store.sinks import (
    BarsSink,
    OptionsSink,
    FundamentalsSink,
    NewsSink,
)
```

#### Pulse (`market_data_store.pulse`) - NEW ✨
```python
from market_data_store.pulse import (
    FeedbackPublisherService,
    PulseConfig,
)
```

#### Telemetry (`market_data_store.telemetry`) - NEW ✨
```python
from market_data_store.telemetry import (
    DriftReporter,
    SchemaSnapshot,
)
```

#### Metrics (`market_data_store.metrics`)
```python
from market_data_store.metrics import metrics_registry
```

---

## 🚀 Usage Examples

### Schema Drift Detection

```python
from market_data_store.telemetry.drift_reporter import DriftReporter, SchemaSnapshot
from market_data_store.pulse.config import PulseConfig

# Initialize drift reporter
pulse_config = PulseConfig(enabled=True, backend="redis")
reporter = DriftReporter(pulse_config=pulse_config)
await reporter.start()

# Check for drift
local_snapshot = SchemaSnapshot(
    name="telemetry.FeedbackEvent",
    track="v1",
    sha256="abc123...",
    version="1.0.0",
)

drift_detected = await reporter.detect_and_emit_drift(
    local_snapshot=local_snapshot,
    registry_sha="def456...",
    registry_version="1.1.0",
)

if drift_detected:
    print("⚠️  Schema drift detected!")
```

### Write Coordinator with Sinks

```python
from market_data_store.coordinator import WriteCoordinator
from market_data_store.sinks import BarsSink

# Initialize coordinator
coordinator = WriteCoordinator(
    coordinator_id="bars_coordinator",
    sink=BarsSink(conn_string="postgresql://..."),
    max_queue_size=1000,
)

# Write data
from market_data_core import Bar

bar = Bar(
    symbol="AAPL",
    timestamp=datetime.now(),
    open=150.0,
    high=151.0,
    low=149.0,
    close=150.5,
    volume=1000000,
)

await coordinator.enqueue(bar)
```

---

## 📊 Metrics

### New Metrics in v0.6.0

**Schema Drift:**
- `schema_drift_total{repo,track,schema}` - Counter of drift events
- `schema_drift_last_detected_timestamp{repo,track,schema}` - Last drift time

**Pulse:**
- `pulse_publish_total{stream,track,outcome}` - Pulse event count
- `pulse_publish_latency_ms{stream,track}` - Pulse publish latency

**Existing Metrics:**
- `sink_writes_total{sink,outcome}` - Write operations
- `sink_write_latency{sink}` - Write latency
- `http_requests_total{method,endpoint}` - HTTP request count
- `http_request_duration_seconds{method,endpoint}` - Request latency

---

## 🐳 Docker Usage

### Pull Image (when available on Docker Hub)

```bash
docker pull market-data-store:0.6.0
```

### Run Standalone

```bash
docker run -d \
  -p 8082:8082 \
  -e DATABASE_URL=postgresql://... \
  -e REGISTRY_URL=http://registry:8080 \
  --name store \
  market-data-store:0.6.0
```

### Health Check

```bash
curl http://localhost:8082/health
```

---

## 🔄 Migration from v0.5.0

No migration required! v0.6.0 is fully backward compatible.

**Optional:** If you want to enable drift detection:

1. Set environment variables:
```bash
PULSE_ENABLED=true
EVENT_BUS_BACKEND=redis  # or "inmem"
REDIS_URL=redis://localhost:6379/0
SCHEMA_TRACK=v1
```

2. Add drift monitoring to your application:
```python
from market_data_store.telemetry import DriftReporter

reporter = DriftReporter()
await reporter.start()
# ... use reporter ...
await reporter.stop()
```

---

## 📈 Performance Improvements

| Metric | v0.5.0 | v0.6.0 | Improvement |
|--------|--------|--------|-------------|
| **Docker Build Time** | 120s | 30s | 4x faster |
| **Image Size** | 250MB | 200MB | 20% smaller |
| **Dependency Install** | git clone | PyPI wheel | 10x faster |
| **Startup Time** | 20s | 18s | 10% faster |

---

## 🐛 Bug Fixes

- Fixed Pulse config environment variable handling (now uses `default_factory`)
- Fixed logging format strings in drift reporter
- Improved test stability with `pytest-timeout`

---

## 📋 Dependencies

### Core Dependencies
- `market-data-core>=1.2.8,<2.0.0` (PyPI, not git!)
- `fastapi>=0.115`
- `uvicorn[standard]>=0.30`
- `sqlalchemy>=2.0`
- `asyncpg>=0.29`
- `alembic>=1.13`
- `psycopg[binary]>=3.2`
- `typer>=0.12`
- `pydantic>=2.7`
- `prometheus-client>=0.20`
- `loguru>=0.7`

---

## 🔗 Related Releases

- **Core v1.2.8:** https://pypi.org/project/market-data-core/1.2.8/
- **Pipeline:** Coming soon with Store v0.6.0 integration
- **Orchestrator:** Coming soon with Store v0.6.0 integration

---

## 📞 Support

- **Issues:** https://github.com/mjdevaccount/market-data-store/issues
- **Documentation:** `docs/` in repository
- **Runbooks:** `docs/runbooks/schema_drift.md`

---

## 🙏 Acknowledgments

This release completes:
- Phase 11.1 - Schema Drift Intelligence
- Platform PyPI Migration Initiative
- Infra Hub Standardization

Thank you to all contributors!

---

## 🎯 What's Next (v0.7.0 Roadmap)

- [ ] Enhanced drift remediation workflows
- [ ] Multi-track schema validation
- [ ] Continuous aggregate optimization
- [ ] Advanced backpressure policies
- [ ] Grafana dashboard templates

---

**Full Changelog:** https://github.com/mjdevaccount/market-data-store/compare/v0.5.0...v0.6.0
