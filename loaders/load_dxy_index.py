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
from typing import Any

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

import logging  # noqa: E402

from utils.db.context import DatabaseContext  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fetch_dxy_from_yahoo() -> list[dict[str, Any]]:
    """Fetch actual ICE DXY (US Dollar Index) from Yahoo Finance API.

    Returns gracefully empty if Yahoo Finance is unavailable - the API and dashboard
    will handle missing economic data via explicit data_unavailable markers.

    Returns:
        list: [{"date": "2026-06-29", "value": 101.13}, ...] or empty list if unavailable
    """
    try:
        import yfinance as yf

        logger.info("Fetching DXY (^DXY) from Yahoo Finance...")

        end_date = date.today()
        start_date = end_date - timedelta(days=365)

        dxy = yf.download("^DXY", start=start_date, end=end_date, progress=False)

        if dxy is None or len(dxy) == 0:
            logger.warning(
                "[DXY] Yahoo Finance returned no data. "
                "Economic dashboard will skip DXY. "
                "Check Yahoo Finance API availability."
            )
            return []

        rows = []
        for idx, row in dxy.iterrows():
            if idx.tz_aware:
                date_str = idx.tz_localize(None).date().isoformat()
            else:
                date_str = idx.date().isoformat()

            value = float(row["Close"])
            rows.append({"date": date_str, "value": value})

        logger.info(f"Fetched {len(rows)} DXY values from Yahoo Finance")
        return rows

    except ImportError as e:
        logger.warning(f"[DXY] yfinance not installed: {e}. Skipping DXY data.")
        return []
    except Exception as e:
        logger.warning(f"[DXY] Failed to fetch from Yahoo Finance: {e}. Skipping DXY data.")
        return []


def store_dxy_data(rows: list[dict[str, Any]]) -> int:
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


def main() -> int:
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
