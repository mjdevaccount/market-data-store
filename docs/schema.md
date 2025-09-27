# Database Schema Reference

## Tenant Table Structure

The `tenants` table has two identifier columns:

```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),  -- Primary key (used by foreign keys)
    tenant_id VARCHAR(50) NOT NULL UNIQUE,          -- Human-readable identifier
    name VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## Foreign Key Relationships

**CRITICAL**: All fact tables reference `tenants.id` (UUID), not `tenants.tenant_id` (VARCHAR):

```
tenants.id (UUID) ←── bars.tenant_id
tenants.id (UUID) ←── fundamentals.tenant_id
tenants.id (UUID) ←── news.tenant_id
tenants.id (UUID) ←── options_snap.tenant_id
```

## Row Level Security (RLS)

All fact tables use RLS with the following policy:

```sql
-- RLS policy checks current_setting('app.tenant_id')::uuid
-- This means app.tenant_id must be set to a valid UUID (tenants.id)
```

## Common Errors

1. **Foreign Key Violation**: Using `tenants.tenant_id` (VARCHAR) instead of `tenants.id` (UUID)
2. **Invalid UUID**: Using string identifiers instead of UUID format
3. **RLS Denied**: `app.tenant_id` not set or set to invalid UUID

## Example Usage

```python
# Correct: Use tenants.id (UUID)
mds = MDS({
    "dsn": "postgresql://user:pass@host:port/db",
    "tenant_id": "550e8400-e29b-41d4-a716-446655440000"  # tenants.id
})

# Incorrect: Don't use tenants.tenant_id (VARCHAR)
# tenant_id: "default"  # This will fail with foreign key violation
```
