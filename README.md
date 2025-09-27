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
    ├── __init__.py                # Library exports (MDS, AMDS, models, batch processors)
    ├── client.py                  # MDS (sync client facade) with psycopg 3 + ConnectionPool
    ├── aclient.py                 # AMDS (async client facade) with AsyncConnectionPool
    ├── models.py                  # Pydantic data models with validation
    ├── sql.py                     # Canonical SQL with named parameters and ON CONFLICT upserts
    ├── rls.py                     # Row Level Security helpers (DSN options + context managers)
    ├── errors.py                  # Structured exception hierarchy with psycopg error mapping
    ├── utils.py                   # NDJSON processing with gzip support and model coercion
    ├── batch.py                   # Production-safe batch processing (sync + async)
    └── cli.py                     # Comprehensive operational CLI with environment variables
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
- PostgreSQL 13+ with **TimescaleDB extension** (required)
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
# After a fresh initdb bootstrap, stamp Alembic to prevent migration conflicts:
python -m datastore.cli stamp-head

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

# Environment variable support
export MDS_DSN="postgresql://user:pass@host:port/db"
export MDS_TENANT_ID="uuid-string"
mds ping  # Uses env vars automatically
```

## 📚 Client Library Documentation

### 🏗️ Architecture Overview

The `mds_client` library provides a production-ready Python client for Market Data Core with two main facades:

- **`MDS`** - Synchronous client for operations and simple integrations
- **`AMDS`** - Asynchronous client for high-performance Market Data Core

Both clients support:
- **Row Level Security (RLS)** with tenant isolation via DSN options or context managers
- **Connection pooling** with psycopg 3 + psycopg_pool (ConnectionPool/AsyncConnectionPool)
- **TimescaleDB integration** with time-first composite primary keys and idempotent upserts
- **Statement timeouts** with per-connection configuration
- **Structured error handling** with psycopg error mapping and retry logic
- **Job outbox pattern** with idempotency key support
- **Performance optimization** with multiple write modes: `executemany` (default), `execute_values` (sync), and `COPY` (fastest)

### 📊 Data Models

The library provides strict Pydantic models for all market data types:

#### [`Bar`](src/mds_client/models.py#L15-L35) - OHLCV Market Data
```python
class Bar(BaseModel):
    tenant_id: str                    # UUID for tenant isolation
    vendor: str                       # Data provider (e.g., "ibkr", "alpha_vantage")
    symbol: str                       # Trading symbol (auto-uppercased)
    timeframe: str                    # Time aggregation ("1m", "5m", "1h", "1d")
    ts: datetime                      # Timestamp (UTC)
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    close_price: Optional[float] = None
    volume: Optional[int] = None
    id: Optional[str] = None          # UUID (not globally unique)
```

#### [`Fundamentals`](src/mds_client/models.py#L38-L50) - Company Financials
```python
class Fundamentals(BaseModel):
    tenant_id: str
    vendor: str
    symbol: str
    asof: datetime                    # As-of date for financial data
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    net_income: Optional[float] = None
    eps: Optional[float] = None       # Earnings per share
    id: Optional[str] = None
```

#### [`News`](src/mds_client/models.py#L53-L66) - Market News & Sentiment
```python
class News(BaseModel):
    tenant_id: str
    vendor: str
    published_at: datetime            # Publication timestamp
    title: str                        # News headline
    id: Optional[str] = None
    symbol: Optional[str] = None      # Related symbol (if applicable)
    url: Optional[str] = None         # Source URL
    sentiment_score: Optional[float] = None  # -1.0 to 1.0 sentiment
