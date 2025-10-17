# 🚀 market-data-store

> **High-performance market data infrastructure** with TimescaleDB, RLS, production-ready client library, and async sinks

**Hybrid architecture** providing both control-plane and data-plane capabilities:

- 🗄️ **Migrations & policies** (TimescaleDB)
- 🔧 **Admin endpoints**: health, readiness, schema/version, migrate, retention/compression, backfills, aggregates
- 📊 **Prometheus** metrics + observability
- 🐍 **`mds_client` library**: Production-ready Python client for Market Data Core with sync/async APIs, RLS, and tenant isolation
- 🚰 **Async sinks** (Phase 4.1): High-throughput ingestion with backpressure awareness

> 💡 The `mds_client` library provides direct in-process access for Market Data Core. No HTTP latency - Core imports and uses the library directly with connection pooling, RLS, and TimescaleDB integration.

> ⚡ NEW: **Async Sinks Layer** (Phase 4.1) - Stream-oriented ingestion with automatic Prometheus metrics, error handling, and flow control readiness.

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
```bash
# Run FastAPI service (admin endpoints)
uvicorn datastore.service.app:app --host 0.0.0.0 --port 8000 --factory
```

📊 **Policies & Aggregates** → [`/src/datastore/timescale_policies.py`](src/datastore/timescale_policies.py), [`/src/datastore/aggregates.py`](src/datastore/aggregates.py)

🛠️ **Control-plane CLI** → [`/src/datastore/cli.py`](src/datastore/cli.py)

📦 **Client Library** → [`/src/mds_client/`](src/mds_client/) - For Market Data Core integration

🔧 **Client CLI** → [`/src/mds_client/cli.py`](src/mds_client/cli.py) - Operational commands (`mds` command)

