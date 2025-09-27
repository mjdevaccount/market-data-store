# Database Setup Guide

This guide explains how to set up the database schema and run migrations for the market-data-store control-plane.

## Prerequisites

1. PostgreSQL 13+ with TimescaleDB extension (required for time-series optimization)
2. Python 3.11+ with virtual environment activated
3. Environment variables configured

## Schema Files

The repository includes multiple schema setup options:

- **`docker/initdb.d/01_schema.sql`** - Production-ready schema with TimescaleDB, RLS, and tenant isolation
- **`docker/initdb.d/02_seed_data.sql`** - Seed data for initial setup
- **`migrations/versions/0001_initial.py`** - Alembic migration (for incremental updates)
- **`seeds/seed.sql`** - Seed data via CLI

## Environment Setup

Create a `.env` file in the project root with:

```bash
# Database Configuration
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/marketdata
ADMIN_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/marketdata

# Application Configuration
APP_PORT=8081
ADMIN_TOKEN=dev-token-change-in-production
```

## Database Initialization

### Option 1: Docker initdb (Recommended for fresh setup)

The schema is automatically applied when using Docker with the initdb scripts:

```powershell
# Start the database with initdb scripts
docker-compose up -d db

# The schema will be automatically applied from docker/initdb.d/01_schema.sql
```

### Option 2: Manual Schema Setup

For existing databases or manual setup:

```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Option 2a: Use the production schema directly
docker exec md_postgres psql -U postgres -d market_data -f /path/to/docker/initdb.d/01_schema.sql

# Option 2b: Use migrations (for incremental updates)
python -m datastore.cli migrate
```

### 3. Seed Data

Load default configuration and tenant data:

```powershell
python -m datastore.cli seed
```

### 4. Apply TimescaleDB Policies (Optional)

If using TimescaleDB for time-series optimization:

```powershell
python -m datastore.cli policies
```

## Schema Overview

The production schema (`docker/initdb.d/01_schema.sql`) creates:

### Core Tables
- `tenants` - Multi-tenant isolation
- `jobs_outbox` - Async job processing
- `api_config` - System configuration

### Fact Tables (Time-series)
- `bars` - OHLCV price data
- `fundamentals` - Financial metrics
- `news` - Market news with sentiment
- `options_snap` - Options chain snapshots

### Features
- **TimescaleDB hypertables** with optimized chunk intervals
- **Row-level security (RLS)** for tenant isolation with `app.tenant_id` session variable
- **Tenant-scoped tables** (jobs_outbox, api_config) with proper RLS policies
- **Symbol validation** (UPPER case enforcement)
- **Automatic `updated_at` triggers** on all tables
- **Optimized indexes** for time-series queries
- **Monitoring views** (latest_prices, data_freshness, job_queue_health)
- **UTC timezone** configuration

## CLI Commands

```powershell
# Show help
python -m datastore.cli --help

# Run specific migration target
python -m datastore.cli migrate 0001_initial

# Apply seed data
python -m datastore.cli seed

# Apply TimescaleDB policies
python -m datastore.cli policies
```

## Verification

After setup, verify the schema:

```sql
-- Check tables exist
\dt

-- Check RLS is enabled
SELECT schemaname, tablename, rowsecurity FROM pg_tables WHERE tablename IN ('bars', 'fundamentals', 'news', 'options_snap');

-- Check views
\dv
```