```

#### [`OptionSnap`](src/mds_client/models.py#L69-L90) - Options Market Data
```python
class OptionSnap(BaseModel):
    tenant_id: str
    vendor: str
    symbol: str
    expiry: date                      # Option expiration date
    option_type: str                  # "C" for call, "P" for put
    strike: float                     # Strike price
    ts: datetime                      # Snapshot timestamp
    iv: Optional[float] = None        # Implied volatility
    delta: Optional[float] = None     # Option delta
    gamma: Optional[float] = None     # Option gamma
    oi: Optional[int] = None          # Open interest
    volume: Optional[int] = None      # Trading volume
    spot: Optional[float] = None      # Underlying spot price
    id: Optional[str] = None
```

#### [`LatestPrice`](src/mds_client/models.py#L93-L100) - Real-time Price Snapshots
```python
class LatestPrice(BaseModel):
    tenant_id: str
    vendor: str
    symbol: str
    price: float                      # Latest price
    price_timestamp: datetime         # When price was recorded
```

### 🔧 Configuration

#### Client Configuration
```python
# MDS (sync) configuration with performance tuning
mds = MDS({
    "dsn": "postgresql://user:pass@host:port/db?options=-c%20app.tenant_id%3D<uuid>",
    "tenant_id": "uuid-string",        # Optional: overrides DSN tenant_id
    "app_name": "mds_client",          # Application name for pg_stat_activity
    "connect_timeout": 10.0,           # Connection timeout in seconds
    "statement_timeout_ms": 30000,     # Query timeout in milliseconds
    "pool_min": 1,                     # Minimum connections in pool
    "pool_max": 10,                    # Maximum connections in pool
    # Performance optimization settings
    "write_mode": "auto",              # "auto" | "executemany" | "values" | "copy"
    "values_min_rows": 500,           # Use execute_values for >= N rows
    "values_page_size": 1000,         # Page size for execute_values
    "copy_min_rows": 5000,            # Use COPY for >= N rows
})

# AMDS (async) configuration
amds = AMDS({
    "dsn": "postgresql://user:pass@host:port/db",
    "tenant_id": "uuid-string",
    "app_name": "mds_client_async",
    "pool_max": 10,                    # Async pool typically larger
    "write_mode": "auto",              # "auto" | "executemany" | "copy"
    "copy_min_rows": 5000,            # Use COPY for >= N rows
})
```

### 🚀 API Reference

#### Synchronous Client (`MDS`)

**Connection & Health:**
- [`health()`](src/mds_client/client.py) - Check database connectivity
- [`schema_version()`](src/mds_client/client.py) - Get current schema version
- [`close()`](src/mds_client/client.py) - Close connection pool

**Write Operations (Idempotent Upserts):**
- [`upsert_bars(rows: Sequence[Bar])`](src/mds_client/client.py) - Insert/update OHLCV data with time-first PKs
- [`upsert_fundamentals(rows: Sequence[Fundamentals])`](src/mds_client/client.py) - Insert/update financial data
- [`upsert_news(rows: Sequence[News])`](src/mds_client/client.py) - Insert/update news data (auto-generates UUID if missing)
- [`upsert_options(rows: Sequence[OptionSnap])`](src/mds_client/client.py) - Insert/update options data

**Read Operations:**
- [`latest_prices(symbols: Sequence[str], vendor: str)`](src/mds_client/client.py) - Get latest prices for symbols
- [`bars_window(symbol, timeframe, start, end, vendor)`](src/mds_client/client.py) - Get bars in time window

**Job Operations:**
- [`enqueue_job(idempotency_key, job_type, payload, priority)`](src/mds_client/client.py) - Enqueue job with idempotency

#### Asynchronous Client (`AMDS`)

The async client provides identical methods with `async`/`await` syntax:

- [`async health()`](src/mds_client/aclient.py) - Async health check
- [`async schema_version()`](src/mds_client/aclient.py) - Async schema version
- [`async aclose()`](src/mds_client/aclient.py) - Close async connection pool
- [`async upsert_bars(rows)`](src/mds_client/aclient.py) - Async bar upserts
- [`async upsert_fundamentals(rows)`](src/mds_client/aclient.py) - Async fundamentals upserts
- [`async upsert_news(rows)`](src/mds_client/aclient.py) - Async news upserts
- [`async upsert_options(rows)`](src/mds_client/aclient.py) - Async options upserts
- [`async latest_prices(symbols, vendor)`](src/mds_client/aclient.py) - Async price queries
- [`async bars_window(symbol, timeframe, start, end, vendor)`](src/mds_client/aclient.py) - Async bar queries
- [`async enqueue_job(...)`](src/mds_client/aclient.py) - Async job enqueueing

### 🔒 Row Level Security (RLS)

The library automatically handles tenant isolation through PostgreSQL's Row Level Security:

#### DSN Options (Recommended)
```python
# Tenant ID embedded in connection string
dsn = "postgresql://user:pass@host:port/db?options=-c%20app.tenant_id%3D<uuid>"
mds = MDS({"dsn": dsn})
```

#### Context Manager (Fallback)
```python
# Explicit tenant context for operations (if not using DSN options)
# Note: Current implementation uses SET app.tenant_id per connection
# Context managers would be implemented in rls.py if needed
```

### ⚠️ Error Handling

The library provides structured error handling with automatic retry logic:

#### [`MDSOperationalError`](src/mds_client/errors.py) - Base operational error
#### [`RetryableError`](src/mds_client/errors.py) - Temporary errors (network, deadlocks, serialization failures)
#### [`ConstraintViolation`](src/mds_client/errors.py) - Database constraint violations (unique, foreign key, check)
#### [`RLSDenied`](src/mds_client/errors.py) - Row Level Security policy violations
#### [`TimeoutExceeded`](src/mds_client/errors.py) - Query or connection timeouts

All errors are automatically mapped from `psycopg.errors` exceptions for precise error handling.

### 🛠️ Operational CLI

The library includes a comprehensive CLI for operations and debugging:

```bash
# Health and connectivity
mds ping --dsn "postgresql://..." --tenant-id "uuid"

