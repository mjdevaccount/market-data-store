# market-data-store

Thin **control-plane** for the market data database:
- **Migrations & policies** (TimescaleDB)
- **Admin endpoints**: health, readiness, schema/version, migrate, retention/compression, backfills, aggregates
- **Prometheus** metrics

> No bulk reads/writes via HTTP. Orchestrator writes via the `datastore` library; readers query DB directly or via a future analytics API.

## 📂 Project Layout

This section provides visibility into the repository structure for quick navigation and understanding of the codebase organization.

```bash
market-data-store/
├── alembic.ini                    # Alembic configuration for database migrations
├── docker-compose.yml             # Docker services configuration
├── Dockerfile                     # Container build instructions
├── Makefile                       # Build and deployment automation
├── pyproject.toml                 # Python project configuration and dependencies
├── README.md                      # Project documentation
├── cursorrules/                   # IDE rules and project guidelines
│   ├── index.mdc                  # Main rules index
│   ├── README.md                  # Rules documentation
│   ├── solution_manifest.json     # Asset lookup configuration
│   └── rules/                     # Task-specific rule definitions
├── docker/                        # Docker-related files
│   └── initdb.d/
│       └── 00_timescale.sql       # TimescaleDB initialization script
├── migrations/                    # Database migration files
│   ├── env.py                     # Alembic environment configuration
│   ├── script.py.mako             # Migration template
│   └── versions/                  # Migration version files
├── src/datastore/                 # Main Python package
│   ├── __init__.py                # Package initialization
│   ├── aggregates.py              # Continuous aggregates definitions
│   ├── cli.py                     # Command-line interface (migrations, policies, seeds)
│   ├── config.py                  # Application configuration and settings
│   ├── idempotency.py             # Idempotency helpers for conflict handling
│   ├── reads.py                   # Read operation helpers (minimal, for ops/tests)
│   ├── timescale_policies.py      # TimescaleDB retention/compression policies
│   ├── writes.py                  # Write operations (upserts/batch writers)
│   └── service/                   # FastAPI service layer
│       └── app.py                 # FastAPI application with admin endpoints
└── tools/                         # Development and build tools
    └── build_solution_manifest.py # Solution manifest builder
```