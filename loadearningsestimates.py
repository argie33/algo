#!/usr/bin/env python3
"""
Earnings Estimates & Surprise Loader

Populates earnings_surprise and earnings_estimates with surprise calculations
from historical earnings data.

Run:
    python3 loadearningsestimates.py
"""

from credential_helper import get_db_password, get_db_config
try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import logging
import os
import sys
import psycopg2
from datetime import date, timedelta
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

from optimal_loader import OptimalLoader

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class EarningsEstimatesLoader(OptimalLoader):
    """Load earnings surprise estimates from historical earnings data."""

    table_name = "earnings_surprise"
    primary_key = ("symbol", "earnings_date")
    watermark_field = "earnings_date"

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        """Compute earnings surprises from historical earnings data."""
        try:
            self.connect()

            # Get historical earnings data
            query = """
                SELECT symbol, earnings_date, actual_eps, expected_eps
                FROM earnings_history
                WHERE symbol = %s AND earnings_date IS NOT NULL
            """
            params = [symbol]

            if since:
                query += " AND earnings_date > %s"
                params.append(since)

            query += " ORDER BY earnings_date DESC LIMIT 100"

            self.cur.execute(query, params)
            results = []

            for row in self.cur.fetchall():
                sym, earnings_date, actual, expected = row

                # Calculate surprise percentage
                if expected and expected != 0:
                    surprise_pct = ((actual - expected) / abs(expected)) * 100
                else:
                    surprise_pct = None

                results.append({
                    'symbol': sym,
                    'earnings_date': earnings_date,
                    'actual_eps': actual,
                    'expected_eps': expected,
                    'surprise_pct': surprise_pct,
                    'created_at': date.today(),
                })

            self.disconnect()
            return results
        except Exception as e:
            logger.error(f"Error fetching earnings estimates for {symbol}: {e}")
            return None

    def insert_batch(self, rows, table_name=None):
        """Insert earnings surprise records."""
        if not rows:
            return 0

        try:
            self.connect()
            inserted = 0

            for row in rows:
                self.cur.execute("""
                    INSERT INTO earnings_surprise
                    (symbol, earnings_date, actual_eps, expected_eps, surprise_pct, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, earnings_date) DO UPDATE
                    SET actual_eps = EXCLUDED.actual_eps,
                        expected_eps = EXCLUDED.expected_eps,
                        surprise_pct = EXCLUDED.surprise_pct
                """, (
                    row['symbol'],
                    row['earnings_date'],
                    row['actual_eps'],
                    row['expected_eps'],
                    row['surprise_pct'],
                    row['created_at'],
                ))
                inserted += 1

            self.conn.commit()
            self.disconnect()
            return inserted
        except Exception as e:
            logger.error(f"Error inserting earnings surprises: {e}")
            if self.conn:
                self.conn.rollback()
            return 0

    def run(self):
        """Load earnings surprises for all symbols."""
        logger.info("=" * 70)
        logger.info("EARNINGS ESTIMATES & SURPRISE LOADER")
        logger.info("=" * 70)

        try:
            self.connect()

            # Get all symbols with earnings history
            self.cur.execute("""
                SELECT DISTINCT symbol FROM earnings_history
                WHERE earnings_date IS NOT NULL
                ORDER BY symbol
            """)
            symbols = [row[0] for row in self.cur.fetchall()]
            self.disconnect()

            if not symbols:
                logger.info("No earnings history found")
                return

            logger.info(f"Processing earnings surprises for {len(symbols)} symbols...")

            total_inserted = 0
            for idx, symbol in enumerate(symbols):
                try:
                    rows = self.fetch_incremental(symbol, None)
                    if rows:
                        inserted = self.insert_batch(rows)
                        total_inserted += inserted

                        if (idx + 1) % 100 == 0:
                            logger.info(f"  {idx + 1}/{len(symbols)} symbols processed")
                except Exception as e:
                    logger.warning(f"  Error processing {symbol}: {e}")
                    continue

            logger.info(f"\n✓ Completed: Inserted {total_inserted} earnings surprise records")
        except Exception as e:
            logger.error(f"FATAL ERROR: {e}")
            sys.exit(1)


if __name__ == '__main__':
    loader = EarningsEstimatesLoader()
    loader.run()