# Schema information
mds schema-version --dsn "postgresql://..."

# Write operations
mds write-bar --dsn "..." --tenant-id "uuid" --vendor "ibkr" \
  --symbol "AAPL" --timeframe "1m" --ts "2024-01-01T10:00:00" \
  --close-price 150.5 --volume 1000

mds write-fundamental --dsn "..." --tenant-id "uuid" --vendor "alpha" \
  --symbol "AAPL" --asof "2024-01-01" --eps 1.25

mds write-news --dsn "..." --tenant-id "uuid" --vendor "reuters" \
  --title "AAPL Reports Strong Q4" --published-at "2024-01-01T10:00:00" \
  --symbol "AAPL" --sentiment-score 0.8

mds write-option --dsn "..." --tenant-id "uuid" --vendor "ibkr" \
  --symbol "AAPL" --expiry "2024-12-20" --option-type "C" --strike 200 \
  --ts "2024-01-01T10:00:00" --iv 0.25 --delta 0.55

# Read operations
mds latest-prices --dsn "..." --vendor "ibkr" --symbols "AAPL,MSFT"

# Job queue operations
mds enqueue-job --dsn "..." --tenant-id "uuid" \
  --idempotency-key "job-123" --job-type "backfill" \
  --payload '{"symbol": "AAPL", "start": "2024-01-01"}' --priority "high"

# Sync NDJSON ingest (stdin or file, .gz supported)
mds ingest-ndjson bars ./bars.ndjson \
  --dsn "postgresql://..." --tenant-id "uuid" \
  --max-rows 2000 --max-ms 3000

# Or from stdin
cat bars.ndjson | mds ingest-ndjson bars - \
  --dsn "postgresql://..." --tenant-id "uuid"

# Async NDJSON ingest (uses AMDS + AsyncBatchProcessor)
mds ingest-ndjson-async bars ./bars.ndjson \
  --dsn "postgresql://..." --tenant-id "uuid" \
  --max-rows 2000 --max-ms 3000
