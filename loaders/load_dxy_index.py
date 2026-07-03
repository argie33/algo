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
            logger.warning(
                "[DXY] Yahoo Finance returned no data for DX-Y.NYB ticker."
            )
            raise RuntimeError("[DXY] No data available from Yahoo Finance for DX-Y.NYB")

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
        raise RuntimeError(f"[DXY] yfinance library not available: {e}") from e
    except Exception as e:
        logger.error(f"[DXY] Failed to fetch from Yahoo Finance: {e}")
        raise RuntimeError(f"[DXY] Yahoo Finance fetch failed: {e}") from e


def store_dxy_data(rows: list[dict[str, Any]]) -> int:
    """Store DXY data in economic_data table.

    Governance: Fail-fast on errors. Distinguishable exit codes.

    Returns: Number of rows stored (>0 for success)
    Raises: RuntimeError if input is empty or storage fails
    """
    if not rows:
        raise RuntimeError(
            "[DXY] Cannot store empty rows. "
            "Fetch must return data or raise exception, not return empty list."
        )

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

    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(
            f"[DXY] Failed to store {len(rows)} DXY records to database: {e}. "
            f"Data was fetched but persistence failed. Cannot proceed."
        ) from e


def main() -> int:
    """Fetch and store actual ICE DXY data from Yahoo Finance.

    Governance: Fail-fast on missing data. No silent fallbacks.
    Exit codes must be unambiguous:
    - 0: Data fetched and stored successfully
    - 1: Data fetch or storage failed (error occurred)
    - 2: No data available (graceful degradation, not an error)
    """
    logger.info("Starting DXY (ICE) data fetch...")

    try:
        rows = fetch_dxy_from_yahoo()
        if not rows:
            logger.warning(
                "[DXY] Fetch succeeded but returned no data. "
                "Exit code 2 (DATA_UNAVAILABLE) — economic dashboard will omit DXY_ICE. "
                "Operator should investigate why Yahoo Finance returned no DXY data."
            )
            return 2  # Unambiguous: data is unavailable, not an error

        count = store_dxy_data(rows)
        logger.info(f"SUCCESS: Stored {count} DXY records. Exit code 0 (SUCCESS).")
        return 0

    except RuntimeError as e:
        logger.error(f"[DXY] {e}. Exit code 1 (ERROR).")
        return 1
    except Exception as e:
        logger.error(f"[DXY] Unexpected error: {e}. Exit code 1 (ERROR).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
