# Market Data Store - Infra Integration Guide

**Service:** market-data-store
**Role:** Control-plane API for schema management, migrations, policies
**Port:** 8082
**Docker Image:** `market-data-store:latest`

---

## 🐳 Docker Setup

### Dockerfile Specifications

- **Base Image:** `python:3.11-slim`
- **User:** Non-root (`appuser`)
- **Port:** 8082
- **Health Check:** `GET /health` (10s interval, 3 retries)
- **Startup Time:** ~20s (includes DB connection check)

### Build & Run Locally

```bash
# Build image
docker build -t market-data-store:latest .

# Run standalone (requires Postgres)
docker run -d \
  -p 8082:8082 \
  -e DATABASE_URL=postgresql://postgres:postgres@postgres:5432/market_data \
  -e REGISTRY_URL=http://registry:8080 \
  -e REGISTRY_TRACK=v1 \
  --name store \
  market-data-store:latest

# Check health
curl http://localhost:8082/health
```

---

## 🏗️ Compose Integration

### Service Definition

Store is defined in `market_data_infra/docker-compose.yml` with:

```yaml
store:
  build: ../market-data-store
  container_name: store
  environment:
    DATABASE_URL: postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
    REGISTRY_URL: ${REGISTRY_URL}
    REGISTRY_TRACK: ${REGISTRY_TRACK}
  ports: ["8082:8082"]
  depends_on:
    postgres:
      condition: service_healthy
    registry:
      condition: service_healthy
  healthcheck:
    test: ["CMD-SHELL", "curl -fsS http://localhost:8082/health || exit 1"]
    interval: 10s
    timeout: 3s
    retries: 10
  networks: [mdnet]
  profiles: ["store"]
```

### Start Store

```bash
# From market_data_infra directory
cd ../market_data_infra

# Start Store + dependencies (DB + Registry)
make up-store

# Check status
docker compose ps

# View logs
docker compose logs store -f

# Stop Store
make down-store
```

---

## 🔌 Endpoints

### Health & Readiness

| Endpoint | Method | Purpose | Response |
|----------|--------|---------|----------|
| `/health` | GET | Liveness probe (Docker) | 200 OK |
| `/healthz` | GET | Liveness probe (k8s) | 200 OK |
| `/readyz` | GET | Readiness probe | 200/503 |
| `/metrics` | GET | Prometheus metrics | text/plain |

**Health Response:**
```json
{
  "service": "market-data-store",
  "state": "healthy",
  "components": [
    {"name": "database", "state": "healthy"},
    {"name": "prometheus", "state": "healthy"}
  ],
  "version": "0.5.0",
  "ts": 1697654321.123
}
```

### Control Plane API

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/schema/version` | GET | None | Get current schema version |
| `/migrate` | POST | Admin Token | Trigger migrations |
| `/retention/apply` | POST | Admin Token | Apply retention policies |
| `/refresh/aggregate` | POST | Admin Token | Refresh continuous aggregates |
| `/backfill/{job}` | POST | Admin Token | Trigger backfill job |

**Authentication:**
```bash
# Admin endpoints require Bearer token
curl -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -X POST http://localhost:8082/migrate
```

---

## 🔧 Configuration

### Required Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | **Required** | Postgres connection string |
| `REGISTRY_URL` | `http://registry:8080` | Schema Registry URL |
| `REGISTRY_TRACK` | `v1` | Schema track to use |
| `PORT` | `8082` | Service port |

### Optional Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ADMIN_TOKEN` | `iamalive` | Admin API authentication |
| `LOG_LEVEL` | `INFO` | Logging level |
| `PULSE_ENABLED` | `true` | Enable Pulse telemetry |
| `EVENT_BUS_BACKEND` | `inmem` | Event bus backend |

### Example .env (in market_data_infra)

```bash
# Database
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/market_data
POSTGRES_DB=market_data
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# Store
STORE_URL=http://store:8082
ADMIN_TOKEN=iamalive

# Registry
REGISTRY_URL=http://registry:8080
REGISTRY_TRACK=v1
```

---

## 🏥 Health Checks

### Docker Health Check

Dockerfile includes built-in health check:
```dockerfile
HEALTHCHECK --interval=10s --timeout=3s --retries=3 --start-period=20s \
  CMD curl -fsS http://localhost:8082/health || exit 1
```

### Manual Health Verification

```bash
# Basic health
curl http://localhost:8082/health

# Detailed health with components
curl http://localhost:8082/health | jq '.'

# Readiness (strict)
curl http://localhost:8082/readyz

# Prometheus metrics
curl http://localhost:8082/metrics
```

### Expected Health States

