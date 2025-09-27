from __future__ import annotations

import gzip
import json
import os
from datetime import datetime, timezone, timedelta

import pytest

from mds_client.client import MDS
from mds_client.models import Bar
from mds_client.sql import build_ndjson_select, TABLE_PRESETS
from psycopg import sql as psql


@pytest.mark.skipif(
    not (os.getenv("MDS_TEST_DSN") and os.getenv("MDS_TEST_TENANT_ID")),
    reason="set MDS_TEST_DSN and MDS_TEST_TENANT_ID to run DB tests",
)
def test_bars_ndjson_roundtrip(tmp_path):
    dsn = os.environ["MDS_TEST_DSN"]
    tenant_id = os.environ["MDS_TEST_TENANT_ID"]

    mds = MDS({"dsn": dsn, "tenant_id": tenant_id})

    now = datetime.now(tz=timezone.utc).replace(microsecond=0)
    rows = [
        Bar(
            tenant_id=tenant_id,
            vendor="ibkr",
            symbol="AAPL",
            timeframe="1m",
            ts=now + timedelta(minutes=i),
            open_price=100 + i,
            high_price=100.5 + i,
            low_price=99.5 + i,
            close_price=100.2 + i,
            volume=1000 + 10 * i,
        )
        for i in range(3)
    ]

    # Clean slate for this slice
    with mds.pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM bars
            WHERE tenant_id = current_setting('app.tenant_id')::uuid
              AND vendor = %s AND symbol = %s AND timeframe = %s
            """,
            ("ibkr", "AAPL", "1m"),
        )

    # Upsert original rows
    mds.upsert_bars(rows)

    # Dump to NDJSON
    sel = build_ndjson_select(
        "bars",
        vendor="ibkr",
        symbol="AAPL",
        timeframe="1m",
        start=rows[0].ts,
        end=rows[-1].ts + timedelta(minutes=1),
    )
    out_path = tmp_path / "bars.ndjson.gz"
    with mds.pool.connection() as conn, conn.cursor() as cur, gzip.open(out_path, "wb") as gz:
        copy_sql = psql.SQL("COPY ({sel}) TO STDOUT").format(sel=sel)
        with cur.copy(copy_sql) as cp:
            while data := cp.read():
                gz.write(data)

    # Delete again to prove restore works
    with mds.pool.connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM bars
            WHERE tenant_id = current_setting('app.tenant_id')::uuid
              AND vendor = %s AND symbol = %s AND timeframe = %s
            """,
            ("ibkr", "AAPL", "1m"),
        )

    # Re-ingest from NDJSON (simulate ingest-ndjson path via models + upsert)
    re_rows = []
    with gzip.open(out_path, "rt", encoding="utf-8") as fh:
        for line in fh:
            d = json.loads(line)
            # Ensure required fields are present; coercion handled by Bar model
            re_rows.append(Bar(**d))

    mds.upsert_bars(re_rows)

    # Dump again and compare docs
    again = []
    with mds.pool.connection() as conn, conn.cursor() as cur:
        copy_sql = psql.SQL("COPY ({sel}) TO STDOUT").format(sel=sel)
        with cur.copy(copy_sql) as cp:
            # copy.read() returns bytes; we want JSON lines
            buf = b""
            while chunk := cp.read():
                buf += chunk
            for line in buf.splitlines():
                if not line:
                    continue
                again.append(json.loads(line))

    # Normalize to sets of tuples (ordered by ts) for equality
    preset_cols = TABLE_PRESETS["bars"].cols

    def normalize(docs):
        return [tuple(d.get(c) for c in preset_cols) for d in sorted(docs, key=lambda x: x["ts"])]

    # First export
    with gzip.open(out_path, "rt", encoding="utf-8") as fh:
        first_dump = [json.loads(line) for line in fh if line.strip()]

    assert normalize(first_dump) == normalize(again)
