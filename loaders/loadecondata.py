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

Economic Dashboard series (economic.js /api/economic/leading-indicators):
  All series below power the EconomicDashboard page tabs (Overview, Business
  Cycle, Rates & Fed, Labor, Inflation, Growth, Housing). economic.js hard-
  fails with 500 if the 15 required series are missing, so the full list must
  be loaded on every daily run.

Run:
    python3 loadecondata.py [--parallelism 8]
"""

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

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
#
# Group 1: Critical for algo_market_exposure.py circuit breakers
FRED_SERIES_ALGO = [
    "BAMLH0A0HYM2",   # HY OAS — credit spread circuit breaker
    "BAMLC0A0CM",     # IG OAS — investment-grade complement
    "T10Y2Y",         # 10Y-2Y yield spread — recession signal
    "FEDFUNDS",       # Fed funds effective rate
    "UNRATE",         # Unemployment rate
    "USREC",          # US recession indicator (0/1)
    "DCOILWTICO",     # WTI crude oil price
]

# Group 2: Required by economic.js /api/economic/leading-indicators
# economic.js fails hard (HTTP 500) when any of these 15 are missing:
# UNRATE, PAYEMS, CPIAUCSL, GDPC1, DGS10, DGS2, T10Y2Y, SP500, VIXCLS,
# FEDFUNDS, INDPRO, HOUST, MICH, ICSA, BUSLOANS
FRED_SERIES_DASHBOARD = [
    # Labor market
    "PAYEMS",         # Nonfarm Payrolls (monthly)
    "ICSA",           # Initial Jobless Claims (weekly)
    "UEMPMEAN",       # Average Duration of Unemployment (monthly)
    "EMSRATIO",       # Employment-Population Ratio (monthly)
    "CIVPART",        # Labor Force Participation Rate (monthly)
    # Prices & inflation
    "CPIAUCSL",       # Consumer Price Index (monthly)
    "CPILFESL",       # Core CPI ex Food & Energy (monthly)
    "PPIACO",         # Producer Price Index All Commodities (monthly)
    # GDP & production
    "GDPC1",          # Real GDP (quarterly)
    "INDPRO",         # Industrial Production Index (monthly)
    "CUMFSL",         # Capacity Utilization (monthly)
    # Housing
    "HOUST",          # Housing Starts (monthly)
    "PERMIT",         # New Building Permits (monthly)
    "MORTGAGE30US",   # 30-yr Fixed Rate Mortgage (weekly)
    # Sentiment
    "MICH",           # U of Michigan Consumer Sentiment (monthly)
    "UMCSENT",        # U of Michigan Consumer Sentiment preliminary (monthly)
    # Credit & lending
    "BUSLOANS",       # Commercial & Industrial Loans (monthly)
    # Equity & volatility (sourced from FRED, not price_daily)
    "SP500",          # S&P 500 Index closing level (daily)
    "VIXCLS",         # CBOE VIX (daily)
    # Rates
    "PRIME",          # Bank Prime Loan Rate (monthly)
    # Trade
    "TOTALSA",        # Total Light Vehicle Sales (monthly)
    "IMPGS",          # Imports of Goods & Services (quarterly)
    # Money supply
    "M1SL",           # M1 Money Stock seasonally adjusted (monthly)
    "M2SL",           # M2 Money Stock (monthly)
    "WALCL",          # Fed Balance Sheet Total Assets (weekly)
    # Retail
    "RSXFS",          # Advance Retail Sales ex Food Services (monthly)
]

# Group 3: Full yield curve — required for yield-curve-full endpoint
FRED_SERIES_YIELD_CURVE = [
    "DGS3MO",         # 3-Month Treasury (daily)
    "DGS6MO",         # 6-Month Treasury (daily)
    "DGS1",           # 1-Year Treasury (daily)
    "DGS2",           # 2-Year Treasury (daily)
    "DGS3",           # 3-Year Treasury (daily)
    "DGS5",           # 5-Year Treasury (daily)
    "DGS7",           # 7-Year Treasury (daily)
    "DGS10",          # 10-Year Treasury (daily)
    "DGS20",          # 20-Year Treasury (daily)
    "DGS30",          # 30-Year Treasury (daily)
]

# Combined — deduplicated (some IDs appear in multiple groups)
_seen: set = set()
FRED_SERIES = []
for _s in FRED_SERIES_ALGO + FRED_SERIES_DASHBOARD + FRED_SERIES_YIELD_CURVE:
    if _s not in _seen:
        FRED_SERIES.append(_s)
        _seen.add(_s)

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
        # Get FRED API key from credential manager (tries AWS Secrets Manager first, then env vars)
        if credential_manager:
            try:
                self._api_key = credential_manager.get_secret("FRED_API_KEY", default="")
            except Exception as e:
                logging.warning(f"Credential manager failed: {e}, falling back to environment")
                self._api_key = os.getenv("FRED_API_KEY", "")
        else:
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

    # Get FRED API key from credential manager or environment
    api_key = None
    if credential_manager:
        try:
            api_key = credential_manager.get_secret("FRED_API_KEY", default=None)
        except Exception:
            api_key = os.getenv("FRED_API_KEY")
    else:
        api_key = os.getenv("FRED_API_KEY")

    if not api_key:
        logging.error("FRED_API_KEY not found in AWS Secrets Manager or environment variables. "
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

