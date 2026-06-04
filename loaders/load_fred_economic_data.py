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
import time

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
    # Core PCE (Fed's actual 2% inflation target — preferred over CPI)
    "PCEPILFE",   # Core PCE: Personal Consumption Expenditures ex-Food & Energy (monthly)
    # Inflation expectations — market-implied TIPS breakevens
    "T5YIE",      # 5-Year Breakeven Inflation Rate (daily)
    "T10YIE",     # 10-Year Breakeven Inflation Rate (daily)
    # Dollar strength
    "DTWEXBGS",   # USD Broad Nominal Index, trade-weighted (daily)
    # Commodities
    "DCOILWTICO", # WTI Crude Oil, Cushing OK ($/barrel, daily)
    # Financial stress (broader than credit spreads alone)
    "STLFSI4",    # St. Louis Fed Financial Stress Index (weekly; 0=normal, positive=stress)
    "ANFCI",      # Chicago Fed Adjusted National Financial Conditions Index (weekly)
    # Labor market — advanced indicators
    "JTSJOL",     # JOLTS Job Openings (thousands, monthly)
    "JTSQUR",     # JOLTS Quit Rate (% monthly — signals worker confidence)
    "AHETPI",     # Average Hourly Earnings, Total Private (level; displayed as YoY %)
    # Industrial capacity
    "TCU",        # Capacity Utilization: Manufacturing, Mining, Utilities (%)
    "MFGBDPHI",  # Philadelphia Fed Manufacturing Index (diffusion; >0=expansion)
    "CFNAI",      # Chicago Fed National Activity Index (85-indicator composite)
    # Housing — leading indicator
    "PERMIT",     # Building Permits, Total (thousands, SAAR, monthly)
    # Consumer health
    "PSAVERT",    # Personal Savings Rate (%)
    "DSPIC96",    # Real Disposable Personal Income (level; displayed as YoY %)
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

        for i, series_id in enumerate(SERIES):
            # Add delay between requests to avoid rate limiting (FRED allows ~10 requests/sec)
            if i > 0:
                time.sleep(0.15)

            logger.info(f"Fetching {series_id} from FRED ({start_date} to {end_date})...")

            # Exponential backoff for rate limiting: up to 3 retries
            max_retries = 3
            base_delay = 0.5

            for attempt in range(max_retries):
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
                    break  # Success, exit retry loop

                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 429:  # Rate limit
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)
                            logger.warning(f"  {series_id}: Rate limited (429), retrying in {delay}s (attempt {attempt + 1}/{max_retries})...")
                            time.sleep(delay)
                        else:
                            logger.error(f"  {series_id}: FAILED after {max_retries} retries — {e}")
                    else:
                        logger.error(f"  {series_id}: FAILED — {e}")
                        break  # Don't retry on non-rate-limit errors
                except Exception as e:
                    logger.error(f"  {series_id}: FAILED — {e}")
                    break  # Don't retry on other exceptions

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
