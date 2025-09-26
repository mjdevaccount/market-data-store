from loguru import logger
from sqlalchemy.engine import Engine


def create_continuous_aggregates(engine: Engine) -> None:
    # example (commented): daily close from intraday bars
    # with engine.begin() as conn:
    #     conn.execute(text("""
    #     CREATE MATERIALIZED VIEW IF NOT EXISTS bars_1d
    #     WITH (timescaledb.continuous) AS
    #     SELECT
    #       symbol,
    #       time_bucket('1 day', ts) AS bucket,
    #       first(open_price, ts) AS open,
    #       max(high_price) AS high,
    #       min(low_price) AS low,
    #       last(close_price, ts) AS close,
    #       sum(volume) AS volume
    #     FROM bars
    #     GROUP BY symbol, bucket;
    #     """))
    logger.info("No continuous aggregates defined yet (stub).")
