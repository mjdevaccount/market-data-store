from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Engine

CHECK_TS = text("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")

HYPERS = [
    ("bars", "ts"),
    ("fundamentals", "asof"),
    ("news", "published_at"),
    ("options_snap", "ts"),
]

COMPRESSION_POLICIES = [
    ("bars", "90 days"),
    ("options_snap", "90 days"),
    ("news", "30 days"),
]

# before enabling compression, bail if any RLS is enabled on the table
RLS_CHECK = """
SELECT EXISTS (
  SELECT 1
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_catalog.pg_policies p ON p.schemaname = n.nspname AND p.tablename = c.relname
  WHERE n.nspname='public' AND c.relname = :table
);
"""


def _timescale_available(engine: Engine) -> bool:
    with engine.connect() as conn:
        return bool(conn.execute(CHECK_TS).scalar())


def apply_hypertables(engine: Engine) -> None:
    if not _timescale_available(engine):
        logger.warning("TimescaleDB not installed; skipping hypertables.")
        return
    with engine.begin() as conn:
        for table, timecol in HYPERS:
            logger.info(f"Creating hypertable for {table}({timecol}) if not exists")
            conn.execute(
                text("SELECT create_hypertable(:t, :tc, if_not_exists => TRUE);").bindparams(
                    t=table, tc=timecol
                )
            )


def apply_compression(engine: Engine) -> None:
    if not _timescale_available(engine):
        logger.warning("TimescaleDB not installed; skipping compression policies.")
        return
    with engine.begin() as conn:
        for table, interval in COMPRESSION_POLICIES:
            rls_exists = conn.execute(text(RLS_CHECK), {"table": table}).scalar()
            if rls_exists:
                # log and skip
                logger.warning(f"Skipping compression on {table} (RLS enabled).")
                continue
            conn.execute(text(f"ALTER TABLE {table} SET (timescaledb.compress);"))
            conn.execute(
                text("SELECT add_compression_policy(:t, INTERVAL :ival)").bindparams(
                    t=table, ival=interval
                )
            )


def apply_retention(engine: Engine) -> None:
    # Optional: add retention policies later if desired
    pass


def apply_all(engine: Engine) -> None:
    apply_hypertables(engine)
    apply_compression(engine)
    apply_retention(engine)
