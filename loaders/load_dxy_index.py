#!/usr/bin/env python3
"""
Fetch actual ICE DXY (US Dollar Index).

The real DXY is published by Intercontinental Exchange (ICE), not FRED.
FRED's DTWEXBGS is a trade-weighted proxy but not the actual index.

KNOWN ISSUE (as of 2026-06-29):
  Yahoo Finance's ^DXY ticker no longer returns data ("possibly delisted").
  This loader attempts multiple data sources:
  1. IEX Cloud API (if configured)
  2. Yahoo Finance (fallback, likely to fail)

  When all sources fail, this loader gracefully skips DXY data.
  The API will omit DXY_ICE from economic indicators when unavailable.

WORKAROUND:
  Use FRED's DTWEXBGS (already available) as a temporary proxy.
  See: https://fred.stlouisfed.org/series/DTWEXBGS
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


def fetch_dxy_from_iex() -> list[dict[str, Any]]:
    """Fetch ICE DXY from IEX Cloud API (if available).

    Returns:
        list: [{"date": "2026-06-29", "value": 101.13}, ...] or empty list if unavailable
    """
    try:
        import requests

        from utils.loaders import get_api_key

        iex_key = get_api_key("algo/iex_cloud", "IEX_API_KEY", required=False)
        if not iex_key:
            logger.debug("[DXY] IEX Cloud API key not configured. Skipping IEX source.")
            return []

        logger.info("Fetching DXY from IEX Cloud...")

        # IEX Cloud historical price endpoint
        # Symbol for DXY might be different - this is a placeholder
        url = "https://cloud.iexapis.com/stable/stock/DXY/chart/1y"
        params = {"token": iex_key}

        resp = requests.get(url, params=params, timeout=(10, 20))
        resp.raise_for_status()
        data = resp.json()

        if not data or not isinstance(data, list):
            logger.warning("[DXY] IEX Cloud returned no data or unexpected format")
            return []

        rows = []
        for item in data:
            try:
                rows.append({
                    "date": item["date"],
                    "value": float(item["close"])
                })
            except (KeyError, ValueError, TypeError) as e:
                logger.debug(f"[DXY] Skipping malformed IEX record: {e}")
                continue

        if rows:
            logger.info(f"Fetched {len(rows)} DXY values from IEX Cloud")
        else:
            logger.warning("[DXY] IEX Cloud returned no valid records")

        return rows

    except ImportError as e:
        logger.error(
            f"[CRITICAL] IEX Cloud fetch error: required 'requests' library not available: {e}. "
            f"Cannot fetch DXY data from IEX Cloud. This is a dependency error, not a transient API failure."
        )
        return []
    except Exception as e:
        logger.warning(f"[DXY] Failed to fetch from IEX Cloud: {e}")
        return []


def fetch_dxy_from_yahoo() -> list[dict[str, Any]]:
    """Fetch actual ICE DXY (US Dollar Index) from Yahoo Finance API.

    NOTE: As of 2026-06-29, Yahoo Finance's ^DXY ticker returns "possibly delisted" errors.
    This method serves as a fallback for if/when the data becomes available again.

    Returns gracefully empty if Yahoo Finance is unavailable - the API and dashboard
    will handle missing economic data via explicit data_unavailable markers.

    Returns:
        list: [{"date": "2026-06-29", "value": 101.13}, ...] or empty list if unavailable
    """
    try:
        import yfinance as yf

        logger.debug("Attempting to fetch DXY (^DXY) from Yahoo Finance...")

        end_date = date.today()
        start_date = end_date - timedelta(days=365)

        dxy = yf.download("^DXY", start=start_date, end=end_date, progress=False)

        if dxy is None or len(dxy) == 0:
            logger.debug(
                "[DXY] Yahoo Finance returned no data. "
                "This is expected - ^DXY ticker is currently unavailable on Yahoo Finance."
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

        logger.info(f"Fetched {len(rows)} DXY values from Yahoo Finance (unexpected - ticker should be unavailable)")
        return rows

    except ImportError as e:
        logger.error(
            f"[CRITICAL] Yahoo Finance fetch failed: required 'yfinance' library not available: {e}. "
            f"Cannot fetch DXY data. This is a dependency error, not a transient API failure."
        )
        return []
    except Exception as e:
        logger.debug(f"[DXY] Failed to fetch from Yahoo Finance: {e} (expected)")
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
    """Fetch and store actual ICE DXY data from available sources."""
    logger.info("Starting DXY (ICE) data fetch...")

    # Try multiple sources in order of preference
    rows = []

    # 1. Try IEX Cloud (if configured)
    rows = fetch_dxy_from_iex()
    if rows:
        logger.info(f"Using DXY data from IEX Cloud ({len(rows)} records)")
    else:
        # 2. Try Yahoo Finance (fallback)
        rows = fetch_dxy_from_yahoo()
        if rows:
            logger.info(f"Using DXY data from Yahoo Finance ({len(rows)} records)")

    if not rows:
        logger.warning(
            "[DXY] Could not fetch DXY data from any source. "
            "Economic dashboard will omit DXY_ICE from indicators. "
            "WORKAROUND: Use FRED's DTWEXBGS as temporary proxy "
            "(https://fred.stlouisfed.org/series/DTWEXBGS)"
        )
        # Return 0 (success) instead of 1 - this is an expected graceful degradation
        # The API handles missing DXY_ICE by simply omitting it from responses
        return 0

    # Store in database
    count = store_dxy_data(rows)

    if count > 0:
        logger.info(f"SUCCESS: Stored {count} DXY records")
        return 0
    else:
        logger.error(
            "[CRITICAL] Could not store DXY data to database. "
            "Fetched data but storage failed - DXY data will be missing from economic indicators. "
            "This will impact circuit breaker calculations that depend on market sentiment data."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
