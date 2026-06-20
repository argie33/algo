#!/usr/bin/env python3
"""Fix invalid VIX values in market_health_daily table.

VIX must be > 0. This script sets any VIX values <= 0 to NULL.
"""

import logging
import sys
from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def fix_invalid_vix():
    """Update market_health_daily to set invalid VIX values to NULL."""
    try:
        with DatabaseContext("write") as cur:
            # Find rows with invalid VIX
            cur.execute(
                "SELECT COUNT(*) as invalid_count FROM market_health_daily WHERE vix_level IS NOT NULL AND vix_level <= 0"
            )
            row = cur.fetchone()
            invalid_count = row[0] if row else 0

            if invalid_count == 0:
                logger.info("No invalid VIX values found in market_health_daily")
                return 0

            logger.warning(f"Found {invalid_count} rows with invalid VIX values (vix_level <= 0)")

            # Fix by setting to NULL
            cur.execute(
                "UPDATE market_health_daily SET vix_level = NULL WHERE vix_level IS NOT NULL AND vix_level <= 0"
            )

            fixed_count = cur.rowcount
            logger.info(f"Fixed {fixed_count} rows: set vix_level = NULL")

            return fixed_count
    except Exception as e:
        logger.error(f"Failed to fix invalid VIX values: {e}")
        raise


if __name__ == "__main__":
    try:
        fixed = fix_invalid_vix()
        print(f"✓ Fixed {fixed} rows with invalid VIX values")
        sys.exit(0)
    except Exception as e:
        print(f"✗ Failed: {e}")
        sys.exit(1)
