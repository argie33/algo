#!/usr/bin/env python3
"""Economic Calendar Loader — Upcoming macro release dates from FRED."""
import sys
import logging
import os
import json
import socket
from datetime import date, timedelta
from typing import Optional, List
import requests
import boto3

from utils.db.context import DatabaseContext
from utils.infrastructure.url_validator import validate_url
from utils.loaders.helpers import get_api_key
from config.api_endpoints import get_fred_url
from utils.infrastructure.timeout import ExecutionTimeout

logger = logging.getLogger(__name__)

# FRED series IDs → display names and importance
TRACKED_SERIES = {
    "CPIAUCSL":     ("CPI - Inflation",                "HIGH"),
    "PCEPILFE":     ("Core PCE Inflation",             "HIGH"),
    "PAYEMS":       ("Non-Farm Payrolls (NFP)",        "HIGH"),
    "UNRATE":       ("Unemployment Rate",              "HIGH"),
    "GDPC1":        ("GDP (Real)",                     "HIGH"),
    "FEDFUNDS":     ("Federal Funds Rate",             "HIGH"),
    "AHETPI":       ("Average Hourly Earnings",        "HIGH"),
    "JTSJOL":       ("JOLTS Job Openings",             "HIGH"),
    "ICSA":         ("Initial Jobless Claims",         "MEDIUM"),
    "INDPRO":       ("Industrial Production",          "MEDIUM"),
    "RSXFS":        ("Retail Sales",                   "MEDIUM"),
    "HOUST":        ("Housing Starts",                 "MEDIUM"),
    "PERMIT":       ("Building Permits",               "MEDIUM"),
    "TCU":          ("Capacity Utilization",           "MEDIUM"),
    "UMCSENT":      ("Consumer Sentiment (UMich)",     "MEDIUM"),
    "MFGBDPHI":     ("Philly Fed Manufacturing Index", "MEDIUM"),
    "T10Y2Y":       ("Yield Curve (10Y-2Y)",           "LOW"),
    "BAMLH0A0HYM2": ("HY Credit Spread",               "LOW"),
    "CFNAI":        ("Chicago Fed Activity Index",     "LOW"),
}

# FOMC meeting schedule (manually maintained — FRED doesn't publish these via API)
# Format: (date, description)
FOMC_DATES_2026 = [
    ("2026-01-28", "FOMC Meeting Decision"),
    ("2026-03-18", "FOMC Meeting Decision"),
    ("2026-05-06", "FOMC Meeting Decision"),
    ("2026-06-17", "FOMC Meeting Decision"),
    ("2026-07-29", "FOMC Meeting Decision"),
    ("2026-09-16", "FOMC Meeting Decision"),
    ("2026-11-04", "FOMC Meeting Decision"),
    ("2026-12-16", "FOMC Meeting Decision"),
]

FOMC_DATES_2027 = [
    ("2027-01-27", "FOMC Meeting Decision"),
    ("2027-03-17", "FOMC Meeting Decision"),
    ("2027-05-05", "FOMC Meeting Decision"),
    ("2027-06-16", "FOMC Meeting Decision"),
    ("2027-07-28", "FOMC Meeting Decision"),
    ("2027-09-15", "FOMC Meeting Decision"),
    ("2027-11-03", "FOMC Meeting Decision"),
    ("2027-12-15", "FOMC Meeting Decision"),
]

def _get_fred_api_key() -> str:
    """Get FRED API key from Secrets Manager, fall back to env var."""
    return get_api_key('algo/fred', 'FRED_API_KEY') or ""

def _fetch_release_dates(series_id: str, api_key: str, start: date, end: date) -> List[date]:
    """Fetch upcoming release dates for a FRED series via the releases endpoint with timeout protection."""
    try:
        fred_base = get_fred_url()

        # SECURITY FIX S-05: Validate FRED URLs to prevent SSRF attacks
        is_valid, error_msg = validate_url(fred_base, allowed_domains=['stlouisfed.org', 'api.stlouisfed.org'])
        if not is_valid:
            # SECURITY FIX S-12: Don't log full URL (exposes infrastructure)
            logger.error(f"SSRF prevention: Invalid FRED URL: {error_msg}")
            return []

        # Get the release ID for this series with granular timeouts
        try:
            r = requests.get(
                f"{fred_base}/series/release",
                params={"series_id": series_id, "api_key": api_key, "file_type": "json"},
                timeout=(5, 10),
            )
            r.raise_for_status()
            data = r.json()
            releases = data.get("releases", [])
            if not releases:
                return []
            release_id = releases[0]["id"]
        except requests.exceptions.Timeout:
            logger.warning(f"FRED release ID fetch timeout for {series_id}")
            return []
        except requests.exceptions.ConnectionError:
            logger.warning(f"FRED release ID fetch connection error for {series_id}")
            return []

        # Get upcoming release dates for this release with granular timeouts
        try:
            r2 = requests.get(
                f"{fred_base}/release/dates",
                params={
                    "release_id": release_id,
                    "api_key": api_key,
                    "file_type": "json",
                    "realtime_start": str(start),
                    "realtime_end": str(end),
                    "sort_order": "asc",
                    "limit": 12,
                },
                timeout=(5, 10),
            )
            r2.raise_for_status()
            dates_data = r2.json()
            return [
                date.fromisoformat(d["date"])
                for d in dates_data.get("release_dates", [])
                if d.get("date")
            ]
        except requests.exceptions.Timeout:
            logger.warning(f"FRED release dates fetch timeout for {series_id}")
            return []
        except requests.exceptions.ConnectionError:
            logger.warning(f"FRED release dates fetch connection error for {series_id}")
            return []
    except Exception as e:
        logger.debug(f"FRED release dates fetch failed for {series_id}: {e}")
        return []

