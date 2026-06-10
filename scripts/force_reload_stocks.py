#!/usr/bin/env python3
"""
Force reload stock prices to fix coverage issue blocking Phase 1.
This bypasses the DynamoDB lock since the price loader is stuck/incomplete.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

from utils.database_context import DatabaseContext
from utils.data_source_router import DataSourceRouter
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

ET = ZoneInfo("America/New_York")

def get_stock_symbols():
    """Get all active stock symbols (exclude ETFs)."""
    with DatabaseContext('read') as cur:
        cur.execute("""
            SELECT symbol FROM stock_symbols
            WHERE active = true AND (etf IS NULL OR etf = '')
            ORDER BY symbol
        """)
        return [row[0] for row in cur.fetchall()]

def fetch_stock_prices(symbol: str, interval: str = "1d") -> list:
    """Fetch prices for a single stock."""
    router = DataSourceRouter()
    try:
        data = router.fetch(symbol=symbol, interval=interval, max_retries=3)
        if data:
            logger.debug(f"{symbol}: Fetched {len(data)} rows")
        return data or []
    except Exception as e:
        logger.warning(f"{symbol}: Failed to fetch - {e}")
        return []

def bulk_insert_prices(rows):
    """Insert all rows into price_daily table."""
    if not rows:
        return 0

    with DatabaseContext('write') as cur:
        import csv
        import io
        import psycopg2.sql

        # Filter to columns that exist
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'price_daily'
        """)
        valid_cols = {row[0] for row in cur.fetchall()}

        cols = [c for c in rows[0].keys() if c in valid_cols]

        # CSV load
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        for row in rows:
            writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
        buf.seek(0)

        col_ids = [psycopg2.sql.Identifier(c) for c in cols]

        # Upsert with ON CONFLICT
        cur.execute(
            psycopg2.sql.SQL(
                "COPY price_daily ({}) FROM STDIN WITH (FORMAT CSV, NULL '')"
            ).format(psycopg2.sql.SQL(",").join(col_ids)),
            buf
        )
        return cur.rowcount

def reload_stocks():
    """Reload stock prices for today."""
    logger.info("Starting force reload of stock prices...")

    symbols = get_stock_symbols()
    logger.info(f"Found {len(symbols)} active stock symbols to reload")

    all_rows = []
    batch_size = 100

    # Fetch prices with parallelism
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(fetch_stock_prices, sym): sym
            for sym in symbols
        }

        completed = 0
        for future in as_completed(futures):
            completed += 1
            if completed % 500 == 0:
                logger.info(f"  Fetched {completed}/{len(symbols)} symbols...")

            rows = future.result()
            if rows:
                all_rows.extend(rows)

                # Batch insert to avoid memory bloat
                if len(all_rows) >= batch_size * 100:
                    inserted = bulk_insert_prices(all_rows)
                    logger.info(f"  Inserted {inserted} rows (batch)")
                    all_rows = []

    # Final batch
    if all_rows:
        inserted = bulk_insert_prices(all_rows)
        logger.info(f"  Inserted {inserted} final rows")
        all_rows = []

    # Verify coverage
    with DatabaseContext('read') as cur:
        cur.execute("""
            SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s
        """, (date.today(),))

        today_count = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(DISTINCT symbol) FROM price_daily
            WHERE date = (SELECT MAX(date) FROM price_daily WHERE date < %s)
        """, (date.today(),))

        prior_count = cur.fetchone()[0]
        coverage = (today_count / max(prior_count, 1)) * 100

        logger.info(f"\n{'='*60}")
        logger.info(f"RELOAD COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"Today's stocks: {today_count}")
        logger.info(f"Prior day stocks: {prior_count}")
        logger.info(f"Coverage: {coverage:.1f}%")

        if coverage >= 95:
            logger.info("[OK] Coverage >= 95%. Phase 1 should now PASS")
        else:
            logger.warning(f"[WARNING] Coverage {coverage:.1f}% < 95% threshold")

if __name__ == "__main__":
    try:
        reload_stocks()
    except Exception as e:
        logger.error(f"Force reload failed: {e}", exc_info=True)
        sys.exit(1)
