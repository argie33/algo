#!/usr/bin/env python3
"""Consolidated Economic Data Loader - US economic indicators + currency.

Fetches and stores:
- FRED Series: T10Y2Y, FEDFUNDS, BAMLH0A0HYM2, ICSA (daily via FRED API)
- DXY: US Dollar Index from Yahoo Finance (via yfinance)

CONSOLIDATION: Merged load_fred_economic_data.py + load_dxy_index.py into single loader
to eliminate race condition (both were writing economic_data table with different schedules).

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

from config.api_endpoints import get_fred_url  # noqa: E402
from loaders.timeout_config import configure_socket_timeout, get_http_timeout  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.external.yfinance_circuit_breaker import get_circuit_breaker  # noqa: E402
from utils.loaders import get_api_key  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

configure_socket_timeout(30)

# FRED series to fetch
FRED_SERIES = [
    "T10Y2Y",  # 10Y-2Y spread (recession indicator)
    "FEDFUNDS",  # Federal Funds Rate
    "BAMLH0A0HYM2",  # High Yield OAS
    "ICSA",  # Initial Claims
]

# Mirrors utils/data/source_router.py's rate-limit detection keywords
_YF_RATE_LIMIT_KEYWORDS = ("429", "rate", "too many", "invalid crumb", "unauthorized")


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

        # Filter out missing values (FRED uses "." for missing)
        records = []
        for obs in observations:
            if obs.get("value", ".") != ".":
                try:
                    records.append({"date": obs["date"], "value": float(obs["value"])})
                except (ValueError, KeyError) as e:
                    logger.warning(f"[ECONOMIC/FRED] Skipping malformed observation in {series_id}: {e}")

        logger.info(f"[ECONOMIC/FRED] {series_id}: fetched {len(records)} observations")
        return records

    except Exception as e:
        raise RuntimeError(f"[ECONOMIC/FRED] {series_id} fetch failed: {e}") from e


def fetch_dxy_from_yahoo() -> list[dict[str, Any]]:
    """Fetch ICE DXY (US Dollar Index) from Yahoo Finance.

    Uses ticker DX-Y.NYB (Intercontinental Exchange listing on Yahoo Finance).

    Returns:
        list: [{"date": "2026-06-29", "value": 101.13}, ...]

    Raises:
        RuntimeError: If yfinance unavailable, API fails, or no data returned
    """
    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError(
            f"[ECONOMIC/DXY] Required 'yfinance' library not available: {e}. "
            f"This is a deployment-time dependency error."
        ) from e

    logger.debug("[ECONOMIC/DXY] Attempting to fetch DXY (DX-Y.NYB) from Yahoo Finance...")

    end_date = date.today()
    start_date = end_date - timedelta(days=365)

    http_timeout = get_http_timeout()

    # Consult the shared cross-ECS-task IP circuit breaker before hitting yfinance
    # (mirrors utils/data/source_router.py's _yf_download_with_circuit_breaker).
    # wait_or_raise() blocks briefly for short shared-IP bans; long bans raise
    # YFinanceStillBannedError (a RuntimeError), which load() catches and records
    # as DXY_ICE unavailable - no unthrottled request is fired during an active ban.
    circuit_breaker = get_circuit_breaker()
    circuit_breaker.wait_or_raise()

    try:
        dxy = yf.download(
            "DX-Y.NYB",
            start=start_date,
            end=end_date,
            progress=False,
            timeout=http_timeout[1],
        )
    except TimeoutError as e:
        raise RuntimeError(f"[ECONOMIC/DXY] Yahoo Finance fetch timed out: {e}") from e
    except Exception as e:
        if any(keyword in str(e).lower() for keyword in _YF_RATE_LIMIT_KEYWORDS):
            circuit_breaker.report_rate_limit_error()
        raise RuntimeError(f"[ECONOMIC/DXY] Failed to fetch from Yahoo Finance: {e}") from e

    circuit_breaker.report_success()

    if dxy is None or len(dxy) == 0:
        raise RuntimeError("[ECONOMIC/DXY] No data available from Yahoo Finance for DX-Y.NYB")

    rows = []
    for idx, row in dxy.iterrows():
        # idx is a pandas Timestamp; convert to date string
        if hasattr(idx, "tz") and idx.tz is not None:
            date_str = idx.tz_localize(None).date().isoformat()
        else:
            date_str = idx.date().isoformat()

        value = float(row["Close"])
        rows.append({"date": date_str, "value": value})

    logger.info(f"[ECONOMIC/DXY] Fetched {len(rows)} DXY values from Yahoo Finance (DX-Y.NYB)")
    return rows


def store_economic_data(series_id: str, records: list[dict[str, Any]]) -> int:
    """Store economic data in database.

    Args:
        series_id: Series identifier (FRED series ID or "DXY_ICE")
        records: List of {"date": "...", "value": ...} dicts

    Returns: Number of records stored
    """
    if not records:
        return 0

    try:
        with DatabaseContext("write") as cur:
            cur.execute("DELETE FROM economic_data WHERE series_id = %s", (series_id,))
            for record in records:
                cur.execute(
                    """INSERT INTO economic_data (series_id, date, value, data_unavailable, reason)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (series_id, record["date"], record["value"], False, None),
                )
        return len(records)
    except Exception as e:
        logger.error(f"[ECONOMIC] Failed to store {series_id}: {e}")
        return 0


def mark_unavailable(series_id: str, reason: str) -> None:
    """Mark series as unavailable in database.

    Args:
        series_id: Series identifier
        reason: Explanation for unavailability
    """
    try:
        with DatabaseContext("write") as cur:
            cur.execute(
                """INSERT INTO economic_data (series_id, date, value, data_unavailable, reason)
                   VALUES (%s, %s, %s, %s, %s)""",
                (series_id, date.today(), None, True, reason),
            )
    except Exception as e:
        logger.error(f"[ECONOMIC] Failed to mark {series_id} unavailable: {e}")


def load() -> dict[str, Any]:
    """Fetch and store consolidated economic data (FRED + DXY).

    Returns: Dict with status and results
    """
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
            mark_unavailable(series_id, "FRED_API_KEY not configured")
            fred_results[series_id] = "unavailable (no API key)"
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
                mark_unavailable(series_id, str(e))
                fred_results[series_id] = "unavailable (fetch error)"

    # Fetch DXY data
    logger.info("[ECONOMIC] Fetching DXY (US Dollar Index)...")
    try:
        dxy_records = fetch_dxy_from_yahoo()
        inserted = store_economic_data("DXY_ICE", dxy_records)
        total_inserted += inserted
        dxy_result = f"{inserted} records"
    except RuntimeError as e:
        logger.error(f"[ECONOMIC/DXY] Failed: {e}")
        mark_unavailable("DXY_ICE", str(e))
        dxy_result = "unavailable (fetch error)"

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
