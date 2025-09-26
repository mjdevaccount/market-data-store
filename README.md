# market-data-store

Thin **control-plane** for the market data database:

- **Migrations & policies** (TimescaleDB)
- **Admin endpoints**: health, readiness, schema/version, migrate, retention/compression, backfills, aggregates
- **Prometheus** metrics

> No bulk reads/writes via HTTP. Orchestrator writes via the `datastore` library; readers query DB directly or via a future analytics API.

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
├── src/datastore/                 # Data access, write/read ops, CLI
│   ├── __init__.py                # Package init
│   ├── cli.py                     # CLI for migrations, policies, seeds
│   ├── config.py                  # App configuration
│   ├── idempotency.py             # Conflict/idempotency helpers
│   ├── reads.py                   # Read ops (ops/tests support)
│   ├── writes.py                  # Write ops (batch/upserts)
│   └── service/                   # FastAPI service layer
│       └── app.py                 # FastAPI app with admin endpoints
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

🛠️ **CLI Commands** → [`/src/datastore/cli.py`](src/datastore/cli.py)

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

```powershell
# Run migrations
python -m datastore.cli migrate

# Apply seed data
python -m datastore.cli seed

# Apply TimescaleDB policies (optional)
python -m datastore.cli policies
```

### Dependencies

- **Production**: [`requirements.txt`](requirements.txt) - Core runtime dependencies
- **Development**: [`requirements-dev.txt`](requirements-dev.txt) - Includes dev tools (ruff, black, pre-commit)
- **Project Config**: [`pyproject.toml`](pyproject.toml) - Full project metadata and build configuration

> **Cursor**: You can regenerate this section automatically whenever the folder structure changes. The `/cursorrules/` directory is your home base for self-bootstrapping rules and automation.