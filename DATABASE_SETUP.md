# Database Setup Guide

This guide explains how to set up the database schema and run migrations for the market-data-store control-plane.

## Prerequisites

1. PostgreSQL 13+ with TimescaleDB extension (optional, for time-series optimization)
2. Python 3.11+ with virtual environment activated
3. Environment variables configured

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

### 1. Run Migrations

Apply the initial schema:

```powershell
# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Run migrations
python -m datastore.cli migrate
```

### 2. Seed Data

Load default configuration and tenant data:

```powershell
python -m datastore.cli seed
```

### 3. Apply TimescaleDB Policies (Optional)

If using TimescaleDB for time-series optimization:

```powershell
python -m datastore.cli policies
```

## Schema Overview

The initial migration creates:

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
- Row-level security (RLS) for tenant isolation
- Automatic `updated_at` triggers
- Optimized indexes for time-series queries
- Views for common queries (latest_prices, data_freshness, job_queue_health)

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
