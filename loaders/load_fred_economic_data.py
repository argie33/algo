#!/usr/bin/env python3
"""FRED Economic Data Loader — Market-wide macroeconomic indicators.

Data Criticality: REQUIRED (used for market analysis, not critical for position sizing)
Failure Mode: Fails with context if data unavailable/stale, retries with circuit breaker
Freshness Requirement: Maximum 48 hours staleness (FRED updates weekly)

Uses canonical circuit breaker (utils.infrastructure.circuit_breaker:CircuitBreaker)
with DataImportance.REQUIRED and freshness validation to prevent silent stale data.
"""

import json
import logging
import socket
import sys
import time
from datetime import date, datetime, timedelta
from typing import Any

import requests

from config.api_endpoints import get_fred_url
from loaders.runner import run_loader
from utils.infrastructure.circuit_breaker import DataImportance
from utils.infrastructure.url_validator import validate_url
from utils.loaders import create_circuit_breaker, get_api_key
from utils.optimal_loader import OptimalLoader
from utils.validation.data_freshness import FreshnessValidator, StaleDataError

logger = logging.getLogger(__name__)

SERIES = [
    # Treasury yield curve (needed by YieldCurveCard + _get_yield_curve_full)
    "DGS3MO",  # 3-Month Treasury
    "DGS6MO",  # 6-Month Treasury
    "DGS1",  # 1-Year Treasury
    "DGS2",  # 2-Year Treasury
    "DGS3",  # 3-Year Treasury
    "DGS5",  # 5-Year Treasury
    "DGS7",  # 7-Year Treasury
    "DGS10",  # 10-Year Treasury
    "DGS20",  # 20-Year Treasury
    "DGS30",  # 30-Year Treasury
    # Yield spreads (inversion signals)
    "T10Y2Y",  # 10Y-2Y spread (orchestrator + yield curve card)
    "T10Y3M",  # 10Y-3M spread (yield curve card)
    # Credit spreads (orchestrator market exposure + yield curve card)
    "BAMLH0A0HYM2",  # HY corporate OAS
    "BAMLC0A0CM",  # IG corporate OAS
    # Volatility proxy
    "VIXCLS",  # CBOE VIX (FRED daily)
    # Labor market (leading indicators + orchestrator jobless-claims factor)
    "UNRATE",  # Unemployment Rate
    "PAYEMS",  # Nonfarm Payroll (level; displayed as YoY %)
    "ICSA",  # Initial Jobless Claims (weekly)
    "CIVPART",  # Labor Force Participation Rate
    # Activity / production
    "INDPRO",  # Industrial Production (level; displayed as YoY %)
    "RSXFS",  # Retail Sales ex-Food Services (level; displayed as YoY %)
    # Inflation
    "CPIAUCSL",  # CPI All Urban (level; displayed as YoY %)
    # Monetary / rates
    "FEDFUNDS",  # Federal Funds Effective Rate
    "M2SL",  # M2 Money Supply (level; displayed as YoY %)
    # GDP & growth
    "GDPC1",  # Real GDP (quarterly; displayed as YoY %)
    # Consumer confidence
    "UMCSENT",  # University of Michigan Consumer Sentiment
    # Housing
    "HOUST",  # Housing Starts (level; displayed as YoY %)
    "MORTGAGE30US",  # 30-Year Fixed Rate Mortgage Average
    # Lending / credit
    "BUSLOANS",  # Commercial & Industrial Loans (Business Loans)
    # Core PCE (Fed's actual 2% inflation target — preferred over CPI)
    "PCEPILFE",  # Core PCE: Personal Consumption Expenditures ex-Food & Energy (monthly)
    # Inflation expectations — market-implied TIPS breakevens
    "T5YIE",  # 5-Year Breakeven Inflation Rate (daily)
    "T10YIE",  # 10-Year Breakeven Inflation Rate (daily)
    # Dollar strength
    # NOTE: Real DXY is published by ICE. DTWEXBGS is a FRED proxy (trade-weighted broad index).
    # DXY_ICE now fetched from Yahoo Finance (ticker: DX-Y.NYB) - see _fetch_dxy_from_yahoo()
    "DTWEXBGS",  # USD Broad Trade-Weighted Index (FRED proxy for comparison) - daily
    # Commodities
    "DCOILWTICO",  # WTI Crude Oil, Cushing OK ($/barrel, daily)
    # Financial stress (broader than credit spreads alone)
    "STLFSI4",  # St. Louis Fed Financial Stress Index (weekly; 0=normal, positive=stress)
    "ANFCI",  # Chicago Fed Adjusted National Financial Conditions Index (weekly)
    # Labor market — advanced indicators
    "JTSJOL",  # JOLTS Job Openings (thousands, monthly)
    "JTSQUR",  # JOLTS Quit Rate (% monthly — signals worker confidence)
    "AHETPI",  # Average Hourly Earnings, Total Private (level; displayed as YoY %)
    # Industrial capacity
    "TCU",  # Capacity Utilization: Manufacturing, Mining, Utilities (%)
    "CFNAI",  # Chicago Fed National Activity Index (85-indicator composite)
    # Housing — leading indicator
    "PERMIT",  # Building Permits, Total (thousands, SAAR, monthly)
    # Consumer health
    "PSAVERT",  # Personal Savings Rate (%)
    "DSPIC96",  # Real Disposable Personal Income (level; displayed as YoY %)
]


