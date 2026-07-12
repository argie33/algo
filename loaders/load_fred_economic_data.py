#!/usr/bin/env python3
"""FRED Economic Data Loader — US economic indicators.

Fetches macro indicators:
- T10Y2Y: 10-year minus 2-year Treasury yield spread (recession detection)
- FEDFUNDS: Federal Funds Rate (monetary policy)
- BAMLH0A0HYM2: High Yield OAS spread (credit risk)
- ICSA: Initial Jobless Claims (labor market)

Uses FRED API (FREE): https://fred.stlouisfed.org/docs/api/
API key from AWS Secrets Manager (algo/fred) or FRED_API_KEY env var.
"""

import logging
import socket
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

import requests  # noqa: E402

from config.api_endpoints import get_fred_url  # noqa: E402
from loaders.timeout_config import configure_socket_timeout, get_http_timeout  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.loaders import get_api_key  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

configure_socket_timeout(30)

# FRED series to fetch
FRED_SERIES = [
    "T10Y2Y",  # 10Y-2Y spread (recession indicator)
    "FEDFUNDS",  # Federal Funds Rate
    "BAMLH0A0HYM2",  # High Yield OAS
    "ICSA",  # Initial Claims
]


def get_fred_api_key() -> str:
    """Get FRED API key from Secrets Manager or environment variable.

    Tries AWS Secrets Manager first (algo/fred), falls back to FRED_API_KEY env var.
    """
    key = get_api_key("algo/fred", "FRED_API_KEY", required=False)
    if not key:
        logger.warning("[FRED] API key not found - will mark data unavailable")
        return ""
    return key


def fetch_from_fred(api_key: str, series_id: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    """Fetch single FRED series via REST API.

    Args:
        api_key: FRED API key
        series_id: FRED series ID (e.g., "T10Y2Y")
        start_date: Start date
        end_date: End date

    Returns:
        List of {"date": "2026-01-01", "value": 1.23} dicts
    """
    if not api_key:
        return []

    try:
        fred_url = f"{get_fred_url()}/series/observations"
        params = {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start_date.isoformat(),
            "observation_end": end_date.isoformat(),
        }

        logger.debug(f"[FRED] Fetching {series_id}...")
        http_timeout = get_http_timeout()
        response = requests.get(fred_url, params=params, timeout=http_timeout)
        response.raise_for_status()

        data = response.json()
        observations = data.get("observations", [])

        # Filter out missing values (FRED uses "." for missing)
        records = []
        for obs in observations:
            if obs.get("value", ".") != ".":
                try:
                    records.append({"date": obs["date"], "value": float(obs["value"])})
                except (ValueError, KeyError):
                    pass

        logger.info(f"[FRED] {series_id}: fetched {len(records)} observations")
        return records

    except Exception as e:
        logger.warning(f"[FRED] {series_id} fetch failed: {e}")
        return []


def store_economic_data(series_id: str, records: list[dict[str, Any]]) -> int:
    """Store economic data in database."""
    if not records:
        return 0

    try:
        with DatabaseContext("write") as cur:
            cur.execute("DELETE FROM economic_data WHERE series_id = %s", (series_id,))
            for record in records:
                cur.execute(
                    """INSERT INTO economic_data (series_id, date, value, data_unavailable, reason)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (series_id, record["date"], record["value"], False, None),
                )
        return len(records)
    except Exception as e:
        logger.error(f"[FRED] Failed to store {series_id}: {e}")
        return 0


def mark_unavailable(series_id: str, reason: str) -> None:
    """Mark series as unavailable in database."""
    try:
        with DatabaseContext("write") as cur:
            cur.execute(
                """INSERT INTO economic_data (series_id, date, value, data_unavailable, reason)
                   VALUES (%s, %s, %s, %s, %s)""",
                (series_id, date.today(), None, True, reason),
            )
    except Exception as e:
        logger.error(f"[FRED] Failed to mark {series_id} unavailable: {e}")


def load() -> dict[str, Any]:
    """Fetch and store FRED economic data."""
    api_key = get_fred_api_key()
    if not api_key:
        logger.warning("[FRED] No API key configured - marking all series unavailable")
        for series_id in FRED_SERIES:
            mark_unavailable(
                series_id, "FRED_API_KEY not configured in Secrets Manager or environment"
            )
        return {"status": "skipped", "reason": "No FRED API key"}

    end_date = date.today()
    start_date = end_date - timedelta(days=365)
    total_inserted = 0

    socket.setdefaulttimeout(30.0)

    for i, series_id in enumerate(FRED_SERIES):
        # Rate limiting: 5s between requests
        if i > 0:
            time.sleep(5.0)

        logger.info(f"[FRED] Processing {series_id}...")
        records = fetch_from_fred(api_key, series_id, start_date, end_date)

        if records:
            inserted = store_economic_data(series_id, records)
            total_inserted += inserted
        else:
            mark_unavailable(series_id, "No data from FRED API")

    logger.info(f"[FRED] Load complete: {total_inserted} records inserted")
    return {"status": "complete", "records_inserted": total_inserted}


if __name__ == "__main__":
    result = load()
    sys.exit(0 if result.get("status") == "complete" else 1)
