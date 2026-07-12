#!/usr/bin/env python3
"""Fetch US economic data from Federal Reserve Economic Data (FRED) API.

Fetches macro indicators:
- T10Y2Y: 10-year minus 2-year Treasury yield spread (recession predictor)
- FEDFUNDS: Federal Funds Rate (monetary policy)
- BAMLH0A0HYM2: High Yield OAS spread (credit risk)
- ICSA: Initial Jobless Claims (labor market)

FRED API is FREE: https://fred.stlouisfed.org/docs/api/
Get free API key: https://fred.stlouisfed.org/docs/api/api_key.html

Environment variable: FRED_API_KEY (required)

Loader metadata (for orchestrator integration):
- LOADER_TYPE: 'auxiliary' (optional enrichment, doesn't block trading)
- REQUIRED_SYMBOLS: None (macro data, not symbol-specific)
- SCHEMA: {'series_id', 'date', 'value', 'data_unavailable', 'reason'}
- COMPLETENESS_THRESHOLD: 80% (some macro series may have gaps)
"""

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

import logging  # noqa: E402
import os  # noqa: E402

from loaders.timeout_config import configure_socket_timeout, get_http_timeout  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

configure_socket_timeout(30)

# Loader metadata (used by orchestrator)
LOADER_TYPE = "auxiliary"  # Optional enrichment, won't block trading if unavailable
REQUIRED_SYMBOLS = None  # Macro data, not symbol-specific
COMPLETENESS_THRESHOLD = 0.80  # 80% completeness acceptable for macro series (gaps common)

# FRED series to fetch (all daily)
FRED_SERIES = {
    "T10Y2Y": "10-Year minus 2-Year Treasury Spread (recession indicator)",
    "FEDFUNDS": "Federal Funds Rate (monetary policy)",
    "BAMLH0A0HYM2": "ICE BofA High Yield OAS (credit risk)",
    "ICSA": "Initial Jobless Claims (labor market)",
}


def fetch_from_fred(api_key: str, series_id: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    """Fetch single FRED series via REST API.

    Args:
        api_key: FRED API key (free from https://fred.stlouisfed.org/docs/api/api_key.html)
        series_id: FRED series ID (e.g., "T10Y2Y")
        start_date: Start date (inclusive)
        end_date: End date (inclusive)

    Returns:
        List of {"date": "2026-01-01", "value": 1.23} dicts, or empty list if unavailable
    """
    try:
        import requests

        http_timeout = get_http_timeout()
        url = "https://api.stlouisfed.org/fred/series/observations"
        params = {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start_date.isoformat(),
            "observation_end": end_date.isoformat(),
        }

        logger.debug(f"[FRED] Fetching {series_id} from {start_date} to {end_date}...")
        response = requests.get(url, params=params, timeout=http_timeout)
        response.raise_for_status()

        data = response.json()
        if "observations" not in data:
            logger.warning(f"[FRED] No observations for {series_id}")
            return []

        # Convert FRED response to standard format, filter out missing values
        records = []
        for obs in data["observations"]:
            if obs.get("value", ".") != ".":  # FRED uses "." for missing data
                try:
                    records.append(
                        {
                            "date": obs["date"],
                            "value": float(obs["value"]),
                        }
                    )
                except (ValueError, KeyError):
                    continue  # Skip malformed records

        logger.info(f"[FRED] {series_id}: fetched {len(records)} observations")
        return records

    except ImportError:
        logger.error("[FRED] requests library not available (pip install requests)")
        return []
    except requests.RequestException as e:  # type: ignore
        logger.warning(f"[FRED] {series_id} fetch failed: {e}")
        return []
    except Exception as e:
        logger.error(f"[FRED] {series_id} unexpected error: {e}")
        return []


def store_economic_data(series_id: str, records: list[dict[str, Any]]) -> int:
    """Store economic data in database.

    Args:
        series_id: FRED series ID
        records: List of {"date": "2026-01-01", "value": 1.23} dicts

    Returns:
        Number of rows inserted
    """
    if not records:
        logger.warning(f"[FRED] No records to store for {series_id}")
        return 0

    try:
        with DatabaseContext("write") as cur:
            # Clear old data for this series (keep only latest)
            cur.execute("DELETE FROM economic_data WHERE series_id = %s", (series_id,))

            # Insert new data
            for record in records:
                cur.execute(
                    """
                    INSERT INTO economic_data (series_id, date, value, data_unavailable, reason)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        series_id,
                        record["date"],
                        record["value"],
                        False,
                        None,
                    ),
                )

            inserted = len(records)
            logger.info(f"[FRED] {series_id}: inserted {inserted} rows")
            return inserted

    except Exception as e:
        logger.error(f"[FRED] Failed to store {series_id}: {e}")
        return 0


def mark_unavailable(series_id: str, reason: str) -> None:
    """Mark series as unavailable in database."""
    try:
        with DatabaseContext("write") as cur:
            cur.execute(
                """
                INSERT INTO economic_data (series_id, date, value, data_unavailable, reason)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (series_id, date.today(), None, True, reason),
            )
            logger.info(f"[FRED] Marked {series_id} as data_unavailable: {reason}")
    except Exception as e:
        logger.error(f"[FRED] Failed to mark {series_id} unavailable: {e}")


def load() -> dict[str, Any]:
    """Fetch and store FRED economic data.

    Returns:
        dict with status info
    """
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        logger.warning("[FRED] FRED_API_KEY not set - skipping economic data load")
        for series_id in FRED_SERIES:
            mark_unavailable(
                series_id,
                "FRED_API_KEY environment variable not set. "
                "Get free key at https://fred.stlouisfed.org/docs/api/api_key.html",
            )
        return {"status": "skipped", "reason": "FRED_API_KEY not configured"}

    # Fetch data for last 365 days (FRED often has 1-day lag)
    end_date = date.today()
    start_date = end_date - timedelta(days=365)

    total_inserted = 0
    for series_id, description in FRED_SERIES.items():
        logger.info(f"[FRED] Processing {series_id}: {description}")
        records = fetch_from_fred(api_key, series_id, start_date, end_date)

        if records:
            inserted = store_economic_data(series_id, records)
            total_inserted += inserted
        else:
            mark_unavailable(series_id, f"No data from FRED API (fetched {start_date} to {end_date})")

    logger.info(f"[FRED] Load complete: {total_inserted} total records inserted")
    return {"status": "complete", "records_inserted": total_inserted}


if __name__ == "__main__":
    result = load()
    logger.info(f"Result: {result}")
    sys.exit(0 if result.get("status") == "complete" else 1)
