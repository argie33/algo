#!/usr/bin/env python3
# fan-out trigger 2026-05-05 — verify ECS task def + LOADER_FILE wiring
"""
Economic Data Loader — fetches FRED series via direct HTTP.

Loads macroeconomic time series into the economic_data table.
No fredapi package required — uses direct FRED REST API calls.
FRED_API_KEY env var is required (free at fred.stlouisfed.org).

Critical series for algo_market_exposure.py:
  BAMLH0A0HYM2  — HY OAS credit spread (credit spread circuit breaker)
  BAMLC0A0CM    — IG OAS (investment-grade complement)
  T10Y2Y        — 10Y-2Y yield spread (recession signal)
  FEDFUNDS      — Fed funds effective rate
  UNRATE        — Unemployment rate

Run:
    python3 loadecondata.py [--parallelism 4]
"""

from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import argparse
import logging
import os
import sys
import time
from datetime import date, timedelta
from typing import List, Optional

from optimal_loader import OptimalLoader

from pathlib import Path as _DotenvPath
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _DotenvPath(__file__).resolve().parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# FRED series to load — series_id is used as the "symbol" in OptimalLoader
FRED_SERIES = [
    "BAMLH0A0HYM2",   # HY OAS — critical for credit spread factor
    "BAMLC0A0CM",     # IG OAS
    "T10Y2Y",         # 10Y-2Y yield spread
    "FEDFUNDS",       # Fed funds rate
    "UNRATE",         # Unemployment rate
    "USREC",          # US recession indicator (0/1)
    "DCOILWTICO",     # WTI crude oil price
]

FRED_API_BASE = "https://api.stlouisfed.org/fred/series/observations"


def _fetch_fred_series(series_id: str, since: Optional[date], api_key: str) -> Optional[List[dict]]:
    """Fetch observations for one FRED series. Returns list of {series_id, date, value} dicts."""
    import urllib.request
    import urllib.parse
    import json

    observation_start = (since - timedelta(days=5)).isoformat() if since else "2000-01-01"
    params = urllib.parse.urlencode({
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": observation_start,
        "sort_order": "asc",
        "limit": 10000,
    })
    url = f"{FRED_API_BASE}?{params}"

    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            observations = data.get("observations", [])
            rows = []
            for obs in observations:
                val_str = obs.get("value", ".")
                if val_str == ".":
                    continue
                try:
                    rows.append({
                        "series_id": series_id,
                        "date": obs["date"],
                        "value": float(val_str),
                    })
                except (ValueError, KeyError):
                    continue
            return rows if rows else None
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            logging.warning("FRED fetch failed for %s after 3 attempts: %s", series_id, e)
            return None
    return None


class EconDataLoader(OptimalLoader):
    table_name = "economic_data"
    primary_key = ("series_id", "date")
    watermark_field = "date"

    def __init__(self):
        super().__init__()
        self._api_key = os.getenv("FRED_API_KEY", "")

    def fetch_incremental(self, symbol: str, since: Optional[date]):
        if not self._api_key:
            logging.warning("FRED_API_KEY not set — skipping economic data load")
            return None
        return _fetch_fred_series(symbol, since, self._api_key)

    def transform(self, rows):
        return rows

    def _validate_row(self, row: dict) -> bool:
        if not row.get("series_id") or not row.get("date"):
            return False
        try:
            float(row["value"])
        except (TypeError, ValueError):
            return False
        return True


def main():
    parser = argparse.ArgumentParser(description="Economic data loader (FRED)")
    parser.add_argument("--series", help="Comma-separated FRED series IDs. Default: all configured.")
    parser.add_argument("--parallelism", type=int, default=4)
    args = parser.parse_args()

    if not os.getenv("FRED_API_KEY"):
        logging.error("FRED_API_KEY environment variable not set. "
                      "Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html")
        return 1

    series = [s.strip().upper() for s in args.series.split(",")] if args.series else FRED_SERIES

    loader = EconDataLoader()
    try:
        stats = loader.run(series, parallelism=args.parallelism)
    finally:
        loader.close()

    logging.info("Econ data load complete: %s", stats)
    return 0 if stats["symbols_failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
