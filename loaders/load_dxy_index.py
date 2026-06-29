#!/usr/bin/env python3
"""
Fetch actual ICE DXY (US Dollar Index) from Yahoo Finance.

The real DXY is published by Intercontinental Exchange (ICE), not FRED.
FRED's DTWEXBGS is a trade-weighted proxy but not the actual index.

This loader fetches the real DXY (^DXY ticker) from Yahoo Finance.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

import logging  # noqa: E402

from utils.db.context import DatabaseContext  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fetch_dxy_from_yahoo():
    """Fetch actual ICE DXY from Yahoo Finance API.

    Returns:
        list: [{"date": "2026-06-29", "value": 101.13}, ...]
    """
    try:
        import yfinance as yf

        # Fetch DXY (^DXY on Yahoo)
        logger.info("Fetching DXY (^DXY) from Yahoo Finance...")

        end_date = date.today()
        start_date = end_date - timedelta(days=365)

        dxy = yf.download("^DXY", start=start_date, end=end_date, progress=False)

        if dxy is None or len(dxy) == 0:
            logger.error("Yahoo Finance returned no data for DXY")
            return []

        # Convert to FRED format (date, value)
        rows = []
        for idx, row in dxy.iterrows():
            if idx.tz_aware:
                date_str = idx.tz_localize(None).date().isoformat()
            else:
                date_str = idx.date().isoformat()

            # Use Close price as the DXY value
            value = float(row["Close"])
            rows.append({"date": date_str, "value": value})

        logger.info(f"Fetched {len(rows)} DXY values from Yahoo Finance")
        return rows

    except ImportError:
        logger.error("yfinance not installed. Install with: pip install yfinance")
        return []
    except Exception as e:
        logger.error(f"Failed to fetch DXY from Yahoo: {e}")
        return []


def store_dxy_data(rows: list) -> int:
    """Store DXY data in economic_data table."""
    if not rows:
        return 0

    try:
        with DatabaseContext("write") as cur:
            # Delete existing DXY data to avoid duplicates
            cur.execute('DELETE FROM economic_data WHERE series_id = %s', ('DXY_ICE',))

            # Insert new data
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO economic_data (series_id, date, value)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (series_id, date) DO UPDATE SET value = EXCLUDED.value
                    """,
                    ('DXY_ICE', row['date'], row['value'])
                )

            logger.info(f"Stored {len(rows)} DXY records in database")
            return len(rows)

    except Exception as e:
        logger.error(f"Failed to store DXY data: {e}")
        return 0


def main():
    """Fetch and store actual ICE DXY data."""
    logger.info("Starting DXY (ICE) data fetch...")

    # Fetch from Yahoo Finance
    rows = fetch_dxy_from_yahoo()

    if not rows:
        logger.error("FAILED: Could not fetch DXY data")
        return 1

    # Store in database
    count = store_dxy_data(rows)

    if count > 0:
        logger.info(f"SUCCESS: Stored {count} DXY records")
        return 0
    else:
        logger.error("FAILED: Could not store DXY data")
        return 1


if __name__ == "__main__":
    sys.exit(main())