```

### ⚡ Performance Optimization

The library provides multiple write modes for optimal performance across different batch sizes:

#### Write Mode Selection (Auto)
```python
# Automatic mode selection based on batch size
mds = MDS({
    "write_mode": "auto",              # Default: intelligent selection
    "values_min_rows": 500,           # Use execute_values for >= 500 rows
    "copy_min_rows": 5000,            # Use COPY for >= 5000 rows
})

# Behavior:
# len(rows) >= 5000 → COPY (fastest, sync + async)
# len(rows) >= 500  → execute_values (fast, sync only)
# len(rows) < 500   → executemany (safe default)
```

#### Manual Mode Selection
```python
# Force specific write modes
mds = MDS({"write_mode": "executemany"})  # Always use executemany
mds = MDS({"write_mode": "values"})       # Force execute_values (sync only)
mds = MDS({"write_mode": "copy"})         # Force COPY path
```

#### Environment Variable Configuration
```bash
# Set via environment variables
export MDS_WRITE_MODE=auto
export MDS_VALUES_MIN_ROWS=500
export MDS_VALUES_PAGE_SIZE=1000
export MDS_COPY_MIN_ROWS=5000
```

#### Performance Characteristics
- **`executemany`**: Safe default, good for small batches (< 500 rows)
- **`execute_values`**: Fast for mid-size batches (500-5000 rows), sync only
- **`COPY`**: Fastest for large batches (5000+ rows), works with RLS and maintains idempotency

### 🔄 Batch Processing

For high-throughput scenarios, the library supports both sync and async batch processing:

#### Sync Batch Processing
```python
from mds_client import MDS, BatchProcessor, BatchConfig, Bar

mds = MDS({"dsn": "...", "tenant_id": "..."})
bp = BatchProcessor(mds, BatchConfig(max_rows=1000, max_ms=5000))
for bar in big_set:
    bp.add_bar(bar)
bp.flush()
```

#### Async Batch Processing
```python
from mds_client import AMDS, AsyncBatchProcessor, BatchConfig, Bar

amds = AMDS({"dsn": "...", "tenant_id": "...", "pool_max": 10})
async with AsyncBatchProcessor(amds, BatchConfig(max_rows=1000, max_ms=5000)) as bp:
    for bar in big_set:
        await bp.add_bar(bar)
# Auto-flush on context exit
```

### Key Features
- **Dual API**: Sync (`MDS`) and async (`AMDS`) facades with identical interfaces
- **RLS Integration**: Automatic tenant isolation via DSN options or per-connection SET
- **TimescaleDB Compatible**: Time-first composite primary keys with idempotent upserts
- **Connection Pooling**: Production-ready with psycopg 3 + psycopg_pool
- **Performance Optimization**: Multiple write modes with automatic selection:
  - `executemany`: Safe default for small batches
  - `execute_values`: Fast mid-size batches (sync only, requires psycopg extras)
  - `COPY`: Fastest for large batches (sync + async)
- **Batch Processing**: High-throughput ingestion with byte-accurate sizing and auto-flush tickers
- **Structured Errors**: Comprehensive exception hierarchy with psycopg error mapping
- **Environment Variables**: CLI support for MDS_DSN and MDS_TENANT_ID
- **NDJSON Support**: Gzip compression, stdin input, and model coercion
- **Job Outbox**: Idempotent job enqueueing with conflict-free guarantees

### Dependencies

- **Production**: [`requirements.txt`](requirements.txt) - Core runtime dependencies
- **Development**: [`requirements-dev.txt`](requirements-dev.txt) - Includes dev tools (ruff, black, pre-commit)
- **Project Config**: [`pyproject.toml`](pyproject.toml) - Full project metadata and build configuration

> **Cursor**: You can regenerate this section automatically whenever the folder structure changes. The `/cursorrules/` directory is your home base for self-bootstrapping rules and automation.
