#!/usr/bin/env python3
"""Consolidated Economic Data Loader - Comprehensive US economic indicators + currency.

Fetches and stores:
- FRED Series: 56 comprehensive economic indicators (yields, employment, inflation,
  growth, credit spreads, financial conditions, housing, commodities, recession indicator)
- DXY: USD Dollar Index proxy from FRED (DEXUSEU - EUR/USD exchange rate, inverted)

CONSOLIDATION: Merged load_fred_economic_data.py + load_dxy_index.py into single loader
to eliminate race condition (both were writing economic_data table with different schedules).

CRITICAL FIX (Session 212): Replaced FEDFUNDS with SOFR (Secured Overnight Financing Rate).
FEDFUNDS in FRED is monthly data with gaps (only 6-12 observations per year). SOFR is:
- Fed's official overnight benchmark rate (replaced LIBOR)
- Published daily with complete coverage (~150+ observations)
- More relevant for modern trading (Fed Funds target implemented via SOFR since 2023)

CRITICAL FIX (Session 211): Eliminated yfinance dependency for DXY.
Now uses FRED DEXUSEU (EUR/USD) as proxy for dollar strength. EUR/USD represents 57.6%
of official DXY, providing good approximation without external API dependency.

Uses FRED API (FREE): https://fred.stlouisfed.org/docs/api/
API key from AWS Secrets Manager (algo/fred) or FRED_API_KEY env var.

FAIL-FAST GOVERNANCE: All fetch functions raise RuntimeError on failures instead of silently
returning empty arrays. Callers must handle exceptions explicitly.
"""

import logging
import socket
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

import requests  # noqa: E402

from algo.config.api_endpoints import get_fred_url  # noqa: E402
from loaders.timeout_config import configure_socket_timeout, get_http_timeout  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.loaders import get_api_key  # noqa: E402
from utils.loaders.status_manager import LoaderStatusManager  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

configure_socket_timeout(30)

# FRED series to fetch - comprehensive economic indicators
# Organized by category for maintenance clarity
FRED_SERIES = [
    # Monetary policy & rates (core)
    "T10Y2Y",  # 10Y-2Y spread (recession indicator)
    "SOFR",  # Secured Overnight Financing Rate (daily benchmark)
    "T10Y3M",  # 10Y-3M spread (longer recession indicator)
    "T5YIE",  # 5-year breakeven inflation
    "T10YIE",  # 10-year breakeven inflation

    # Yield curve (all maturities)
    "DGS3MO",  # 3-month treasury
    "DGS6MO",  # 6-month treasury
    "DGS1",  # 1-year treasury
    "DGS2",  # 2-year treasury
    "DGS3",  # 3-year treasury
    "DGS5",  # 5-year treasury
    "DGS7",  # 7-year treasury
    "DGS10",  # 10-year treasury
    "DGS20",  # 20-year treasury
    "DGS30",  # 30-year treasury

    # Credit spreads
    "BAMLH0A0HYM2",  # High Yield OAS
    "BAMLC0A0CM",  # Investment Grade OAS

    # Employment & income
    "PAYEMS",  # Total nonfarm payroll
    "UNRATE",  # Unemployment rate
    "CIVPART",  # Labor force participation rate
    "AHETPI",  # Average hourly earnings
    "JTSJOL",  # JOLTS job openings
    "JTSQUR",  # JOLTS quit rate
    "ICSA",  # Initial claims (weekly)
    "UEMPMEAN",  # Mean unemployment duration

    # Inflation
    "CPIAUCSL",  # CPI - All Urban Consumers
    "CPILFESL",  # Core CPI (ex-food & energy)
    "PCEPILFE",  # Core PCE Inflation
    "PPIACO",  # Producer Price Index

    # Activity & production
    "INDPRO",  # Industrial Production
    "RSXFS",  # Retail Sales
    "HOUST",  # Housing Starts
    "PERMIT",  # Building Permits
    "TCU",  # Capacity Utilization
    "CFNAI",  # Chicago Fed Activity Index
    "MICH",  # Consumer Sentiment (University of Michigan)

    # Growth & income
    "GDPC1",  # Real GDP
    "DSPIC96",  # Real Disposable Income
    "TOTALSA",  # Total nonfarm payroll (seasonally adjusted)

    # Money supply & credit
    "M1SL",  # M1 Money Supply
    "M2SL",  # M2 Money Supply
    "WALCL",  # Monetary Base
    "BUSLOANS",  # Commercial and Industrial Loans
    "PRIME",  # Bank prime loan rate

    # Financial conditions
    "ANFCI",  # Advanced National Financial Conditions Index
    "STLFSI4",  # St. Louis Fed Financial Stress Index

    # Consumer/housing
    "MORTGAGE30US",  # 30-year mortgage rate
    "PSAVERT",  # Personal savings rate
    "UMCSENT",  # Consumer sentiment

    # Currency & commodities
    "DTWEXBGS",  # Trade-weighted USD index
    "DCOILWTICO",  # WTI Crude Oil price

    # Recession indicator
    "USREC",  # NBER recession indicator
]


