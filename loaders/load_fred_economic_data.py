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
import boto3

from utils.optimal_loader import OptimalLoader
from utils.loader_helpers import get_api_key
from config.api_endpoints import get_fred_url

logger = logging.getLogger(__name__)

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
    """Get FRED API key from Secrets Manager, fall back to env var."""
    return get_api_key('algo/fred', 'FRED_API_KEY') or ""

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
        failed_series = []

        for i, series_id in enumerate(SERIES):
            # Very conservative delay between requests: FRED API has strict per-key rate limiting
            # After hitting 429, key is blocked for extended period - require long delays between ALL requests
            # 5s per request = 12 req/min, well under FRED's typical ~120 req/min per key
            if i > 0:
                time.sleep(5.0)

            logger.info(f"Fetching {series_id} from FRED ({start_date} to {end_date})...")

            # Extreme exponential backoff for rate limiting: up to 5 retries with very long waits
            # FRED blocks key for minutes after hitting rate limit - need long resets
            max_retries = 5
            base_delay = 10.0  # Start with 10s, double on each retry (10s, 20s, 40s, 80s, 160s)

            success = False
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
                    fred_url = f"{get_fred_url()}/series/observations"
                    resp = requests.get(fred_url, params=params, timeout=30)
                    resp.raise_for_status()
                    observations = resp.json().get("observations", [])

                    for obs in observations:
                        val_str = obs.get("value", ".")
                        if val_str == ".":
                            logger.debug(
                                f"{series_id} [{obs.get('date')}]: Observation skipped — missing value "
                                f"(value='.')"
                            )
                            continue
                        try:
                            all_rows.append({
                                'series_id': series_id,
                                'date': obs["date"],
                                'value': float(val_str)
                            })
                        except (ValueError, KeyError) as e:
                            logger.debug(
                                f"{series_id} [{obs.get('date')}]: Observation skipped — parsing error "
                                f"(value={val_str}, error={e})"
                            )
                            continue

                    logger.info(f"  {series_id}: SUCCESS ({len([r for r in all_rows if r['series_id'] == series_id])} rows)")
                    success = True
                    break  # Success, exit retry loop

                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 429:  # Rate limit
                        if attempt < max_retries - 1:
                            delay = base_delay * (2 ** attempt)
                            logger.warning(f"  {series_id}: 429 rate limit (attempt {attempt + 1}/{max_retries}), waiting {delay}s...")
                            time.sleep(delay)
                        else:
                            logger.error(f"  {series_id}: FAILED after {max_retries} retries with 429 errors")
                            failed_series.append(series_id)
                    else:
                        logger.error(f"  {series_id}: HTTP {e.response.status_code} — {e}")
                        failed_series.append(series_id)
                        break  # Don't retry on non-rate-limit errors
                except Exception as e:
                    logger.error(f"  {series_id}: ERROR — {e}")
                    failed_series.append(series_id)
                    break  # Don't retry on other exceptions

        if failed_series:
            logger.warning(f"Failed to fetch {len(failed_series)} series: {', '.join(failed_series)}")

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
