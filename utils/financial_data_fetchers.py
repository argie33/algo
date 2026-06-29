#!/usr/bin/env python3
"""
Consolidated financial data fetcher utilities.

Replaces duplicated fetch patterns across loaders (DXY, economic data, etc.)
Eliminates 50-100 LOC of copy-paste fetching logic.
"""

import logging
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)


def fetch_financial_data_from_source(
    source_name: str,
    fetch_func: Callable[[], Any],
    parse_func: Callable[[Any], list[dict[str, Any]]],
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    """Generic financial data fetcher with consistent error handling.

    Args:
        source_name: Name of the data source (e.g., "Yahoo Finance", "IEX Cloud")
        fetch_func: Function that fetches raw data from the source
        parse_func: Function that converts raw data to [{"date": "...", "value": ...}, ...]
        symbol: Optional symbol for logging context

    Returns:
        List of dicts with "date" and "value" keys, or empty list if fetch fails
    """
    try:
        logger.info(f"[{source_name}] Fetching data{' for ' + symbol if symbol else ''}...")
        raw_data = fetch_func()

        if raw_data is None or (isinstance(raw_data, (list, dict)) and len(raw_data) == 0):
            logger.debug(f"[{source_name}] Returned no data{' for ' + symbol if symbol else ''}")
            return []

        rows = parse_func(raw_data)

        if rows:
            logger.info(f"[{source_name}] Fetched {len(rows)} record(s){' for ' + symbol if symbol else ''}")
        else:
            logger.warning(
                f"[{source_name}] Fetched raw data but parsing returned no valid records"
                f"{' for ' + symbol if symbol else ''}"
            )

        return rows

    except ImportError as e:
        logger.error(
            f"[CRITICAL] {source_name} fetch failed: required library not available: {e}. "
            f"Dependency error, not a transient API failure."
        )
        return []
    except Exception as e:
        logger.warning(f"[{source_name}] Failed to fetch{' for ' + symbol if symbol else ''}: {e}")
        return []


def fetch_dxy_from_iex() -> list[dict[str, Any]]:
    """Fetch ICE DXY from IEX Cloud API.

    Returns:
        list: [{"date": "2026-06-29", "value": 101.13}, ...] or empty list if unavailable
    """
    import requests

    from utils.loaders import get_api_key

    iex_key = get_api_key("algo/iex_cloud", "IEX_API_KEY", required=False)
    if not iex_key:
        logger.debug("[IEX] API key not configured")
        return []

    url = "https://cloud.iexapis.com/stable/stock/DXY/chart/1y"
    resp = requests.get(url, params={"token": iex_key}, timeout=(10, 20))
    resp.raise_for_status()

    data = resp.json()
    if not data or not isinstance(data, list):
        return []

    rows = []
    for item in data:
        try:
            rows.append({"date": item["date"], "value": float(item["close"])})
        except (KeyError, ValueError, TypeError):
            continue

    return rows


def fetch_dxy_from_yahoo() -> list[dict[str, Any]]:
    """Fetch ICE DXY from Yahoo Finance.

    NOTE: As of 2026-06-29, Yahoo Finance's ^DXY ticker is unavailable ("possibly delisted").

    Returns:
        list: [{"date": "2026-06-29", "value": 101.13}, ...] or empty list if unavailable
    """
    import yfinance as yf

    end_date = date.today()
    start_date = end_date - timedelta(days=365)

    dxy = yf.download("^DXY", start=start_date, end=end_date, progress=False)

    if dxy is None or len(dxy) == 0:
        return []

    rows = []
    for idx, row in dxy.iterrows():
        if idx.tz_aware:
            date_str = idx.tz_localize(None).date().isoformat()
        else:
            date_str = idx.date().isoformat()

        value = float(row["Close"])
        rows.append({"date": date_str, "value": value})

    return rows
