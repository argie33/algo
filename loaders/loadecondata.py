#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Economic Data Loader — FRED time series.

Fetches all series needed by the economic dashboard from the FRED REST API
and stores them in the economic_data table.

Run:
    python3 loadecondata.py [--backfill-days 730]
"""

import logging
import os
import time
from datetime import date, timedelta
from typing import List, Optional

import requests

from config.env_loader import load_env
from utils.optimal_loader import OptimalLoader

log = logging.getLogger(__name__)

# All FRED series consumed by the API (indicators + yield curve + spreads)
FRED_SERIES = [
    # Leading indicators
    "UNRATE", "PAYEMS", "ICSA", "CIVPART", "INDPRO", "RSXFS",
    "CPIAUCSL", "FEDFUNDS", "M2SL", "T10Y2Y", "GDPC1", "UMCSENT", "HOUST",
    # Yield curve
    "DGS3MO", "DGS6MO", "DGS1", "DGS2", "DGS3", "DGS5", "DGS7",
    "DGS10", "DGS20", "DGS30", "T10Y3M",
    # Credit spreads
    "BAMLH0A0HYM2", "BAMLC0A0CM",
]

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


class EconDataLoader(OptimalLoader):
    table_name = "economic_data"
    primary_key = ("series_id", "date")
    watermark_field = "date"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._api_key = os.getenv("FRED_API_KEY", "")
        if not self._api_key:
            log.warning("FRED_API_KEY not set — economic data load will fail")

    def fetch_incremental(self, symbol: str, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch FRED observations for one series_id."""
        series_id = symbol
        start = since or date(2015, 1, 1)

        params = {
            "series_id": series_id,
            "api_key": self._api_key,
            "file_type": "json",
            "observation_start": str(start),
            "observation_end": str(date.today()),
            "sort_order": "asc",
        }
        try:
            resp = requests.get(FRED_BASE, params=params, timeout=30)
            if resp.status_code == 429:
                log.warning("FRED rate limit — sleeping 30s")
                time.sleep(30)
                resp = requests.get(FRED_BASE, params=params, timeout=30)
            resp.raise_for_status()
            observations = resp.json().get("observations", [])
        except Exception as e:
            log.error("FRED fetch failed for %s: %s", series_id, e)
            return None

        rows = []
        for obs in observations:
            val_str = obs.get("value", ".")
            if val_str == "." or val_str is None:
                continue
            try:
                rows.append({
                    "series_id": series_id,
                    "date": obs["date"],
                    "value": float(val_str),
                })
            except (ValueError, KeyError):
                continue

        log.debug("FRED %s: %d observations from %s", series_id, len(rows), start)
        return rows or None


def main() -> int:
    import argparse
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="FRED economic data loader")
    parser.add_argument("--symbols", type=str, help="Comma-separated series (default: all)")
    parser.add_argument("--backfill-days", type=int, default=0)
    parser.add_argument("--parallelism", type=int, default=4)
    args = parser.parse_args()

    series = args.symbols.split(",") if args.symbols else FRED_SERIES
    loader = EconDataLoader(backfill_days=args.backfill_days)
    try:
        stats = loader.run(series, parallelism=args.parallelism)
    finally:
        loader.close()

    log.info("Economic data load complete: %s", stats)
    fail_rate = stats.get("symbols_failed", 0) / max(len(symbols), 1)
        if fail_rate > 0.05:
            logger.error(f"Too many failures: {stats['symbols_failed']}/{len(symbols)} ({fail_rate*100:.1f}%)")
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
