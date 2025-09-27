"""
Row Level Security (RLS) helpers for tenant isolation.

Supports both DSN options (cheapest) and context manager (SET LOCAL) approaches.
"""

from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


def ensure_tenant_in_dsn(dsn: str, tenant_id: str | None) -> str:
    if not tenant_id:
        return dsn
    parts = urlsplit(dsn)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    # Preserve any existing options; append app.tenant_id
    opt = q.get("options", "")
    snippet = f"-c app.tenant_id={tenant_id}"
    q["options"] = f"{opt} {snippet}".strip()
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))


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
