"""
Row Level Security (RLS) helpers for tenant isolation.

Supports both DSN options (cheapest) and context manager (SET LOCAL) approaches.
"""


def ensure_tenant_in_dsn(dsn: str, tenant_id: str | None) -> str:
    if "options=" in dsn or not tenant_id:
        return dsn
    sep = "&" if "?" in dsn else "?"
    return f"{dsn}{sep}options=-c%20app.tenant_id%3D{tenant_id}"


class TenantContext:
    def __init__(self, pool, tenant_id: str):
        self.pool = pool
        self.tenant_id = tenant_id

    def __enter__(self):
        self.conn = self.pool.connection().__enter__()
        self.cur = self.conn.cursor().__enter__()
        self.cur.execute("SET LOCAL app.tenant_id = %s", [self.tenant_id])
        return self

    def cursor(self):
        return self.cur

    def __exit__(self, *a):
        self.cur.__exit__(*a)
        self.conn.__exit__(*a)


class AsyncTenantContext:
    def __init__(self, pool, tenant_id: str):
        self.pool = pool
        self.tenant_id = tenant_id

    async def __aenter__(self):
        self.conn = await self.pool.getconn()
        self.cur = await self.conn.cursor()
        await self.cur.execute("SET LOCAL app.tenant_id = %s", [self.tenant_id])
        return self

    def cursor(self):
        return self.cur

    async def __aexit__(self, exc_type, exc, tb):
        await self.cur.close()
        await self.pool.putconn(self.conn)