🤖 **Cursor Rules & Automation** → [`/cursorrules/`](cursorrules/) (Cursor's self-bootstrap home)

🏗️ **Infra & Deployment** → [`/docker/`](docker/), [`Dockerfile`](Dockerfile), [`docker-compose.yml`](docker-compose.yml)

⚙️ **Project Config** → [`pyproject.toml`](pyproject.toml)

## 📋 Releases

### 🏷️ Current Release: [v0.4.0]

**What's included:**
- ✅ **Core v1.1.0 contract adoption** - FeedbackEvent extends Core DTO
- ✅ **Adapter pattern** - Preserves Store fields while maintaining Core compatibility
- ✅ **Health DTOs** - `/healthz` and `/readyz` return Core `HealthStatus`
- ✅ Complete `mds_client` library with sync/async APIs
- ✅ Production-ready batch processing and backup/restore
- ✅ Comprehensive CLI with all operational commands
- ✅ Full documentation and troubleshooting guides
- ✅ RLS security and tenant isolation

### Previous Release: [v0.3.0]
- ✅ Write coordinator with backpressure feedback
- ✅ Async sinks layer
- ✅ HTTP feedback broadcaster

### 📦 Installation from Release
```bash
# Install specific version
pip install git+https://github.com/mjdevaccount/market-data-store.git@v0.1.0#subdirectory=src

# Install latest version
pip install git+https://github.com/mjdevaccount/market-data-store.git#subdirectory=src
```

## 🚀 Quick Start

### 📦 Installation

#### Option 1: Install from Git (Recommended)
```bash
# Install the mds_client library directly from this repository
pip install git+https://github.com/mjdevaccount/market-data-store.git@v0.1.0#subdirectory=src

# Or install the latest version
pip install git+https://github.com/mjdevaccount/market-data-store.git#subdirectory=src
```

#### Option 2: Development Setup
```powershell
# Clone and setup for development
git clone https://github.com/mjdevaccount/market-data-store.git
cd market-data-store

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# For development
pip install -r requirements-dev.txt
```

### Prerequisites
- Python 3.11+
- PostgreSQL 13+ with **TimescaleDB extension** (required)
- Virtual environment

### 🎯 Using the Released Package

Once installed, you can use the `mds_client` library in your projects:

```python
# Basic usage with cross-platform compatibility
from mds_client import MDS, Bar
from mds_client.runtime import boot_event_loop
from datetime import datetime, timezone

# Configure event loop for Windows/Docker compatibility
boot_event_loop()

# Configure client
mds = MDS({
    "dsn": "postgresql://user:pass@host:port/db",
    "tenant_id": "your-tenant-uuid"
})

# Write market data
bar = Bar(
    tenant_id="your-tenant-uuid",
    vendor="ibkr",
    symbol="AAPL",
    timeframe="1m",
    ts=datetime.now(timezone.utc),
    close_price=150.5,
    volume=1000
)

mds.upsert_bars([bar])
```

```bash
# Use the CLI
export MDS_DSN="postgresql://user:pass@host:port/db"
export MDS_TENANT_ID="your-tenant-uuid"

# Test connection
mds ping

# Write data
mds write-bar --vendor ibkr --symbol AAPL --timeframe 1m --ts "2024-01-01T10:00:00Z" --close-price 150.5 --volume 1000
```

---

## 🚰 Async Sinks Layer (Phase 4.1 - NEW)

> **Status**: ✅ Production Ready | **Version**: v0.2.0 | **Released**: October 2025

The async sinks layer provides **high-throughput, observable ingestion** with automatic Prometheus metrics and backpressure readiness.

### Key Features

- ⚡ **Async-first**: Non-blocking I/O with `asyncio` and `asyncpg`
- 📊 **Auto-metrics**: Prometheus counters and histograms for all writes
- 🔄 **Context managers**: Clean resource management with `async with`
- 🎯 **Type-safe**: Strong typing with Pydantic models
- 🛡️ **Error handling**: Graceful failures with metric recording
- 🧪 **Tested**: 12/12 unit tests passing, integration-ready

### Available Sinks

| Sink | Purpose | Model | Wraps |
|------|---------|-------|-------|
| **BarsSink** | OHLCV market data | `Bar` | `AMDS.upsert_bars()` |
| **OptionsSink** | Options snapshots | `OptionSnap` | `AMDS.upsert_options()` |
| **FundamentalsSink** | Company financials | `Fundamentals` | `AMDS.upsert_fundamentals()` |
| **NewsSink** | News & sentiment | `News` | `AMDS.upsert_news()` |

### Quick Start

```python
import asyncio
from datetime import datetime, timezone
from mds_client import AMDS
from mds_client.models import Bar
from market_data_store.sinks import BarsSink

async def main():
    # Configure AMDS client
    config = {
        "dsn": "postgresql://user:pass@localhost:5432/marketdata",
        "tenant_id": "your-tenant-uuid",
        "pool_max": 10
    }

    # Create sample data
    bars = [
        Bar(
            tenant_id=config["tenant_id"],
            vendor="ibkr",
            symbol="AAPL",
            timeframe="1m",
            ts=datetime.now(timezone.utc),
            close_price=150.5,
            volume=1000
        )
    ]

    # Write via sink (auto-metrics + error handling)
    async with AMDS(config) as amds:
        async with BarsSink(amds) as sink:
            await sink.write(bars)

    print("✅ Bars written successfully")

if __name__ == "__main__":
    asyncio.run(main())
```

### Metrics Exported

Sinks automatically register metrics to the global Prometheus registry:

```promql
# Total write attempts (counter)
sink_writes_total{sink="bars|options|fundamentals|news", status="success|failure"}

# Write latency (histogram)
sink_write_latency_seconds{sink="bars|options|fundamentals|news"}
```

**Scrape at**: `http://localhost:8081/metrics` (FastAPI control-plane)

### Example: All Sinks

See [`examples/run_store_pipeline.py`](examples/run_store_pipeline.py) for a complete example using all four sinks.

```powershell
# Set environment variables
$env:MDS_DSN="postgresql://user:pass@localhost:5432/marketdata"
$env:MDS_TENANT_ID="your-tenant-uuid"

# Run pipeline example
python examples/run_store_pipeline.py
```

**Output:**
```
🚀 market_data_store Sink Pipeline Example
   Tenant: 6b6a6a8a...

📊 BarsSink Example
  ✅ Wrote 2 bars
📈 OptionsSink Example
  ✅ Wrote 1 options
📋 FundamentalsSink Example
  ✅ Wrote 1 fundamentals
📰 NewsSink Example
  ✅ Wrote 1 news items

✅ All sinks completed successfully!
```

### Benchmarks

Run performance benchmarks with [`examples/benchmark_sinks.py`](examples/benchmark_sinks.py):

```powershell
python examples/benchmark_sinks.py --batches 50 --batch-size 1000 --parallel 4
```

**Example Results** (Mock mode, Windows):
```
========================================================================
Benchmark Results (Phase 4.1)
========================================================================
BarsSink                 13,674 rec/s   avg latency   14.0 ms   total    2,000
OptionsSink              12,899 rec/s   avg latency   14.2 ms   total    2,000
FundamentalsSink         12,886 rec/s   avg latency   15.0 ms   total    2,000
NewsSink                 12,947 rec/s   avg latency   14.9 ms   total    2,000
========================================================================

Overall: 8,000 records in 0.61s (13,093 rec/s aggregate)
```

### Migration from AsyncBatchProcessor

If you're currently using `mds_client.batch.AsyncBatchProcessor`:

**Before:**
```python
from mds_client import AMDS, AsyncBatchProcessor, BatchConfig

async with AsyncBatchProcessor(amds, BatchConfig(max_rows=1000)) as processor:
    for bar in stream:
        await processor.add_bar(bar)
```

**After (with sinks):**
```python
from market_data_store.sinks import BarsSink

async with BarsSink(amds) as sink:
    await sink.write(batch_of_bars)
```

**Key Differences:**
- ✅ Sinks provide **automatic Prometheus metrics**
- ✅ Sinks use **standardized logging** (loguru)
- ⚠️ Sinks expect **pre-batched data** (no auto-flushing)
- ⚠️ AsyncBatchProcessor provides **incremental adds + auto-flush**

**When to Use:**
- **Sinks**: Pre-batched data, need metrics/observability
- **AsyncBatchProcessor**: Streaming data, need auto-batching

### Testing

```powershell
# Unit tests (fast, no DB)
pytest -v tests/unit/sinks/

# Smoke test
python tests/smoke_test_sinks.py

# Integration tests (requires DB)
$env:MDS_DSN="postgresql://..."
$env:MDS_TENANT_ID="uuid"
pytest -v tests/integration/ -m integration

# All tests
pytest -v tests/
```

**Test Coverage:**
- ✅ 12/12 unit tests passing (0.51s)
- ✅ 6/6 smoke test checks passing
- ✅ 0 linter errors
- ✅ Integration tests ready (DB required)

### Architecture

The sinks layer is part of the **hybrid architecture**:

```
┌─────────────────────────────────────────┐
│ market-data-store (Hybrid)              │
├─────────────────────────────────────────┤
│ Control-plane (datastore/)              │
│  • Migrations, policies, admin API      │
│  • Health, readiness, metrics endpoints │
├─────────────────────────────────────────┤
│ Data-plane (market_data_store/sinks/)   │
│  • BarsSink, OptionsSink, etc.          │
│  • Prometheus metrics integration       │
│  • Backpressure readiness (Phase 4.2+)  │
├─────────────────────────────────────────┤
│ Client library (mds_client/)            │
│  • MDS (sync) + AMDS (async) facades    │
│  • Connection pooling, RLS, validation  │
└─────────────────────────────────────────┘
```

### Documentation

- 📖 **Implementation Guide**: [`PHASE_4_IMPLEMENTATION.md`](PHASE_4_IMPLEMENTATION.md)
- 📖 **Cursor Rules**: [`cursorrules/rules/sinks_layer.mdc`](cursorrules/rules/sinks_layer.mdc)
- 📖 **Examples**: [`examples/`](examples/)

### Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| **4.1** | ✅ Complete | Async sinks with metrics |
| **4.2** | ⏸️ Deferred | Write coordinator + queue |
| **4.3** | 🚫 Blocked | Backpressure integration |

Phase 4.2+ deferred pending architecture decisions and external dependencies (`market-data-pipeline` v0.8.0).

---

## 🔧 Windows/Docker Compatibility

This project includes comprehensive cross-platform compatibility for both Windows development and Linux/Docker production environments with **zero resource leaks** and **automatic cleanup**:

### **Event Loop Configuration**
- **Windows**: Automatically uses `WindowsSelectorEventLoopPolicy` for psycopg compatibility
- **Linux/macOS**: Uses `uvloop` for enhanced performance when available
- **Automatic**: No manual configuration required - just call `boot_event_loop()` early in your application

### **Connection Pool Management**
- **Context managers**: All clients support `with` and `async with` for automatic cleanup
- **Zero pool warnings**: Explicit pool lifecycle management eliminates cleanup warnings
- **Resource management**: Proper timeout-based cleanup prevents hanging threads
- **Production ready**: Guaranteed clean shutdown in all scenarios

### **Production Features**
- **Health monitoring**: Comprehensive database health checks and Prometheus metrics
- **Resource management**: Centralized resource cleanup with context managers
- **CLI tools**: Cross-platform command-line interface with health and metrics commands
- **Performance optimized**: 200+ bars/second processing with clean resource management

### **Usage Examples**

**Sync Client with Context Manager:**
```python
from mds_client.runtime import boot_event_loop
from mds_client import MDS

boot_event_loop()  # Configure event loop for your platform

with MDS({'dsn': 'postgresql://...', 'tenant_id': '...'}) as mds:
    result = mds.upsert_bars([bar])
    # Pool automatically closed on exit - NO warnings!
```

**Async Client with Context Manager:**
```python
from mds_client.runtime import boot_event_loop
from mds_client import AMDS

boot_event_loop()  # Configure event loop for your platform

async with AMDS({'dsn': 'postgresql://...', 'tenant_id': '...'}) as amds:
    result = await amds.upsert_bars([bar])
    # Pool automatically closed on exit - NO warnings!
```

**Batch Processing with Context Manager:**
```python
from mds_client.batch import BatchProcessor, BatchConfig

with MDS({'dsn': 'postgresql://...', 'tenant_id': '...'}) as mds:
    with BatchProcessor(mds, BatchConfig(max_rows=100)) as processor:
        processor.add_bar(bar)
        # Both mds and processor automatically closed on exit - NO warnings!
```

**Health Monitoring:**
```bash
# CLI Health Check
mds health --dsn "postgresql://..." --tenant-id "..."

# CLI Metrics
mds metrics --format prometheus
```

### **Performance Benchmarks**
- **Sync processing**: 84+ bars/second with clean shutdown
- **Async processing**: 77+ bars/second with clean shutdown
- **Batch processing**: 200+ bars/second with clean shutdown
- **Zero resource leaks**: All pools properly closed with context managers

### Testing Quickstart
```bash
# Run NDJSON round-trip tests
pytest -q tests/test_ndjson_roundtrip.py

# Run all tests (cross-platform)
pytest tests/ -v

# Run Windows compatibility tests
pytest tests/test_windows_compatibility.py -v
```

### Development Commands
```bash
# Format and lint code
make fmt
make lint

# Run tests
make test

# Database operations
make migrate
make seed
make policies
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

## 🔗 Market Data Store Integration

The `market-data-store` package is a **core dependency** for Market Data Core, providing:

### 📦 **Python Package Integration**
```python
# Import the market data store package
import market_data_store

# Access version information
print(f"Market Data Store version: {market_data_store.__version__}")

# The package provides access to all CLI operations and Python library
from mds_client import MDS, AMDS, Bar, Fundamentals, News, OptionSnap
```

### 🛠️ **Available Operations**

The `market-data-store` package provides comprehensive data persistence capabilities:

#### **Data Types Supported**
- **Bars/OHLCV**: Time-series price data with multiple timeframes
- **Fundamentals**: Company financial data (assets, liabilities, earnings)
- **News**: Market news with sentiment analysis
- **Options**: Options market data with Greeks (delta, gamma, IV)

#### **CLI Operations** (via `mds` command)
```bash
# Health & Schema
mds ping                    # Database connectivity check
mds schema-version         # Get current schema version
mds latest-prices          # Get latest prices for symbols

# Individual Write Operations
mds write-bar              # Write single OHLCV bar
mds write-fundamental      # Write company fundamentals
mds write-news             # Write news article
mds write-option           # Write options data

# Bulk Operations
mds ingest-ndjson          # Bulk ingest from NDJSON files
mds ingest-ndjson-async    # Async bulk ingest

# Export/Import Operations
mds dump                    # Export to CSV
mds restore                 # Import from CSV
mds restore-async           # Async CSV import
mds dump-ndjson             # Export to NDJSON
mds dump-ndjson-async       # Async NDJSON export

# Job Queue Operations
mds enqueue-job             # Queue background jobs
```

#### **Python Library Usage**
```python
# Synchronous operations
from mds_client import MDS
mds = MDS({"dsn": "postgresql://...", "tenant_id": "uuid"})

# Write market data
mds.upsert_bars([bar_data])
mds.upsert_fundamentals([fundamental_data])
mds.upsert_news([news_data])
mds.upsert_options([option_data])

# Read operations
latest_prices = mds.latest_prices(["AAPL", "MSFT"], vendor="ibkr")

# Async operations
from mds_client import AMDS, AsyncBatchProcessor
amds = AMDS({"dsn": "postgresql://...", "tenant_id": "uuid", "pool_max": 10})
```

### 🏗️ **Architecture Benefits**

- **Tenant Isolation**: Row Level Security (RLS) ensures data separation
- **TimescaleDB Integration**: Optimized for time-series data
- **Connection Pooling**: High-performance async/sync connection management
- **Batch Processing**: Efficient bulk operations with configurable batching
- **Idempotent Operations**: Safe retry and upsert semantics
- **Production Ready**: Comprehensive error handling, logging, and monitoring

### 📋 **Quick Reference**

For detailed operation documentation, see:
- **CLI Operations**: [`cursorrules/rules/market_data_store_operations.mdc`](cursorrules/rules/market_data_store_operations.mdc)
- **Python Library**: [`src/mds_client/`](src/mds_client/)
- **Data Models**: [`src/mds_client/models.py`](src/mds_client/models.py)

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
    tenant_id: str                    # UUID for tenant isolation (tenants.id)
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
    tenant_id: str                    # UUID for tenant isolation (tenants.id)
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
    tenant_id: str                    # UUID for tenant isolation (tenants.id)
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
    tenant_id: str                    # UUID for tenant isolation (tenants.id)
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
    tenant_id: str                    # UUID for tenant isolation (tenants.id)
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

> **Exit Codes**: All CLI commands return non-zero exit codes on failure for CI/CD integration.

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
# Note: write-option targets the options_snap table (model: OptionSnap)

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

# Backup/Export operations (tenant-aware, RLS-enforced)
mds dump bars ./bars_export.csv.gz \
  --dsn "postgresql://..." --tenant-id "uuid" \
  --vendor "ibkr" --symbol "AAPL" --timeframe "1m" \
  --start "2024-01-01T00:00:00Z" --end "2024-02-01T00:00:00Z"

# Restore/Import operations (idempotent upserts)
# Sync CSV restore
mds restore bars ./bars_export.csv.gz \
  --dsn "postgresql://..." --tenant-id "uuid"

# Async CSV restore (for large files)
mds restore-async bars ./bars_export.csv.gz \
  --dsn "postgresql://..." --tenant-id "uuid" \
  --delimiter "," --header

# Async CSV restore from STDIN (shell pipelines)
zcat bars_export.csv.gz | mds restore-async-stdin bars \
  --dsn "postgresql://..." --tenant-id "uuid"

# NDJSON dump operations (round-trip with ingest-ndjson)
mds dump-ndjson bars ./bars_export.ndjson.gz \
  --dsn "postgresql://..." --tenant-id "uuid" \
  --vendor "ibkr" --symbol "AAPL" --timeframe "1m" \
  --start "2024-01-01T00:00:00Z" --end "2024-02-01T00:00:00Z"

# Async NDJSON dump for large exports
mds dump-ndjson-async bars ./bars_export.ndjson.gz \
  --dsn "postgresql://..." --tenant-id "uuid" \
  --vendor "ibkr" --symbol "AAPL"
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

#### Environment Variables Reference
| Var | Meaning |
|-----|---------|
| `MDS_DSN` | PostgreSQL DSN |
| `MDS_TENANT_ID` | Tenant UUID for RLS (must be tenants.id, not tenants.tenant_id) |
| `MDS_WRITE_MODE` | `auto` \| `executemany` \| `values` \| `copy` |
| `MDS_VALUES_MIN_ROWS` | Threshold for execute_values |
| `MDS_COPY_MIN_ROWS` | Threshold for COPY |

#### Performance Characteristics
- **`executemany`**: Safe default, good for small batches (< 500 rows)
- **`execute_values`**: Fast for mid-size batches (500-5000 rows), sync only
  - Install extras: `pip install "psycopg[pool,extras]"`
- **`COPY`**: Fastest for large batches (5000+ rows), works with RLS and maintains idempotency

#### Troubleshooting
- **Tenant ID errors**: Use `tenants.id` (UUID), not `tenants.tenant_id` (VARCHAR)
- **Windows async issues**: Use sync `MDS` client; async pools need `SelectorEventLoop`
- **Foreign key violations**: Ensure tenant exists in `tenants` table with correct UUID
- **RLS denied**: Verify `app.tenant_id` is set correctly in connection context

### 💾 Backup & Restore Operations

The library provides tenant-aware backup and restore operations using PostgreSQL's `COPY` command:

#### Export Operations (Tenant-Aware Dumps)
```python
from mds_client import MDS
from psycopg import sql as psql

mds = MDS({"dsn": "...", "tenant_id": "uuid"})

# Export bars for specific vendor/symbol/timeframe
sel = psql.SQL("""
    SELECT {cols}
    FROM bars
    WHERE vendor = {v} AND symbol = {s} AND timeframe = '1m'
      AND ts >= {start} AND ts < {end}
    ORDER BY ts
""").format(
    cols=psql.SQL(", ").join(psql.Identifier(c) for c in mds.TABLE_PRESETS["bars"]["cols"]),
    v=psql.Literal("ibkr"),
    s=psql.Literal("AAPL"),
    start=psql.Literal("2024-01-01T00:00:00Z"),
    end=psql.Literal("2024-02-01T00:00:00Z"),
)

# Export to gzipped CSV
mds.copy_out_csv(select_sql=sel, out_path="bars_aapl_2024-01.csv.gz")
```

#### Import Operations (Idempotent Upserts)
```python
# Restore from CSV with upsert semantics
preset = MDS.TABLE_PRESETS["bars"]
mds.copy_restore_csv(
    target="bars",
    cols=preset["cols"],
    conflict_cols=preset["conflict"],
    update_cols=preset["update"],
    src_path="bars_aapl_2024-01.csv.gz",
)
```

#### CLI Operations
```bash
# Export with filters
mds dump bars ./bars_export.csv.gz \
  --dsn "postgresql://..." --tenant-id "uuid" \
  --vendor "ibkr" --symbol "AAPL" --timeframe "1m" \
  --start "2024-01-01T00:00:00Z" --end "2024-02-01T00:00:00Z"

# Import with upsert (sync)
mds restore bars ./bars_export.csv.gz \
  --dsn "postgresql://..." --tenant-id "uuid"

# Import with upsert (async - for large files)
mds restore-async bars ./bars_export.csv.gz \
  --dsn "postgresql://..." --tenant-id "uuid" \
  --delimiter "," --header

# Import from STDIN (shell pipelines)
zcat bars_export.csv.gz | mds restore-async-stdin bars \
  --dsn "postgresql://..." --tenant-id "uuid"
```

#### Key Features
- **RLS Enforcement**: All operations respect Row Level Security via `SET app.tenant_id`
- **Consistent Snapshots**: Multiple `COPY` operations in single transaction
- **Idempotent Restores**: `INSERT ... ON CONFLICT DO UPDATE` preserves existing data
- **Gzip Support**: Automatic compression for `.gz` files
- **CSV with Headers**: Self-describing format for easy inspection
- **Streaming**: Memory-efficient for large datasets

### 📄 NDJSON Export Operations

The library provides NDJSON export functionality that perfectly round-trips with the existing ingest commands:

#### Export Operations (JSON Streaming)
```python
from mds_client import MDS
from psycopg import sql as psql

mds = MDS({"dsn": "...", "tenant_id": "uuid"})

# Export bars as NDJSON
sel = psql.SQL("""
    SELECT {cols}
    FROM bars
    WHERE vendor = {v} AND symbol = {s} AND timeframe = '1m'
      AND ts >= {start} AND ts < {end}
    ORDER BY ts
""").format(
    cols=psql.SQL(", ").join(psql.Identifier(c) for c in mds.TABLE_PRESETS["bars"]["cols"]),
    v=psql.Literal("ibkr"),
    s=psql.Literal("AAPL"),
    start=psql.Literal("2024-01-01T00:00:00Z"),
    end=psql.Literal("2024-02-01T00:00:00Z"),
)

# Export to gzipped NDJSON
mds.copy_out_ndjson(select_sql=sel, out_path="bars_aapl_2024-01.ndjson.gz")
```

#### CLI Operations
```bash
# Sync NDJSON export
mds dump-ndjson bars ./bars_export.ndjson.gz \
  --dsn "postgresql://..." --tenant-id "uuid" \
  --vendor "ibkr" --symbol "AAPL" --timeframe "1m" \
  --start "2024-01-01T00:00:00Z" --end "2024-02-01T00:00:00Z"

# Async NDJSON export for large datasets
mds dump-ndjson-async bars ./bars_export.ndjson.gz \
  --dsn "postgresql://..." --tenant-id "uuid" \
  --vendor "ibkr" --symbol "AAPL"

# Round-trip: export then import
mds dump-ndjson bars ./bars.ndjson --dsn "..." --tenant-id "uuid"
mds ingest-ndjson bars ./bars.ndjson --dsn "..." --tenant-id "uuid"

# Multi-table exports with template naming
mds dump-ndjson-all \
  --dsn "postgresql://..." --tenant-id "uuid" \
  --vendor ibkr --symbol AAPL --timeframe 1m \
  --start 2024-01-01T00:00:00Z --end 2024-02-01T00:00:00Z

# Custom naming template with directory structure
mds dump-ndjson-all "./exports/{table}/{vendor}-{symbol}-{start}-{end}.ndjson.gz" \
  --dsn "postgresql://..." --tenant-id "uuid" --vendor ibkr

# Async multi-table export for large datasets
mds dump-ndjson-async-all \
  --dsn "postgresql://..." --tenant-id "uuid" \
  --start 2024-01-01 --end 2024-02-01
```

#### Key Features
- **Round-trip compatibility**: Perfect compatibility with `ingest-ndjson` commands
- **JSON streaming**: Uses `to_jsonb()` for efficient PostgreSQL JSON serialization
- **RLS enforcement**: All operations respect tenant isolation
- **Gzip support**: Automatic compression for `.ndjson.gz` files
- **Async support**: High-performance async exports for large datasets
- **ISO timestamps**: Timestamps serialized in ISO-8601 format for clean parsing
- **Multi-table exports**: Export all tables at once with template-based naming
- **Template system**: Flexible file naming with variables `{table}`, `{vendor}`, `{symbol}`, `{timeframe}`, `{start}`, `{end}`
- **Directory creation**: Automatic parent directory creation for organized exports

#### Multi-Table Export Operations
```bash
# Export all tables with default naming
mds dump-ndjson-all \
  --dsn "postgresql://..." --tenant-id "uuid" \
  --vendor ibkr --symbol AAPL --timeframe 1m \
  --start 2024-01-01T00:00:00Z --end 2024-02-01T00:00:00Z
# Creates: ./bars-AAPL-2024-01-01T00:00:00Z-2024-02-01T00:00:00Z.ndjson.gz
#          ./fundamentals-AAPL-2024-01-01T00:00:00Z-2024-02-01T00:00:00Z.ndjson.gz
#          ./news-AAPL-2024-01-01T00:00:00Z-2024-02-01T00:00:00Z.ndjson.gz
#          ./options_snap-AAPL-2024-01-01T00:00:00Z-2024-02-01T00:00:00Z.ndjson.gz
# Note: {timeframe} is ignored for tables without that column (fundamentals/news/options)

# Custom template with directory structure
mds dump-ndjson-all "./exports/{table}/{vendor}-{symbol}-{start}-{end}.ndjson.gz" \
  --dsn "postgresql://..." --tenant-id "uuid" --vendor ibkr
# Creates: ./exports/bars/ibkr-AAPL-2024-01-01-2024-02-01.ndjson.gz
#          ./exports/fundamentals/ibkr-AAPL-2024-01-01-2024-02-01.ndjson.gz
#          etc.

# Async version for large datasets
mds dump-ndjson-async-all \
  --dsn "postgresql://..." --tenant-id "uuid" \
  --start 2024-01-01 --end 2024-02-01
```

#### Template Variables
- `{table}`: Table name (bars, fundamentals, news, options_snap)
- `{vendor}`: Data vendor (e.g., ibkr, reuters) or "ALL" if not specified
- `{symbol}`: Symbol (e.g., AAPL) or "ALL" if not specified
- `{timeframe}`: Timeframe (e.g., 1m, 1h) or "ALL" if not specified
- `{start}`: Start timestamp or "MIN" if not specified
- `{end}`: End timestamp or "MAX" if not specified

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
- **Backup/Restore**: Tenant-aware CSV export/import with RLS enforcement and idempotent upserts
- **NDJSON Export**: Round-trip compatible JSON dumps with `to_jsonb()` streaming

### Dependencies

- **Production**: [`requirements.txt`](requirements.txt) - Core runtime dependencies
- **Development**: [`requirements-dev.txt`](requirements-dev.txt) - Includes dev tools (ruff, black, pre-commit)
- **Project Config**: [`pyproject.toml`](pyproject.toml) - Full project metadata and build configuration

> **Cursor**: You can regenerate this section automatically whenever the folder structure changes. The `/cursorrules/` directory is your home base for self-bootstrapping rules and automation.

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions welcome! Please open an issue or submit a pull request.
