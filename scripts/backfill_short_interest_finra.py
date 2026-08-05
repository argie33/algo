#!/usr/bin/env python3
"""Backfill short_pct values in short_interest_finra.

ISSUE:
- short_interest_finra was loaded on 2026-07-31
- company_info_sec was updated on 2026-08-03 with more shares_outstanding data
- Result: 1,864 FINRA rows have short_shares but NULL short_pct due to missing
  shares_outstanding at loader run time

SOLUTION:
Re-compute short_pct for all FINRA rows now that company_info_sec has the data.

Run: python3 scripts/backfill_short_interest_finra.py
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

def main():
    """Re-compute short_pct for FINRA rows with short_shares but NULL short_pct."""

    logger.info("Starting short_interest_finra backfill...")

    # Find rows with short_shares but NULL short_pct
    with DatabaseContext("read") as cur:
        cur.execute('''
            SELECT s.symbol, s.settlement_date, s.short_shares
            FROM short_interest_finra s
            WHERE s.short_pct IS NULL AND s.short_shares IS NOT NULL
            ORDER BY s.symbol
        ''')
        rows_to_fix = cur.fetchall()

    logger.info(f"Found {len(rows_to_fix)} FINRA rows with short_shares but NULL short_pct")

    if not rows_to_fix:
        logger.info("No backfill needed")
        return

    # Get all shares_outstanding data
    with DatabaseContext("read") as cur:
        cur.execute('''
            SELECT symbol, shares_outstanding, filing_date
            FROM company_info_sec
            WHERE shares_outstanding IS NOT NULL AND shares_outstanding > 1000
            ORDER BY symbol, filing_date DESC
        ''')
        company_data = {}
        for sym, outstanding, _ in cur.fetchall():
            if sym not in company_data:  # Keep most recent
                company_data[sym] = outstanding

    logger.info(f"Loaded shares_outstanding for {len(company_data)} symbols")

    # Compute short_pct where possible
    updated_count = 0
    skipped_count = 0
    now_et = datetime.now(EASTERN_TZ)

    with DatabaseContext("write") as cur:
        for symbol, settlement_date, short_shares in rows_to_fix:
            outstanding = company_data.get(symbol)

            if outstanding and outstanding > 1000:
                # Compute short_pct
                short_pct = round((short_shares / outstanding) * 100, 2)
                cur.execute("""
                    UPDATE short_interest_finra
                    SET short_pct = %s, data_unavailable = FALSE, reason = NULL, updated_at = %s
                    WHERE symbol = %s AND settlement_date = %s
                """, (short_pct, now_et, symbol, settlement_date))
                updated_count += 1
                if updated_count <= 5:
                    logger.info(f"  {symbol}: computed short_pct={short_pct}% (short_shares={short_shares}, outstanding={outstanding})")
            else:
                skipped_count += 1

    logger.info(f"Backfill complete: {updated_count} updated, {skipped_count} skipped (no shares_outstanding)")

    # Verify
    with DatabaseContext("read") as cur:
        cur.execute('''
            SELECT COUNT(*) FROM short_interest_finra
            WHERE short_pct IS NULL AND short_shares IS NOT NULL
        ''')
        remaining = cur.fetchone()[0]

    if remaining > 0:
        logger.warning(f"After backfill: {remaining} rows still have short_shares but NULL short_pct")
        logger.warning("These are likely symbols without shares_outstanding data in company_info_sec")
    else:
        logger.info("✓ All short_interest_finra rows backfilled successfully!")

    # Update positioning_metrics since it depends on short_interest_finra
    logger.info("Updating positioning_metrics to reflect new short_interest_finra values...")
    with DatabaseContext("write") as cur:
        # Re-compute positioning metrics for symbols we just fixed
        cur.execute('''
            UPDATE positioning_metrics pm
            SET short_interest_pct = (
                SELECT short_pct FROM short_interest_finra s
                WHERE s.symbol = pm.symbol
                ORDER BY s.settlement_date DESC LIMIT 1
            )
            WHERE EXISTS (
                SELECT 1 FROM short_interest_finra s
                WHERE s.symbol = pm.symbol
                  AND s.short_pct IS NOT NULL
                  AND pm.short_interest_pct IS NULL
            )
        ''')
        cur.connection.commit()

    logger.info("✓ Positioning metrics updated with new short interest data")

if __name__ == "__main__":
    main()