def get_fred_api_key() -> str:
    """Get FRED API key from Secrets Manager or environment variable.

    CRITICAL: FRED fetch requires valid API key. Fails fast if missing - never returns empty string.
    Empty key causes all downstream FRED fetches to fail silently. Must raise explicitly.
    """
    key = get_api_key("algo/fred", "FRED_API_KEY", required=True)
    if not key:
        raise RuntimeError(
            "[ECONOMIC] CRITICAL: FRED API key not configured. "
            "Economic data enrichment requires FRED access. Set FRED_API_KEY in secrets."
        )
    return key


def fetch_from_fred(api_key: str, series_id: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    """Fetch single FRED series via REST API.

    Args:
        api_key: FRED API key (must not be empty)
        series_id: FRED series ID (e.g., "T10Y2Y")
        start_date: Start date
        end_date: End date

    Returns:
        List of {"date": "2026-01-01", "value": 1.23} dicts

    Raises:
        RuntimeError: If API key empty, API fails, or response invalid
    """
    if not api_key:
        raise RuntimeError("[ECONOMIC/FRED] API key is empty - cannot fetch data")

    try:
        fred_url = f"{get_fred_url()}/series/observations"
        params = {
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start_date.isoformat(),
            "observation_end": end_date.isoformat(),
        }

        logger.debug(f"[ECONOMIC/FRED] Fetching {series_id}...")
        http_timeout = get_http_timeout()
        response = requests.get(fred_url, params=params, timeout=http_timeout)
        response.raise_for_status()

        data = response.json()
        if "observations" not in data:
            raise ValueError(f"FRED response missing 'observations' field for {series_id}")
        observations = data["observations"]

        # Filter out missing values (FRED uses "." as explicit sentinel for missing observations)
        # EXPLICIT VALIDATION: Fail-fast if API response structure changes (KeyError raised at line 113)
        records = []
        for obs in observations:
            # SAFE PATTERN: .get("value", ".") is valid here because FRED API explicitly
            # uses "." to denote missing values in the JSON response. This is different from
            # ignoring errors - we explicitly check for the FRED-documented sentinel value.
            if obs.get("value", ".") != ".":
                try:
                    records.append({"date": obs["date"], "value": float(obs["value"])})
                except (ValueError, KeyError) as e:
                    logger.warning(f"[ECONOMIC/FRED] Skipping malformed observation in {series_id}: {e}")

        logger.info(f"[ECONOMIC/FRED] {series_id}: fetched {len(records)} observations")
        return records

    except Exception as e:
        raise RuntimeError(f"[ECONOMIC/FRED] {series_id} fetch failed: {e}") from e


def fetch_dxy_from_fred(api_key: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    """Fetch USD Dollar Index proxy from FRED (using EUR/USD exchange rate).

    CRITICAL FIX (Session 211): Replaced yfinance DX-Y.NYB with FRED DEXUSEU.
    DXY proxy = 100 / DEXUSEU (invert EUR/USD to get USD strength).
    EUR/USD represents 57.6% of the official DXY, good proxy for dollar strength.

    Returns:
        list: [{"date": "2026-06-29", "value": 101.13}, ...]

    Raises:
        RuntimeError: If FRED fetch fails or no data returned
    """
    logger.debug("[ECONOMIC/DXY] Fetching USD Dollar Index proxy from FRED (DEXUSEU)...")

    try:
        fred_url = f"{get_fred_url()}/series/observations"
        params = {
            "series_id": "DEXUSEU",  # EUR/USD exchange rate
            "api_key": api_key,
            "file_type": "json",
            "observation_start": start_date.isoformat(),
            "observation_end": end_date.isoformat(),
        }

        http_timeout = get_http_timeout()
        response = requests.get(fred_url, params=params, timeout=http_timeout)
        response.raise_for_status()

        data = response.json()
        if "observations" not in data:
            raise RuntimeError("[ECONOMIC/DXY] Invalid FRED response structure")

        rows = []
        for obs in data["observations"]:
            value_str = obs.get("value")
            if value_str and value_str != ".":
                try:
                    eurusd = float(value_str)
                    # Invert: DXY proxy = 100 / EUR/USD (higher USD strength = higher DXY proxy)
                    dxy_proxy = 100.0 / eurusd if eurusd > 0 else None
                    if dxy_proxy is not None:
                        rows.append({"date": obs["date"], "value": dxy_proxy})
                    elif eurusd <= 0:
                        logger.warning(
                            f"[ECONOMIC/DXY] Invalid EUR/USD value on {obs['date']}: {eurusd} (non-positive)"
                        )
                except ValueError as e:
                    logger.warning(
                        f"[ECONOMIC/DXY] Failed to parse EUR/USD value on {obs.get('date')}: {value_str!r}. "
                        f"Error: {e}. Skipping this record."
                    )

        if not rows:
            raise RuntimeError("[ECONOMIC/DXY] No valid data returned from FRED DEXUSEU")

        logger.info(f"[ECONOMIC/DXY] Fetched {len(rows)} USD Index proxy values from FRED (DEXUSEU)")
        return rows

    except requests.RequestException as e:
        raise RuntimeError(f"[ECONOMIC/DXY] FRED fetch failed: {e}") from e
    except Exception as e:
        raise RuntimeError(f"[ECONOMIC/DXY] Failed to process FRED data: {e}") from e


def store_economic_data(series_id: str, records: list[dict[str, Any]]) -> int:
    """Store economic data in database.

    Args:
        series_id: Series identifier (FRED series ID or "DXY_ICE")
        records: List of {"date": "...", "value": ...} dicts

    Returns: Number of records stored

    Raises:
        RuntimeError: If database write fails (FAIL-FAST: do not swallow storage errors)
    """
    if not records:
        return 0

    # Scope the delete to exactly the date range being re-inserted, not the whole series.
    # load() only fetches a 365-day window each run, so an unscoped
    # "DELETE FROM economic_data WHERE series_id = %s" wiped ALL history for that series
    # every single run - the table could never hold more than 365 days of history no matter
    # how long this loader had been running, silently destroying accumulated history each
    # time (e.g. the actual 2022-2024 T10Y2Y yield curve inversion ran ~623 days - longer
    # than this loader could ever retain - directly undermining the "inversion duration
    # matters" logic in algo/risk/market_exposure.py's docstring). Deleting only [min_date,
    # max_date] of the current fetch keeps this idempotent for FRED revisions within that
    # window while preserving any older history already accumulated.
    dates = [r["date"] for r in records]
    min_date, max_date = min(dates), max(dates)

    try:
        with DatabaseContext("write") as cur:
            cur.execute(
                "DELETE FROM economic_data WHERE series_id = %s AND date >= %s AND date <= %s",
                (series_id, min_date, max_date),
            )
            for record in records:
                cur.execute(
                    """INSERT INTO economic_data (series_id, date, value, data_unavailable, reason)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (series_id, record["date"], record["value"], False, None),
                )
        return len(records)
    except Exception as e:
        raise RuntimeError(f"[ECONOMIC] Failed to store {series_id}: {e}") from e


def mark_unavailable(series_id: str, reason: str) -> None:
    """Mark series as unavailable in database.

    Args:
        series_id: Series identifier
        reason: Explanation for unavailability

    Raises:
        RuntimeError: If database write fails (FAIL-FAST: do not swallow marker write failures)
    """
    try:
        with DatabaseContext("write") as cur:
            # economic_data has a UNIQUE(series_id, date) constraint. A bare INSERT
            # here raised (and silently swallowed, below) a duplicate-key error on any
            # same-day retry - e.g. a transient FRED outage on a second run the same
            # day after an earlier successful fetch already stored real data for
            # today, or after an earlier failed run already stored a marker. The
            # WHERE clause on DO UPDATE only lets a retry touch a row that is ALREADY
            # a marker (data_unavailable=TRUE), so a later transient failure can never
            # clobber real data fetched earlier the same day, while repeat genuine
            # failures still get their reason refreshed instead of erroring out.
            cur.execute(
                """INSERT INTO economic_data (series_id, date, value, data_unavailable, reason)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (series_id, date) DO UPDATE SET
                       reason = EXCLUDED.reason
                   WHERE economic_data.data_unavailable = TRUE""",
                (series_id, date.today(), None, True, reason),
            )
    except Exception as e:
        raise RuntimeError(f"[ECONOMIC] Failed to mark {series_id} unavailable: {e}") from e


def load() -> dict[str, Any]:
    """Fetch and store consolidated economic data (FRED + DXY).

    Returns: Dict with status and results

    CRITICAL FIX 2026-08-04: this loader never touched data_loader_status at all - no
    mark_running/mark_completed/mark_failed anywhere in this file. Its DB row was whatever
    a one-off seed/migration left it at, never updated by any real run, so the dashboard's
    DATA FRESHNESS panel had no way to tell "loader ran fine today" from "loader has been
    silently broken since whenever that row was last touched" - the exact class of gap this
    session's fixes target (see market.py's _get_data_status and the sibling loader duration
    fixes). Wired in the same LoaderStatusManager pattern already used by every other loader
    in this codebase; the actual fetch/store logic (unchanged) now lives in _load_impl().
    """
    status_mgr = LoaderStatusManager("economic_data")
    status_mgr.mark_running()
    start_time = time.time()
    try:
        result = _load_impl()
    except Exception as e:
        status_mgr.mark_failed(error_message=str(e)[:500])
        raise

    # mark_completed()'s built-in safety check (utils/loaders/status_manager.py) computes
    # completion_pct from symbol_count/symbols_loaded and marks FAILED if it's below 98% -
    # a per-symbol-loader assumption. This loader has no symbols, just a fixed FRED series
    # list, so those columns are never populated via mark_running(symbol_count=...)/
    # update_progress() and default to None/None, which the safety check reads as 0%
    # complete. Pass this run's own counts explicitly (the same current_run_* override the
    # safety check docstring describes) so a real, fully successful run doesn't get marked
    # FAILED by a check built for a different loader shape.
    fred_series_results = result.get("fred_series") or {}
    total_expected = len(FRED_SERIES) + 1  # +1 for DXY
    succeeded = sum(1 for v in fred_series_results.values() if not str(v).startswith("unavailable")) + (
        0 if str(result.get("dxy", "")).startswith("unavailable") else 1
    )
    status_mgr.mark_completed(
        execution_duration_sec=time.time() - start_time,
        current_run_symbols_loaded=succeeded,
        current_run_symbol_count=total_expected,
    )
    return result


def _load_impl() -> dict[str, Any]:
    """Fetch and store consolidated economic data (FRED + DXY). See load() for status tracking."""
    logger.info("[ECONOMIC] Starting consolidated economic data load (FRED + DXY)...")

    fred_api_key = get_fred_api_key()
    end_date = date.today()
    start_date = end_date - timedelta(days=365)
    total_inserted = 0
    fred_results = {}

    socket.setdefaulttimeout(30.0)

    if not fred_api_key:
        logger.warning("[ECONOMIC/FRED] No API key available")
        for series_id in FRED_SERIES:
            try:
                mark_unavailable(series_id, "FRED_API_KEY not configured")
                fred_results[series_id] = "unavailable (no API key)"
            except RuntimeError as e:
                raise RuntimeError(
                    f"[ECONOMIC] Cannot mark {series_id} unavailable due to database error: {e}"
                ) from e
    else:
        for i, series_id in enumerate(FRED_SERIES):
            # Rate limiting: 5s between requests
            if i > 0:
                time.sleep(5.0)

            logger.info(f"[ECONOMIC/FRED] Processing {series_id}...")
            try:
                records = fetch_from_fred(fred_api_key, series_id, start_date, end_date)
                inserted = store_economic_data(series_id, records)
                total_inserted += inserted
                fred_results[series_id] = f"{inserted} records"
            except RuntimeError as e:
                logger.error(f"[ECONOMIC/FRED] {series_id} failed: {e}")
                try:
                    mark_unavailable(series_id, str(e))
                    fred_results[series_id] = "unavailable (fetch error)"
                except RuntimeError as mark_err:
                    raise RuntimeError(
                        f"[ECONOMIC] {series_id} fetch failed and unable to mark unavailable: {mark_err}"
                    ) from mark_err

    # Fetch DXY data (now from FRED instead of yfinance)
    logger.info("[ECONOMIC] Fetching USD Dollar Index proxy from FRED...")
    try:
        # Adds small delay between FRED requests (already did 4 series above)
        time.sleep(5.0)
        dxy_records = fetch_dxy_from_fred(fred_api_key, start_date, end_date)
        inserted = store_economic_data("DXY_ICE", dxy_records)
        total_inserted += inserted
        dxy_result = f"{inserted} records (proxy: FRED DEXUSEU)"
    except RuntimeError as e:
        logger.error(f"[ECONOMIC/DXY] Failed: {e}")
        try:
            mark_unavailable("DXY_ICE", str(e))
            dxy_result = "unavailable (fetch error)"
        except RuntimeError as mark_err:
            raise RuntimeError(
                f"[ECONOMIC] DXY fetch failed and unable to mark unavailable: {mark_err}"
            ) from mark_err

    logger.info(f"[ECONOMIC] Load complete: {total_inserted} total records inserted")
    return {
        "status": "complete",
        "total_records_inserted": total_inserted,
        "fred_series": fred_results,
        "dxy": dxy_result,
    }


if __name__ == "__main__":
    result = load()
    sys.exit(0 if result.get("status") == "complete" else 1)