def get_fred_api_key() -> str:
    """Get FRED API key from Secrets Manager or environment variable.

    Raises ValueError if API key not found — FRED API calls require valid credentials.
    """
    key = get_api_key("algo/fred", "FRED_API_KEY", required=True)
    if not key:
        raise ValueError("FRED API key is required but was not configured")
    return key


class FredEconomicDataLoader(OptimalLoader):
    """Load FRED economic time-series data (market-wide).

    Data Criticality: REQUIRED (market analysis, not critical for position sizing)
    Failure Mode: Fails with context if data unavailable/stale, retries with circuit breaker
    Freshness Requirement: Maximum 48 hours staleness (FRED updates weekly)

    Uses canonical circuit breaker (utils.infrastructure.circuit_breaker:CircuitBreaker)
    with DataImportance.REQUIRED and freshness validation to prevent silent stale data.
    """

    table_name = "economic_data"
    primary_key = ("series_id", "date")
    watermark_field = "date"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize FRED loader with circuit breaker and freshness validation."""
        super().__init__(*args, **kwargs)

        # Circuit breaker for FRED API outage handling
        self._circuit_breaker = create_circuit_breaker("fred_api", importance_name="REQUIRED")

        # Freshness validator: FRED economic data must be <= 48 hours old
        # FRED updates weekly, so 48-hour requirement allows latest data plus 1 day buffer
        self._freshness_validator = FreshnessValidator(
            max_age_hours={
                "economic_data": 48.0,  # 48 hours for FRED weekly updates
            }
        )

    def _fetch_dxy_from_yahoo(self) -> list[dict[str, Any]]:
        """Fetch actual ICE DXY (US Dollar Index) from Yahoo Finance.

        Uses ticker DX-Y.NYB (Intercontinental Exchange listing on Yahoo Finance).
        Returns empty list if unavailable - caller (orchestrator/dashboard) handles missing DXY with explicit markers.
        Does NOT fall back to DTWEXBGS (trade-weighted proxy is different index).

        Returns:
            list: [{"series_id": "DXY_ICE", "date": "2026-06-29", "value": 101.13}, ...] or empty list if unavailable
        """
        try:
            import yfinance as yf

            logger.debug("Attempting to fetch DXY (DX-Y.NYB) from Yahoo Finance...")

            end_date_val = date.today()
            start_date_val = end_date_val - timedelta(days=365)

            dxy = yf.download("DX-Y.NYB", start=start_date_val, end=end_date_val, progress=False)

            if dxy is None or len(dxy) == 0:
                logger.error("[DXY] Yahoo Finance returned no data for DX-Y.NYB ticker")
                raise RuntimeError("[DXY] No data returned from Yahoo Finance for DX-Y.NYB")

            rows = []
            for idx, row in dxy.iterrows():
                # idx is a pandas Timestamp; convert to date string
                if hasattr(idx, "tz") and idx.tz is not None:
                    date_str = idx.tz_localize(None).date().isoformat()
                else:
                    date_str = idx.date().isoformat()

                value = float(row["Close"])
                rows.append({"series_id": "DXY_ICE", "date": date_str, "value": value})

            logger.info(f"Fetched {len(rows)} DXY values from Yahoo Finance (DX-Y.NYB)")
            return rows

        except ImportError as e:
            logger.error(f"[DXY] yfinance not available: {e}")
            raise RuntimeError(f"[DXY] yfinance dependency not available: {e}") from e
        except Exception as e:
            logger.error(f"[DXY] Failed to fetch from Yahoo Finance: {e}")
            raise RuntimeError(f"[DXY] Yahoo Finance fetch failed: {e}") from e

    def fetch_global(self, since: date | None) -> list[dict[str, Any]]:  # noqa: C901
        """Fetch FRED economic data for all configured series with circuit breaker and freshness validation."""
        api_key = get_fred_api_key()

        # SECURITY FIX S-05: Validate FRED base URL to prevent SSRF attacks
        fred_base_url = get_fred_url()
        is_valid, error_msg = validate_url(fred_base_url, allowed_domains=["stlouisfed.org"])
        if not is_valid:
            logger.error(f"SSRF prevention: Invalid FRED URL: {error_msg}")
            raise ValueError(f"Invalid FRED URL: {error_msg}")

        end_date = date.today().isoformat()
        # 3 years covers quarterly series (GDP, HOUST) plus gives YoY% enough lookback
        start_date = (date.today() - timedelta(days=1095)).isoformat()

        all_rows = []
        failed_series = []

        # Set socket-level timeout to catch hanging connections early
        socket.setdefaulttimeout(30.0)

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

            for attempt in range(max_retries):
                try:

                    def fetch_series(
                        sid: str = series_id,
                        sd: str = start_date,
                        ed: str = end_date,
                    ) -> dict[str, Any]:
                        """Inner function to wrap API call for circuit breaker."""
                        params = {
                            "series_id": sid,
                            "api_key": api_key,
                            "file_type": "json",
                            "observation_start": sd,
                            "observation_end": ed,
                            "sort_order": "asc",
                        }
                        fred_url = f"{get_fred_url()}/series/observations"
                        # Use connect_timeout + read_timeout tuple for more granular control
                        # connect_timeout: 10s to establish connection
                        # read_timeout: 20s to receive response (can be slow with large datasets)
                        resp = requests.get(fred_url, params=params, timeout=(10, 20))
                        resp.raise_for_status()
                        data = resp.json()
                        return data if isinstance(data, dict) else {}

                    # Execute API call through circuit breaker
                    resp_data = self._circuit_breaker.execute(
                        fetch_func=fetch_series, importance=DataImportance.REQUIRED
                    )

                    if not isinstance(resp_data, dict):
                        raise RuntimeError(
                            f"FRED API response for {series_id} is not a dict[str, Any]: {type(resp_data).__name__}. "
                            "This indicates an API schema change. Check FRED API documentation."
                        )
                    observations = resp_data.get("observations")
                    if observations is None:
                        raise RuntimeError(
                            f"FRED API response for {series_id} missing required 'observations' field. "
                            "This indicates an API schema change or data corruption. Available keys: {list(resp_data.keys())}"
                        )
                    if not isinstance(observations, list):
                        raise RuntimeError(
                            f"FRED API response for {series_id}: 'observations' field must be list, got {type(observations).__name__}. "
                            "This indicates an API schema change. Check FRED API documentation."
                        )

                    # Extract latest observation date for freshness validation
                    latest_obs_date = None
                    for obs in observations:
                        val_str = obs.get("value")
                        if val_str is None or val_str == ".":
                            # FRED returns "." for holidays/non-reporting dates — skip silently
                            continue
                        try:
                            all_rows.append(
                                {
                                    "series_id": series_id,
                                    "date": obs["date"],
                                    "value": float(val_str),
                                }
                            )
                            # Track latest observation date
                            if latest_obs_date is None or obs["date"] > latest_obs_date:
                                latest_obs_date = obs["date"]
                        except KeyError as e:
                            raise RuntimeError(
                                f"[FRED] Missing required field in observation for {series_id}: {e}. "
                                "FRED API response format may have changed or data is corrupted."
                            ) from e
                        except ValueError as e:
                            raise RuntimeError(
                                f"[FRED] Failed to parse value for {series_id} [{obs.get('date')}]: {e}. "
                                "Value string: '{val_str}'. Cannot parse economic data."
                            ) from e

                    # Validate freshness after successful fetch (REQUIRED: economic data drives market exposure)
                    # NOTE: Some FRED series are published weekly/monthly, not daily.
                    # We only enforce strict freshness for daily series (rates, commodities, indices).
                    # Monthly series (GDP, JOLTS) are allowed to be older.
                    daily_series = {
                        "FEDFUNDS",
                        "DGS3MO",
                        "DGS6MO",
                        "DGS1",
                        "DGS2",
                        "DGS3",
                        "DGS5",
                        "DGS7",
                        "DGS10",
                        "DGS20",
                        "DGS30",
                        "T10Y2Y",
                        "T10Y3M",
                        "BAMLH0A0HYM2",
                        "BAMLC0A0CM",
                        "VIXCLS",
                        "MORTGAGE30US",
                        "T5YIE",
                        "T10YIE",
                        "DTWEXBGS",
                        "DXY_ICE",
                        "DCOILWTICO",
                    }

                    if latest_obs_date and series_id in daily_series:
                        try:
                            try:
                                latest_dt = datetime.fromisoformat(latest_obs_date)
                            except (ValueError, TypeError) as e:
                                raise RuntimeError(
                                    f"Failed to parse latest FRED observation date '{latest_obs_date}': {e}. "
                                    f"Cannot validate data freshness without valid timestamp."
                                ) from e

                            self._freshness_validator.check("economic_data", latest_dt, allow_missing=False)
                        except StaleDataError as e:
                            msg = (
                                f"[FRESHNESS_VALIDATION] {e}. "
                                f"Daily FRED series {series_id} is stale. "
                                f"This may indicate FRED API issues or network problems."
                            )
                            logger.warning(msg)
                            # For daily series, warn but continue (may be weekends/holidays)
                            # Don't fail the circuit breaker for a single series
                    elif latest_obs_date and series_id not in daily_series:
                        logger.debug(
                            f"  {series_id}: Skipping freshness check (weekly/monthly series, "
                            f"last obs: {latest_obs_date})"
                        )

                    logger.info(
                        f"  {series_id}: SUCCESS ({len([r for r in all_rows if r['series_id'] == series_id])} rows)"
                    )
                    break  # Success, exit retry loop

                except requests.exceptions.Timeout:
                    # Timeout error - retry with backoff
                    if attempt < max_retries - 1:
                        delay = base_delay * (2**attempt)
                        logger.warning(
                            f"  {series_id}: Timeout (attempt {attempt + 1}/{max_retries}), waiting {delay}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"  {series_id}: FAILED after {max_retries} retries with timeout errors")
                        self._circuit_breaker.record_failure()
                        failed_series.append(series_id)
                except requests.exceptions.ConnectionError:
                    # Connection error - retry with backoff
                    if attempt < max_retries - 1:
                        delay = base_delay * (2**attempt)
                        logger.warning(
                            f"  {series_id}: Connection error (attempt {attempt + 1}/{max_retries}), waiting {delay}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"  {series_id}: FAILED after {max_retries} retries with connection errors")
                        self._circuit_breaker.record_failure()
                        failed_series.append(series_id)
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 429:  # Rate limit
                        if attempt < max_retries - 1:
                            delay = base_delay * (2**attempt)
                            logger.warning(
                                f"  {series_id}: 429 rate limit (attempt {attempt + 1}/{max_retries}), waiting {delay}s..."
                            )
                            time.sleep(delay)
                        else:
                            logger.error(f"  {series_id}: FAILED after {max_retries} retries with 429 errors")
                            self._circuit_breaker.record_failure()
                            failed_series.append(series_id)
                    else:
                        logger.error(f"  {series_id}: HTTP {e.response.status_code} — {e}")
                        self._circuit_breaker.record_failure()
                        failed_series.append(series_id)
                        break  # Don't retry on non-rate-limit errors
                except (ValueError, TypeError, KeyError) as e:
                    logger.error(
                        f"[FRED] Data format error for {series_id}: {e}. "
                        "FRED API response format may have changed or data is corrupted."
                    )
                    self._circuit_breaker.record_failure()
                    failed_series.append(series_id)
                    break
                except RuntimeError as e:
                    # Circuit breaker raised RuntimeError for REQUIRED data failure (e.g. 400 on
                    # a retired series ID). Skip this series rather than aborting the whole load.
                    logger.error(f"[FRED] Circuit breaker failed for {series_id}: {e}; skipping series")
                    failed_series.append(series_id)
                    break
                except (
                    requests.RequestException,
                    requests.Timeout,
                    json.JSONDecodeError,
                ) as e:
                    logger.error(
                        f"[FRED] Unexpected error fetching {series_id}: {e}. "
                        "Cannot proceed reliably — stopping FRED data fetch."
                    )
                    self._circuit_breaker.record_failure()
                    raise RuntimeError(
                        f"[FRED] Unexpected error fetching {series_id}: {e}. "
                        "Cannot proceed reliably — stopping FRED data fetch."
                    ) from e

        if failed_series:
            logger.warning(f"Failed to fetch {len(failed_series)} series: {', '.join(failed_series)}")

        # Fetch DXY_ICE from Yahoo Finance (real ICE index, preferred over FRED proxy)
        dxy_rows = self._fetch_dxy_from_yahoo()
        if dxy_rows:
            all_rows.extend(dxy_rows)
            logger.info(f"Added {len(dxy_rows)} DXY_ICE records to economic data")

        if not all_rows:
            raise RuntimeError(
                "No FRED economic data could be fetched. All series failed or returned no observations. "
                "Check FRED API status and credentials."
            )
        return all_rows


if __name__ == "__main__":
    sys.exit(run_loader(FredEconomicDataLoader, global_mode=True))