def _load_economic_calendar(today: date) -> int:
    # Set socket-level timeout to catch hanging connections early
    socket.setdefaulttimeout(15.0)

    api_key = _get_fred_api_key()
    if not api_key:
        logger.warning("FRED_API_KEY not available — skipping economic calendar load")
        return 0

    start = today
    end = today + timedelta(days=90)
    records = []

    # Fetch FRED series release dates
    for series_id, (name, importance) in TRACKED_SERIES.items():
        release_dates = _fetch_release_dates(series_id, api_key, start, end)
        for rd in release_dates:
            if not rd:
                logger.warning(f"FRED {series_id}: Skipping record with None/empty date (prevents dedup collision)")
                continue
            records.append({
                "event_id":    f"FRED_{series_id}_{rd.isoformat()}",
                "event_date":  rd,
                "event_name":  name,
                "category":    "Economic",
                "importance":  importance,
                "country":     "US",
                "event_time":  None,
                "forecast_value":  None,
                "actual_value":    None,
                "previous_value":  None,
            })

    # Add FOMC dates (both years so 90-day window works in late 2026)
    for fomc_date_str, fomc_name in FOMC_DATES_2026 + FOMC_DATES_2027:
        fomc_date = date.fromisoformat(fomc_date_str)
        if start <= fomc_date <= end:
            records.append({
                "event_id":    f"FOMC_{fomc_date_str}",
                "event_date":  fomc_date,
                "event_name":  fomc_name,
                "category":    "FOMC",
                "importance":  "HIGH",
                "country":     "US",
                "event_time":  None,
                "forecast_value":  None,
                "actual_value":    None,
                "previous_value":  None,
            })

    if not records:
        logger.warning("No economic calendar events fetched")
        return 0

    with DatabaseContext('write') as cur:
        cur.executemany("""
            INSERT INTO economic_calendar
                (event_id, event_date, event_name, category, importance, country,
                 event_time, forecast_value, actual_value, previous_value)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_id, event_date) DO UPDATE SET
                event_name      = EXCLUDED.event_name,
                importance      = EXCLUDED.importance,
                category        = EXCLUDED.category,
                forecast_value  = EXCLUDED.forecast_value,
                actual_value    = EXCLUDED.actual_value,
                previous_value  = EXCLUDED.previous_value,
                updated_at      = NOW()
        """, [
            (r["event_id"], r["event_date"], r["event_name"], r["category"],
             r["importance"], r["country"], r["event_time"],
             r["forecast_value"], r["actual_value"], r["previous_value"])
            for r in records
        ])
        count = len(records)
        logger.info(f"Upserted {count} economic calendar events through {end}")

        try:
            cur.execute("""
                INSERT INTO data_loader_status (table_name, row_count, latest_date, last_updated)
                VALUES ('economic_calendar', %s, %s, NOW())
                ON CONFLICT (table_name) DO UPDATE SET
                    row_count = EXCLUDED.row_count,
                    latest_date = EXCLUDED.latest_date,
                    last_updated = EXCLUDED.last_updated
            """, (count, end))
        except Exception as e:
            logger.warning(f"Failed to update data_loader_status: {e}")

    return count

def main():
    try:
        # Execution timeout: ~20 series, 1-2 requests each, ~1-2s per = 1-2 min normally
        # Set limit to 10 min (600s) to catch hanging requests early
        with ExecutionTimeout(max_seconds=600, label="load_economic_calendar"):
            today = date.today()
            count = _load_economic_calendar(today)
            if count > 0:
                logger.info(f"SUCCESS: {count} economic calendar events loaded")
                return 0
            else:
                logger.warning("COMPLETED: No economic calendar events loaded")
                return 0
    except Exception as e:
        logger.error(f"Economic calendar load failed: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(main())