| State | Condition | Action |
|-------|-----------|--------|
| `healthy` | All components OK | None |
| `degraded` | DB slow/unreachable | Investigate DB connection |
| `503` | Service not ready | Wait for startup, check logs |

---

## 📊 Monitoring

### Prometheus Metrics

Store exposes metrics at `/metrics`:

**Service Metrics:**
- `store_up` - Service availability (gauge)
- `migrations_applied_total` - Migration count (counter)
- `http_requests_total{method,endpoint}` - Request count (counter)
- `http_request_duration_seconds{method,endpoint}` - Request latency (histogram)

**Drift Metrics (Phase 11.1):**
- `schema_drift_total{repo,track,schema}` - Drift event count (counter)
- `schema_drift_last_detected_timestamp{repo,track,schema}` - Last drift time (gauge)

**Sink Metrics:**
- `sink_writes_total{sink,outcome}` - Write count (counter)
- `sink_write_latency{sink}` - Write latency (histogram)

**Pulse Metrics:**
- `pulse_publish_total{stream,track,outcome}` - Pulse events (counter)
- `pulse_publish_latency_ms{stream,track}` - Pulse latency (histogram)

### Grafana Integration

Store metrics are scraped by Prometheus (configured in `market_data_infra/monitoring/prometheus/prometheus.yml`):

```yaml
scrape_configs:
  - job_name: 'market-data-services'
    static_configs:
      - targets:
          - 'store:8082'
```

Metrics are accessible in Grafana via the `Prometheus` datasource.

---

## 🐛 Troubleshooting

### Container Won't Start

```bash
# Check logs
docker compose logs store

# Common issues:
# 1. Database not ready
docker compose ps postgres  # Should be "healthy"

# 2. Port already in use
lsof -i :8082  # Check what's using port 8082

# 3. Build failed
docker compose build --no-cache store
```

### Health Check Failing

```bash
# Check if service is responding
docker exec store curl -v http://localhost:8082/health

# Check database connectivity
docker exec store psql $DATABASE_URL -c "SELECT 1"

# Review service logs
docker compose logs store --tail=50
```

### Permission Errors

Store runs as non-root user `appuser`. If you see permission errors:

```bash
# Rebuild with correct ownership
docker compose build --no-cache store

# Verify user
docker exec store id
# Should show: uid=999(appuser) gid=999(appuser)
```

---

## 🚀 Deployment Checklist

Before deploying Store in infra hub:

- [x] **Dockerfile:** Production-ready with non-root user
- [x] **Health Endpoint:** `/health` responds correctly
- [x] **Metrics Endpoint:** `/metrics` exposes Prometheus metrics
- [x] **Dependencies:** Requires Postgres + Registry
- [x] **Port:** Configured for 8082
- [x] **Environment:** Reads from .env correctly
- [x] **Logging:** Uses loguru for structured logs
- [x] **Startup Time:** <20s with DB check
- [x] **Graceful Shutdown:** Handles SIGTERM

---

## 📚 Related Documentation

- **Phase 11.1 Implementation:** `PHASE_11.1_STORE_IMPLEMENTATION.md`
- **Drift Runbook:** `docs/runbooks/schema_drift.md`
- **Alert Rules:** `docs/alerts/prometheus_drift_alerts.yml`
- **Platform Overview:** `../market_data_infra/PLATFORM_OVERVIEW.md`
- **API Service:** `src/datastore/service/app.py`

---

## 🔗 Service Dependencies

```
Store depends on:
├── postgres (required, health check)
│   └── Port: 5432
│   └── Healthcheck: pg_isready
├── registry (required, health check)
│   └── Port: 8080
│   └── Healthcheck: GET /health
└── prometheus (optional, for metrics)
    └── Port: 9090
    └── Scrapes: GET /metrics

Store provides to:
├── pipeline (database writes)
├── orchestrator (control plane API)
└── prometheus (metrics scraping)
```

---

## ✅ Integration Status

| Component | Status | Notes |
|-----------|--------|-------|
| **Dockerfile** | ✅ Ready | Non-root user, health check |
| **Health Endpoint** | ✅ Ready | `/health` and `/healthz` both available |
| **Metrics Endpoint** | ✅ Ready | Prometheus-compatible |
| **Compose Profile** | ✅ Ready | Profile: `store` |
| **Environment Config** | ✅ Ready | Reads from `.env` |
| **Dependencies** | ✅ Ready | Postgres + Registry health checks |
| **Documentation** | ✅ Ready | This file |

**Status:** ✅ **READY FOR INFRA HUB INTEGRATION**

---

**Last Updated:** October 18, 2025
**Version:** 0.5.0
**Maintainer:** Store Team
