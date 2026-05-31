#!/usr/bin/env python3
"""Economic Calendar Loader — Upcoming macro release dates from FRED."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import os
import json
from datetime import date, timedelta
from typing import Optional, List
import requests

from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred"

# FRED series IDs → display names and importance
TRACKED_SERIES = {
    "CPIAUCSL": ("CPI - Inflation",            "HIGH"),
    "PCEPI":    ("PCE Price Index",             "HIGH"),
    "PAYEMS":   ("Non-Farm Payrolls (NFP)",     "HIGH"),
    "UNRATE":   ("Unemployment Rate",           "HIGH"),
    "GDPC1":    ("GDP (Real)",                  "HIGH"),
    "FEDFUNDS": ("Federal Funds Rate",          "HIGH"),
    "ICSA":     ("Initial Jobless Claims",      "MEDIUM"),
    "INDPRO":   ("Industrial Production",       "MEDIUM"),
    "RSXFS":    ("Retail Sales",                "MEDIUM"),
    "HOUST":    ("Housing Starts",              "MEDIUM"),
    "UMCSENT":  ("Consumer Sentiment (UMich)",  "MEDIUM"),
    "T10Y2Y":   ("Yield Curve (10Y-2Y)",        "LOW"),
    "BAMLH0A0HYM2": ("HY Credit Spread",        "LOW"),
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
    key = os.getenv("FRED_API_KEY", "")
    if key:
        return key
    try:
        from config.credential_manager import get_secret
        return get_secret("fred/api_key", default="")
    except Exception:
        pass
    try:
        import boto3
        client = boto3.client("secretsmanager", region_name="us-east-1")
        resp = client.get_secret_value(SecretId="algo/fred")
        data = json.loads(resp.get("SecretString", "{}"))
        return data.get("api_key") or data.get("FRED_API_KEY", "")
    except Exception:
        pass
    return ""


def _fetch_release_dates(series_id: str, api_key: str, start: date, end: date) -> List[date]:
    """Fetch upcoming release dates for a FRED series via the releases endpoint."""
    try:
        # Get the release ID for this series
        r = requests.get(
            f"{FRED_BASE}/series/release",
            params={"series_id": series_id, "api_key": api_key, "file_type": "json"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        releases = data.get("releases", [])
        if not releases:
            return []
        release_id = releases[0]["id"]

        # Get upcoming release dates for this release
        r2 = requests.get(
            f"{FRED_BASE}/release/dates",
            params={
                "release_id": release_id,
                "api_key": api_key,
                "file_type": "json",
                "realtime_start": str(start),
                "realtime_end": str(end),
                "sort_order": "asc",
                "limit": 12,
            },
            timeout=10,
        )
        r2.raise_for_status()
        dates_data = r2.json()
        return [
            date.fromisoformat(d["date"])
            for d in dates_data.get("release_dates", [])
            if d.get("date")
        ]
    except Exception as e:
        logger.debug(f"FRED release dates fetch failed for {series_id}: {e}")
        return []


def _load_economic_calendar(today: date) -> int:
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
    today = date.today()
    try:
        count = _load_economic_calendar(today)
        if count > 0:
            logger.info(f"SUCCESS: {count} economic calendar events loaded")
            return 0
        else:
            logger.warning("COMPLETED: No economic calendar events loaded")
            return 0
    except Exception as e:
        logger.error(f"Economic calendar load failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
