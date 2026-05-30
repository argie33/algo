#!/usr/bin/env python3
"""FRED Economic Data Loader — Loads key macro time-series from FRED API.

Series loaded:
  T10Y2Y       — 10Y minus 2Y Treasury spread (yield curve), daily
  BAMLH0A0HYM2 — ICE BofA US HY OAS credit spread, daily
  ICSA         — Initial jobless claims, weekly
  FEDFUNDS     — Effective federal funds rate, monthly
  UNRATE       — Unemployment rate, monthly

Requires FRED_API_KEY in environment or Secrets Manager (algo/fred).

Run: python3 loaders/load_fred_economic_data.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import os
from datetime import date, timedelta
from typing import List, Tuple, Optional

import requests
import psycopg2
from psycopg2.extras import execute_values

from utils.database_context import DatabaseContext


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

SERIES = [
    "T10Y2Y",
    "BAMLH0A0HYM2",
    "ICSA",
    "FEDFUNDS",
    "UNRATE",
]


def get_fred_api_key() -> str:
    """Get FRED API key from environment, credential_manager, or Secrets Manager.

    Priority:
    1. FRED_API_KEY env var (local dev, or passed by Lambda)
    2. credential_manager (unified handler - tries Secrets Manager then env vars)
    3. Direct Secrets Manager lookup (fallback for non-Lambda contexts)
    """
    # First try environment variable
    key = os.getenv("FRED_API_KEY", "")
    if key:
        return key

    # Try credential_manager if available (works in Lambda with proper IAM)
    try:
        from config.credential_manager import get_secret
        return get_secret("fred/api_key", default="")
    except Exception as e:
        log.debug(f"credential_manager lookup failed: {e}")

    # Fallback: Try direct Secrets Manager (for ECS tasks, local development with boto3)
    try:
        import boto3, json
        client = boto3.client("secretsmanager", region_name="us-east-1")
        resp = client.get_secret_value(SecretId="algo/fred")
        data = json.loads(resp.get("SecretString", "{}"))
        return data.get("api_key") or data.get("FRED_API_KEY", "")
    except Exception as e:
        log.debug(f"Secrets Manager lookup failed: {e}")

    return ""


def fetch_series(series_id: str, api_key: str, start: str, end: str) -> List[Tuple]:
    """Fetch observations for a FRED series. Returns list of (series_id, date, value)."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
        "observation_end": end,
        "sort_order": "asc",
    }
    resp = requests.get(FRED_BASE, params=params, timeout=30)
    resp.raise_for_status()
    observations = resp.json().get("observations", [])
    rows = []
    for obs in observations:
        val_str = obs.get("value", ".")
        if val_str == ".":
            continue
        try:
            rows.append((series_id, obs["date"], float(val_str)))
        except (ValueError, KeyError):
            continue
    return rows


def upsert_rows(cur, rows: List[Tuple]) -> int:
    if not rows:
        return 0
    execute_values(
        cur,
        """
        INSERT INTO economic_data (series_id, date, value)
        VALUES %s
        ON CONFLICT (series_id, date) DO UPDATE SET value = EXCLUDED.value
        """,
        rows,
    )
    return len(rows)


def main():
    api_key = get_fred_api_key()
    if not api_key:
        log.error("FRED_API_KEY not found in environment or Secrets Manager")
        sys.exit(1)

    end_date = date.today().isoformat()
    # Load 2 years of history on first run; subsequent runs just update recent data
    start_date = (date.today() - timedelta(days=730)).isoformat()

    with DatabaseContext('write') as cur:
        total = 0
        for series_id in SERIES:
            log.info(f"Fetching {series_id} from FRED ({start_date} to {end_date})...")
            try:
                rows = fetch_series(series_id, api_key, start_date, end_date)
                n = upsert_rows(cur, rows)
                cur.connection.commit()
                log.info(f"  {series_id}: {n} rows upserted")
                total += n
            except Exception as e:
                cur.connection.rollback()
                log.error(f"  {series_id}: FAILED — {e}")

    log.info(f"Done. Total rows upserted: {total}")


if __name__ == "__main__":
    main()
