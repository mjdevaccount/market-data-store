# market-data-store

**Control-plane** for the market data database with **client library** for Market Data Core:

- **Migrations & policies** (TimescaleDB)
- **Admin endpoints**: health, readiness, schema/version, migrate, retention/compression, backfills, aggregates
- **Prometheus** metrics
- **`mds_client` library**: Production-ready Python client for Market Data Core with sync/async APIs, RLS, and tenant isolation

> The `mds_client` library provides direct in-process access for Market Data Core. No HTTP latency - Core imports and uses the library directly with connection pooling, RLS, and TimescaleDB integration.

## 📂 Project Layout & Description

This repository is structured as a **control-plane** with clear separation between infrastructure, schema management, service layer, and automation rules.

Below is a snapshot of the repo's structure with logical groupings to help new contributors and automation tools (like Cursor) navigate effectively.

### 🏗️ **Infra & Ops**
```bash
├── docker-compose.yml             # Docker services configuration
├── Dockerfile                     # Container build instructions
├── Makefile                       # Build and deployment automation
├── docker/                        # Docker-related files
│   └── initdb.d/                  # Initial SQL scripts for DB setup
│       └── 00_timescale.sql       # TimescaleDB initialization script
└── tools/                         # Auxiliary scripts, CLI utilities
    └── build_solution_manifest.py # Solution manifest builder
```

### 🗄️ **Schema & Migrations**
```bash
├── alembic.ini                         # Alembic configuration for migrations
├── migrations/                         # Alembic migration files
│   ├── env.py                          # Migration environment config
│   ├── script.py.mako                  # Migration template
│   └── versions/                       # Migration version files
├── src/datastore/aggregates.py         # Continuous aggregates definitions
└── src/datastore/timescale_policies.py # TimescaleDB retention/compression policies
```

### 🚀 **Service Layer**
```bash
├── src/datastore/                 # Control-plane: migrations, policies, admin endpoints
│   ├── __init__.py                # Package init
│   ├── cli.py                     # CLI for migrations, policies, seeds
│   ├── config.py                  # App configuration
│   ├── idempotency.py             # Conflict/idempotency helpers
│   ├── reads.py                   # Read ops (ops/tests support)
│   ├── writes.py                  # Write ops (batch/upserts)
│   └── service/                   # FastAPI service layer
│       └── app.py                 # FastAPI app with admin endpoints
└── src/mds_client/                # Client library for Market Data Core
    ├── __init__.py                # Library exports (MDS, AMDS, models)
    ├── client.py                  # Sync/async client facades
    ├── models.py                  # Pydantic data models
    ├── sql.py                     # SQL statements with conflict resolution
    ├── rls.py                     # Row Level Security helpers
    ├── errors.py                  # Structured exception hierarchy
    ├── utils.py                   # Time/size helpers, batch utilities
    ├── batch.py                   # High-throughput batch processing
    └── cli.py                     # Operational CLI commands
```

### 🤖 **Automation Rules**
```bash
├── cursorrules/                   # Cursor rules (automation home base)
│   ├── index.mdc                  # Main rules index
│   ├── README.md                  # Rules documentation
│   ├── solution_manifest.json     # Asset lookup configuration
│   └── rules/                     # Task-specific rule definitions
```

### 🧭 **How to Navigate**

🗄️ **DB Migrations** → [`/migrations/versions/`](migrations/versions/)

🚀 **Admin Endpoints** → [`/src/datastore/service/app.py`](src/datastore/service/app.py)

📊 **Policies & Aggregates** → [`/src/datastore/timescale_policies.py`](src/datastore/timescale_policies.py), [`/src/datastore/aggregates.py`](src/datastore/aggregates.py)

🛠️ **Control-plane CLI** → [`/src/datastore/cli.py`](src/datastore/cli.py)

📦 **Client Library** → [`/src/mds_client/`](src/mds_client/) - For Market Data Core integration

🔧 **Client CLI** → [`/src/mds_client/cli.py`](src/mds_client/cli.py) - Operational commands (`mds` command)

🤖 **Cursor Rules & Automation** → [`/cursorrules/`](cursorrules/) (Cursor's self-bootstrap home)

🏗️ **Infra & Deployment** → [`/docker/`](docker/), [`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml)

⚙️ **Project Config** → [`pyproject.toml`](pyproject.toml)

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 13+ (with TimescaleDB extension optional)
- Virtual environment

### Installation

```powershell
# Clone and setup
git clone <repository>
cd market-data-store

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# For development
pip install -r requirements-dev.txt
```

### Database Setup

**Option 1: Using Docker initdb (Recommended for fresh setup)**
```powershell
# The schema will be automatically applied when the database container starts
# if using docker-compose with the initdb.d scripts
```

**Option 2: Manual setup**
```powershell
# Run migrations (for existing databases)
python -m datastore.cli migrate

# Apply seed data
python -m datastore.cli seed

# Apply TimescaleDB policies (optional)
python -m datastore.cli policies
```

**Option 3: Fresh schema setup**
```powershell
# For a completely fresh database, you can use the production schema directly
# See DATABASE_SETUP.md for detailed instructions
```

## 📦 Client Library Usage

The `mds_client` library provides production-ready APIs for Market Data Core:

### For Market Data Core (Async)
```python
from mds_client import AMDS, Bar

# Configuration with tenant isolation
amds = AMDS({
    "dsn": "postgresql://user:pass@host:port/db?options=-c%20app.tenant_id%3D<uuid>",
    "pool_max": 10
})

# Write market data
await amds.upsert_bars([Bar(
    tenant_id="uuid", vendor="ibkr", symbol="AAPL", timeframe="1m",
    ts=now, close_price=150.5, volume=1000
)])

# Get latest prices for hot cache
prices = await amds.latest_prices(["AAPL", "MSFT"], vendor="ibkr")
```

### For Operations (Sync CLI)
```bash
# Health check
mds ping --dsn "postgresql://..." --tenant-id "uuid"

# Write data
mds write-bar --dsn "..." --tenant-id "uuid" --vendor "ibkr" \
  --symbol "AAPL" --timeframe "1m" --ts "2024-01-01T10:00:00" \
  --close-price 150.5

# Get latest prices
mds latest-prices --dsn "..." --vendor "ibkr" --symbols "AAPL,MSFT"
```

### Key Features
- **Dual API**: Sync (`MDS`) and async (`AMDS`) facades
- **RLS Integration**: Automatic tenant isolation via DSN options
- **TimescaleDB Compatible**: Composite primary keys with time columns first
- **Connection Pooling**: Production-ready with psycopg 3
- **Batch Processing**: High-throughput ingestion with size/time-based flushing
- **Structured Errors**: Comprehensive exception hierarchy with retry logic

### Dependencies

- **Production**: [`requirements.txt`](requirements.txt) - Core runtime dependencies
- **Development**: [`requirements-dev.txt`](requirements-dev.txt) - Includes dev tools (ruff, black, pre-commit)
- **Project Config**: [`pyproject.toml`](pyproject.toml) - Full project metadata and build configuration

> **Cursor**: You can regenerate this section automatically whenever the folder structure changes. The `/cursorrules/` directory is your home base for self-bootstrapping rules and automation.
