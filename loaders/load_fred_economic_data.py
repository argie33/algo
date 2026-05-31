#!/usr/bin/env python3
"""FRED Economic Data Loader — Market-wide macroeconomic indicators."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import os
from datetime import date, timedelta
from typing import List, Optional, Dict, Any
import requests

from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

SERIES = [
    # Treasury yield curve (needed by YieldCurveCard + _get_yield_curve_full)
    "DGS3MO",     # 3-Month Treasury
    "DGS6MO",     # 6-Month Treasury
    "DGS1",       # 1-Year Treasury
    "DGS2",       # 2-Year Treasury
    "DGS3",       # 3-Year Treasury
    "DGS5",       # 5-Year Treasury
    "DGS7",       # 7-Year Treasury
    "DGS10",      # 10-Year Treasury
    "DGS20",      # 20-Year Treasury
    "DGS30",      # 30-Year Treasury
    # Yield spreads (inversion signals)
    "T10Y2Y",     # 10Y-2Y spread (orchestrator + yield curve card)
    "T10Y3M",     # 10Y-3M spread (yield curve card)
    # Credit spreads (orchestrator market exposure + yield curve card)
    "BAMLH0A0HYM2",  # HY corporate OAS
    "BAMLC0A0CM",    # IG corporate OAS
    # Volatility proxy
    "VIXCLS",        # CBOE VIX (FRED daily)
    # Labor market (leading indicators + orchestrator jobless-claims factor)
    "UNRATE",        # Unemployment Rate
    "PAYEMS",        # Nonfarm Payroll (level; displayed as YoY %)
    "ICSA",          # Initial Jobless Claims (weekly)
    "CIVPART",       # Labor Force Participation Rate
    # Activity / production
    "INDPRO",        # Industrial Production (level; displayed as YoY %)
    "RSXFS",         # Retail Sales ex-Food Services (level; displayed as YoY %)
    # Inflation
    "CPIAUCSL",      # CPI All Urban (level; displayed as YoY %)
    # Monetary / rates
    "FEDFUNDS",      # Federal Funds Effective Rate
    "M2SL",          # M2 Money Supply (level; displayed as YoY %)
    # GDP & growth
    "GDPC1",         # Real GDP (quarterly; displayed as YoY %)
    # Consumer confidence
    "UMCSENT",       # University of Michigan Consumer Sentiment
    # Housing
    "HOUST",         # Housing Starts (level; displayed as YoY %)
    "MORTGAGE30US",  # 30-Year Fixed Rate Mortgage Average
    # Lending / credit
    "BUSLOANS",      # Commercial & Industrial Loans (Business Loans)
]


def get_fred_api_key() -> str:
    """Get FRED API key from environment or credential_manager."""
    key = os.getenv("FRED_API_KEY", "")
    if key:
        return key

    try:
        from config.credential_manager import get_secret
        return get_secret("fred/api_key", default="")
    except Exception as e:
        logger.debug(f"credential_manager lookup failed: {e}")

    try:
        import boto3, json
        client = boto3.client("secretsmanager", region_name="us-east-1")
        resp = client.get_secret_value(SecretId="algo/fred")
        data = json.loads(resp.get("SecretString", "{}"))
        return data.get("api_key") or data.get("FRED_API_KEY", "")
    except Exception as e:
        logger.debug(f"Secrets Manager lookup failed: {e}")

    return ""


class FredEconomicDataLoader(OptimalLoader):
    """Load FRED economic time-series data (market-wide)."""

    table_name = "economic_data"
    primary_key = ("series_id", "date")
    watermark_field = "date"

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Fetch FRED economic data for all configured series."""
        api_key = get_fred_api_key()
        if not api_key:
            logger.error("FRED_API_KEY not found")
            raise ValueError("FRED_API_KEY not found")

        end_date = date.today().isoformat()
        # 3 years covers quarterly series (GDP, HOUST) plus gives YoY% enough lookback
        start_date = (date.today() - timedelta(days=1095)).isoformat()

        all_rows = []

        for series_id in SERIES:
            logger.info(f"Fetching {series_id} from FRED ({start_date} to {end_date})...")
            try:
                params = {
                    "series_id": series_id,
                    "api_key": api_key,
                    "file_type": "json",
                    "observation_start": start_date,
                    "observation_end": end_date,
                    "sort_order": "asc",
                }
                resp = requests.get(FRED_BASE, params=params, timeout=30)
                resp.raise_for_status()
                observations = resp.json().get("observations", [])

                for obs in observations:
                    val_str = obs.get("value", ".")
                    if val_str == ".":
                        continue
                    try:
                        all_rows.append({
                            'series_id': series_id,
                            'date': obs["date"],
                            'value': float(val_str)
                        })
                    except (ValueError, KeyError):
                        continue

                logger.info(f"  {series_id}: {len([r for r in all_rows if r['series_id'] == series_id])} rows")

            except Exception as e:
                logger.error(f"  {series_id}: FAILED — {e}")
                continue

        return all_rows if all_rows else None


def main():
    loader = FredEconomicDataLoader()
    result = loader.load_global()

    if result > 0:
        logger.info(f"SUCCESS: {result} economic data records loaded")
        return 0
    else:
        logger.warning(f"COMPLETED: No records loaded")
        return 0


if __name__ == "__main__":
    sys.exit(main())
