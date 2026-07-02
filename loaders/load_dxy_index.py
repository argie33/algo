#!/usr/bin/env python3
"""Fetch actual ICE DXY (US Dollar Index) from Yahoo Finance."""

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

import logging  # noqa: E402

from utils.db.context import DatabaseContext  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def fetch_dxy_from_yahoo() -> list[dict[str, Any]]:
    """Fetch actual ICE DXY (US Dollar Index) from Yahoo Finance API.

    Uses ticker DX-Y.NYB (Intercontinental Exchange listing on Yahoo Finance).

    Returns empty list if Yahoo Finance is unavailable (doesn't fall back to proxies).
    Callers (API, dashboard) must handle missing DXY with explicit error/unavailable markers.

    Returns:
        list: [{"date": "2026-06-29", "value": 101.13}, ...] or empty list if unavailable
    """
    try:
        import yfinance as yf

        logger.debug("Attempting to fetch DXY (DX-Y.NYB) from Yahoo Finance...")

        end_date = date.today()
        start_date = end_date - timedelta(days=365)

        dxy = yf.download("DX-Y.NYB", start=start_date, end=end_date, progress=False)

        if dxy is None or len(dxy) == 0:
            logger.debug(
                "[DXY] Yahoo Finance returned no data for DX-Y.NYB ticker."
            )
            return []

        rows = []
        for idx, row in dxy.iterrows():
            # idx is a pandas Timestamp; convert to date string
            if hasattr(idx, 'tz') and idx.tz is not None:
                date_str = idx.tz_localize(None).date().isoformat()
            else:
                date_str = idx.date().isoformat()

            value = float(row["Close"])
            rows.append({"date": date_str, "value": value})

        logger.info(f"Fetched {len(rows)} DXY values from Yahoo Finance (DX-Y.NYB)")
        return rows

    except ImportError as e:
        logger.error(
            f"[CRITICAL] Yahoo Finance fetch failed: required 'yfinance' library not available: {e}. "
            f"Cannot fetch DXY data. This is a dependency error, not a transient API failure."
        )
        return []
    except Exception as e:
        logger.warning(f"[DXY] Failed to fetch from Yahoo Finance: {e}")
        return []


def store_dxy_data(rows: list[dict[str, Any]]) -> int:
    """Store DXY data in economic_data table."""
    if not rows:
        return 0

    try:
        with DatabaseContext("write") as cur:
            # Delete existing DXY data to avoid duplicates
            cur.execute("DELETE FROM economic_data WHERE series_id = %s", ("DXY_ICE",))

            # Insert new data
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO economic_data (series_id, date, value)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (series_id, date) DO UPDATE SET value = EXCLUDED.value
                    """,
                    ("DXY_ICE", row["date"], row["value"]),
                )

            logger.info(f"Stored {len(rows)} DXY records in database")
            return len(rows)

    except Exception as e:
        logger.error(f"Failed to store DXY data: {e}")
        return 0


def main() -> int:
    """Fetch and store actual ICE DXY data from Yahoo Finance.

    Per governance: "Fail-fast on missing data. No silent fallbacks."
    When DXY data is unavailable, the API gracefully omits it from responses.
    """
    logger.info("Starting DXY (ICE) data fetch...")

    rows = fetch_dxy_from_yahoo()

    if not rows:
        logger.warning("[DXY] Could not fetch DXY data from Yahoo Finance. Economic dashboard will omit DXY_ICE.")
        return 0

    count = store_dxy_data(rows)

    if count > 0:
        logger.info(f"SUCCESS: Stored {count} DXY records")
        return 0
    else:
        logger.error(
            "[CRITICAL] Could not store DXY data to database. "
            "Fetched data but storage failed - DXY data will be missing from economic indicators."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
