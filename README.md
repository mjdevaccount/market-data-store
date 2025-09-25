# market-data-store

Thin **control-plane** for the market data database:
- **Migrations & policies** (TimescaleDB)
- **Admin endpoints**: health, readiness, schema/version, migrate, retention/compression, backfills, aggregates
- **Prometheus** metrics

> No bulk reads/writes via HTTP. Orchestrator writes via the `datastore` library; readers query DB directly or via a future analytics API.
