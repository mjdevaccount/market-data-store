# market-data-store

Thin **control-plane** for the market data database:
- **Migrations & policies** (TimescaleDB)
- **Admin endpoints**: health, readiness, schema/version, migrate, retention/compression, backfills, aggregates
- **Prometheus** metrics

> No bulk reads/writes via HTTP. Orchestrator writes via the `datastore` library; readers query DB directly or via a future analytics API.

## 📂 Project Layout & Description

This repository is structured as a **control-plane** with clear separation between infrastructure, database schema management, service layer, and automation rules. Below is a snapshot of the repo's structure with logical groupings to help new contributors and automation tools navigate the codebase.

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
├── alembic.ini                    # Alembic configuration for database migrations
├── migrations/                    # Alembic migration files
│   ├── env.py                     # Alembic environment configuration
│   ├── script.py.mako             # Migration template
│   └── versions/                  # Migration version files
├── src/datastore/aggregates.py    # Continuous aggregates definitions
└── src/datastore/timescale_policies.py # TimescaleDB retention/compression policies
```

### 🚀 **Service Layer**
```bash
├── src/datastore/                 # Data access, read/write, CLI for migrations
│   ├── __init__.py                # Package initialization
│   ├── cli.py                     # Command-line interface (migrations, policies, seeds)
│   ├── config.py                  # Application configuration and settings
│   ├── idempotency.py             # Idempotency helpers for conflict handling
│   ├── reads.py                   # Read operation helpers (minimal, for ops/tests)
│   ├── writes.py                  # Write operations (upserts/batch writers)
│   └── service/                   # FastAPI service layer
│       └── app.py                 # FastAPI application with admin endpoints
```

### 🤖 **Automation Rules**
```bash
├── cursorrules/                   # Cursor rules definitions (where Cursor lives)
│   ├── index.mdc                  # Main rules index
│   ├── README.md                  # Rules documentation
│   ├── solution_manifest.json     # Asset lookup configuration
│   └── rules/                     # Task-specific rule definitions
```

### 🧭 **How to Navigate**

- **Adding DB migrations** → Go to `/migrations/versions/`
- **Exposing admin endpoints** → Go to `/src/datastore/service/app.py`
- **Database policies & aggregates** → Check `/src/datastore/timescale_policies.py` and `/src/datastore/aggregates.py`
- **CLI commands** → Modify `/src/datastore/cli.py`
- **Cursor rules & automation** → Update `/cursorrules/` (this is where Cursor lives and can self-bootstrap)
- **Docker & deployment** → Check `/docker/`, `/Dockerfile`, `/docker-compose.yml`
- **Project configuration** → Update `/pyproject.toml`

> **Cursor**: You can regenerate this section automatically when the folder structure changes. The `/cursorrules/` directory is your home base for self-bootstrapping rules and automation.