from fastapi import FastAPI, Response, status, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from prometheus_client import (
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
)
from loguru import logger
import time
from datastore.config import get_settings

# Core v1.2.8 telemetry contracts
from market_data_core.telemetry import HealthStatus, HealthComponent

app = FastAPI(title="market-data-store (control-plane)", version="0.6.4")

# Minimal metrics
registry = CollectorRegistry()
STORE_UP = Gauge("store_up", "Store service up (1/0)", registry=registry)
MIGRATIONS_APPLIED = Counter("migrations_applied_total", "Applied migrations", registry=registry)
REQUEST_COUNT = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint"], registry=registry
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"],
    registry=registry,
)

# Security
security = HTTPBearer()


def verify_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    settings = get_settings()
    if credentials.credentials != settings.admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")
    return credentials.credentials


# Metrics middleware
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    # Record metrics
    method = request.method
    endpoint = request.url.path
    REQUEST_COUNT.labels(method=method, endpoint=endpoint).inc()
    REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

    return response


@app.get("/health", response_model=HealthStatus)
@app.get("/healthz", response_model=HealthStatus)
async def health():
    """Health check using Core v1.2.8 HealthStatus.

    Returns structured health status with component breakdown.
    Backward compatible: old consumers can parse as dict.

    Available at both /health (Docker) and /healthz (k8s) for compatibility.
    """
    STORE_UP.set(1)

    # Check database connectivity
    db_state = "healthy"
    try:
        from sqlalchemy import create_engine, text

        settings = get_settings()
        engine = create_engine(settings.database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"DB health check failed: {e}")
        db_state = "degraded"

    # Build component list
    components = [
        HealthComponent(name="database", state=db_state),
        HealthComponent(name="prometheus", state="healthy"),
    ]

    # Determine overall state (degraded if any component is not healthy)
    overall_state = "degraded" if any(c.state != "healthy" for c in components) else "healthy"

    return HealthStatus(
        service="market-data-store",
        state=overall_state,
        components=components,
        version="0.6.4",
        ts=time.time(),
    )


@app.get("/readyz", response_model=HealthStatus)
async def readyz():
    """Readiness check using Core v1.2.8 HealthStatus.

    Stricter than /healthz - returns 503 if any component is not healthy.
    Used for k8s readiness probes.
    """
    try:
        from sqlalchemy import create_engine, text

        settings = get_settings()
        engine = create_engine(settings.database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

        components = [
            HealthComponent(name="database", state="healthy"),
        ]

        return HealthStatus(
            service="market-data-store",
            state="healthy",
            components=components,
            version="0.6.4",
            ts=time.time(),
        )
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")


@app.get("/schema/version")
def schema_version():
    # Later: read from a schema_version table or alembic head
    return {"version": "uninitialized"}


@app.post("/migrate", status_code=status.HTTP_202_ACCEPTED)
def migrate(token: str = Depends(verify_admin_token)):
    # Later: invoke Alembic upgrade programmatically
    MIGRATIONS_APPLIED.inc()
    logger.info("Requested migration apply")
    return {"status": "accepted"}


@app.post("/retention/apply", status_code=status.HTTP_202_ACCEPTED)
def retention_apply(token: str = Depends(verify_admin_token)):
    logger.info("Requested retention/compression apply")
    return {"status": "accepted"}


@app.post("/refresh/aggregate", status_code=status.HTTP_202_ACCEPTED)
def refresh_aggregate(token: str = Depends(verify_admin_token)):
    logger.info("Requested continuous aggregate refresh")
    return {"status": "accepted"}


@app.post("/backfill/{job}", status_code=status.HTTP_202_ACCEPTED)
def backfill_job(job: str, token: str = Depends(verify_admin_token)):
    logger.info(f"Requested backfill job: {job}")
    return {"status": "accepted", "job": job}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
