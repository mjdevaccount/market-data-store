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
    ├── client.py                  # MDS (sync client facade)
    ├── aclient.py                 # AMDS (async client facade)
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
```

## 📚 Client Library Documentation

### 🏗️ Architecture Overview

The `mds_client` library provides a production-ready Python client for Market Data Core with two main facades:

- **`MDS`** - Synchronous client for operations and simple integrations
- **`AMDS`** - Asynchronous client for high-performance Market Data Core

Both clients support:
- **Row Level Security (RLS)** with tenant isolation
- **Connection pooling** with psycopg 3
- **TimescaleDB integration** with time-first composite primary keys
- **Idempotent upserts** with conflict resolution
- **Structured error handling** with retry logic

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

#### [`MDSConfig`](src/mds_client/client.py#L18-L28) - Client Configuration
```python
class MDSConfig(TypedDict, total=False):
    dsn: str                          # PostgreSQL connection string
    tenant_id: str                    # UUID for tenant isolation
    app_name: str                     # Application name for pg_stat_activity
    connect_timeout: float            # Connection timeout in seconds
    statement_timeout_ms: int         # Query timeout in milliseconds
    pool_min: int                     # Minimum connections in pool
    pool_max: int                      # Maximum connections in pool
    max_batch_rows: int               # Batch size for high-throughput writes
    max_batch_ms: int                 # Batch flush interval in milliseconds
```

### 🚀 API Reference

#### Synchronous Client (`MDS`)

**Connection & Health:**
- [`health()`](src/mds_client/client.py#L52-L58) - Check database connectivity
- [`schema_version()`](src/mds_client/client.py#L60-L68) - Get current schema version
- [`tenant(tenant_id)`](src/mds_client/client.py#L49-L50) - Get tenant context for RLS

**Write Operations (Idempotent Upserts):**
- [`upsert_bars(rows: list[Bar])`](src/mds_client/client.py#L71-L83) - Insert/update OHLCV data
- [`upsert_fundamentals(rows: list[Fundamentals])`](src/mds_client/client.py#L85-L97) - Insert/update financial data
- [`upsert_news(rows: list[News])`](src/mds_client/client.py#L99-L111) - Insert/update news data
- [`upsert_options(rows: list[OptionSnap])`](src/mds_client/client.py#L113-L125) - Insert/update options data

**Read Operations:**
- [`latest_prices(symbols: list[str], vendor: str)`](src/mds_client/client.py#L128-L138) - Get latest prices for symbols
- [`bars_window(symbol, timeframe, start, end, vendor)`](src/mds_client/client.py#L140-L154) - Get bars in time window

#### Asynchronous Client (`AMDS`)

The async client provides identical methods with `async`/`await` syntax:

- [`async health()`](src/mds_client/aclient.py#L40-L46) - Async health check
- [`async schema_version()`](src/mds_client/aclient.py#L48-L56) - Async schema version
- [`async upsert_bars(rows)`](src/mds_client/aclient.py#L59-L71) - Async bar upserts
- [`async latest_prices(symbols, vendor)`](src/mds_client/aclient.py#L120-L130) - Async price queries
- And all other methods with async equivalents...

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
# Explicit tenant context for operations
with mds.tenant("tenant-uuid") as ctx:
    # All operations use this tenant context
    ctx.cursor().execute("SELECT * FROM bars")
```

### ⚠️ Error Handling

The library provides structured error handling with automatic retry logic:

#### [`MDSOperationalError`](src/mds_client/errors.py#L7-L9) - Base operational error
#### [`RetryableError`](src/mds_client/errors.py#L11-L13) - Temporary errors (network, deadlocks)
#### [`ConstraintViolation`](src/mds_client/errors.py#L15-L17) - Database constraint violations
#### [`RLSDenied`](src/mds_client/errors.py#L19-L21) - Row Level Security policy violations
#### [`TimeoutExceeded`](src/mds_client/errors.py#L23-L25) - Query or connection timeouts

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
```

### 🔄 Batch Processing

For high-throughput scenarios, the library supports batch processing:

```python
from mds_client import BatchProcessor

# Configure batch processing
batch_config = {
    "max_rows": 1000,      # Flush after 1000 rows
    "max_ms": 5000,        # Or flush after 5 seconds
    "max_bytes": 1024*1024  # Or flush after 1MB
}

# Process large datasets efficiently
processor = BatchProcessor(mds, batch_config)
for bar in large_bar_dataset:
    processor.add_bar(bar)
    # Automatically flushes based on size/time thresholds
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
