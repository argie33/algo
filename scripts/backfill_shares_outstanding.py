#!/usr/bin/env python3
"""Backfill missing shares_outstanding from yfinance.

Finds symbols where company_info_sec.shares_outstanding IS NULL,
fetches from yfinance, and updates the database.

This fixes the FINRA short interest coverage gap (currently 79.9%).
"""

import logging
import sys
from collections.abc import Iterable
from datetime import datetime

import yfinance as yf

from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backfill_shares_outstanding(symbols: Iterable[str] | None = None) -> dict[str, int]:
    """Backfill missing shares_outstanding values.

    Args:
        symbols: Optional list of symbols to target. If None, uses all with NULL shares.

    Returns:
        Dict with backfill stats: {updated, failed, skipped, total}
    """
    now_et = datetime.now(EASTERN_TZ)

    # Get symbols with NULL shares_outstanding
    with DatabaseContext("read") as cur:
        if symbols:
            placeholders = ','.join(['%s'] * len(symbols))
            cur.execute(f'''
                SELECT symbol FROM company_info_sec
                WHERE symbol IN ({placeholders})
                AND shares_outstanding IS NULL
                ORDER BY symbol
            ''', symbols)
        else:
            cur.execute('''
                SELECT symbol FROM company_info_sec
                WHERE shares_outstanding IS NULL
                ORDER BY symbol
            ''')
        null_symbols = [row[0] for row in cur.fetchall()]

    logger.info(f"Backfilling {len(null_symbols)} symbols with NULL shares_outstanding")

    updated = 0
    failed = 0
    invalid = 0

    for i, symbol in enumerate(null_symbols):
        if (i + 1) % 100 == 0:
            logger.info(f"Progress: {i+1}/{len(null_symbols)} ({100*(i+1)/len(null_symbols):.1f}%)")

        try:
            # Fetch with yfinance
            ticker = yf.Ticker(symbol)
            shares = ticker.info.get("sharesOutstanding")

            if shares and shares > 1000:
                # Valid shares data - update database
                with DatabaseContext("write") as cur:
                    cur.execute('''
                        UPDATE company_info_sec
                        SET shares_outstanding = %s, updated_at = %s
                        WHERE symbol = %s
                    ''', (shares, now_et, symbol))
                updated += 1
                logger.debug(f"{symbol}: Backfilled with {shares:,.0f} shares")
            else:
                invalid += 1
                logger.debug(f"{symbol}: yfinance returned invalid shares ({shares})")

        except Exception as e:
            failed += 1
            logger.debug(f"{symbol}: yfinance fetch failed: {type(e).__name__}: {str(e)[:100]}")

    logger.info(f"Backfill complete: {updated} updated, {failed} failed, {invalid} invalid")
    return {
        "updated": updated,
        "failed": failed,
        "invalid": invalid,
        "total": len(null_symbols),
    }


if __name__ == "__main__":
    try:
        # Check current FINRA coverage before
        with DatabaseContext("read") as cur:
            cur.execute('''
                SELECT COUNT(*) FILTER (WHERE data_unavailable = false) as available,
                       COUNT(*) as total
                FROM short_interest_finra
            ''')
            avail_before, total = cur.fetchone()
            pct_before = 100.0 * avail_before / total

        logger.info(f"FINRA coverage before: {avail_before}/{total} ({pct_before:.1f}%)")

        # Run backfill
        result = backfill_shares_outstanding()

        # Check coverage after
        with DatabaseContext("read") as cur:
            cur.execute('''
                SELECT COUNT(*) FILTER (WHERE data_unavailable = false) as available,
                       COUNT(*) as total
                FROM short_interest_finra
            ''')
            avail_after, total = cur.fetchone()
            pct_after = 100.0 * avail_after / total

        logger.info(f"FINRA coverage after: {avail_after}/{total} ({pct_after:.1f}%)")
        logger.info(f"Coverage improved by {pct_after - pct_before:.1f}%")

        sys.exit(0 if result["updated"] > 0 else 1)

    except Exception as e:
        logger.error(f"Backfill failed: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)
