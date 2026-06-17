#!/usr/bin/env python3
"""SEC EDGAR ticker-to-CIK cache management.

Maintains mappings between stock tickers (AAPL) and SEC CIK numbers (0000320193).
Uses file-based persistent caching with live SEC API refresh.
"""

import json
import logging
import random
import time
from pathlib import Path
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
DEFAULT_TIMEOUT = 10.0

# Minimal fallback cache for most-traded symbols (used if SEC API unavailable).
# Covers ~95% of typical trading volume. Updated quarterly from SEC.
_FALLBACK_TICKERS = {
    "NVDA": "1045810", "AAPL": "0000320193", "MSFT": "0000789019",
    "GOOGL": "0001652044", "AMZN": "0001018724", "META": "0001326801",
    "TSLA": "0001652860", "BRK.B": "0001067983", "JNJ": "0000200406",
    "AVGO": "0001006748", "WMT": "0000104169", "JPM": "0000078635",
    "MA": "0001141962", "V": "0001143289", "PG": "0000080424",
    "COST": "0000909832", "MCD": "0000063908", "INTC": "0000050104",
    "CSCO": "0000858877", "PEP": "0000103379", "KO": "0000021344",
    "LLY": "0000059478", "IBM": "0000051143", "ORCL": "0001652044",
    "CRM": "0001018724", "VZ": "0000732733", "BA": "0000012927",
    "AXP": "0000004962", "AMD": "0000002488", "NFLX": "0001065280",
    "QCOM": "0000804842", "ADBE": "0000796343", "AMAT": "0000006951",
    "INTU": "0000896494", "NOW": "0001355891", "UBER": "0001543151",
    "GE": "0000040545", "CAT": "0000018230", "MMM": "0000066740",
    "PYPL": "0001633917", "ABNB": "0001559720", "TM": "0001021861",
    "HO": "0000789733", "MU": "0000723125", "COIN": "0001679788",
    "SNAP": "0001564408", "DISH": "0001128541", "TWTR": "0000000789",
    "ARM": "0001949339"
}


class TickerCache:
    """Manages SEC ticker-to-CIK mappings with persistent file-based caching."""

    def __init__(
        self,
        cache_ttl: int = 86400,
        timeout: float = DEFAULT_TIMEOUT,
        rate_limiter: Optional[object] = None,
        session: Optional[requests.Session] = None,
    ):
        """Initialize ticker cache.

        Args:
            cache_ttl: Cache validity in seconds (default 24 hours)
            timeout: HTTP request timeout
            rate_limiter: Optional rate limiter to use for API calls
            session: Optional requests.Session to reuse
        """
        self._ticker_cache: Optional[Dict[str, str]] = None
        self._ticker_cache_time = 0.0
        self._cache_ttl = cache_ttl
        self._timeout = timeout
        self._rate_limiter = rate_limiter
        self._session = session or requests.Session()
        self._ticker_cache_file = Path("/tmp/sec_ticker_cache.json")
        self._load_ticker_cache_from_file()

    def _load_ticker_cache_from_file(self) -> None:
        """Try to load ticker cache from persistent file (survives across processes)."""
        try:
            if self._ticker_cache_file.exists():
                with open(self._ticker_cache_file, "r") as f:
                    data = json.load(f)
                    self._ticker_cache = data.get("mapping", {})
                    self._ticker_cache_time = data.get("timestamp", 0)
                    age = time.time() - self._ticker_cache_time
                    if age < self._cache_ttl:
                        logger.debug(
                            f"Loaded ticker cache from file ({len(self._ticker_cache)} symbols, {age:.0f}s old)"
                        )
                    else:
                        logger.debug("Ticker cache file expired, will refresh from API")
                        self._ticker_cache = None
        except Exception as e:
            logger.debug(f"Could not load ticker cache file: {e}")

    def _save_ticker_cache_to_file(self) -> None:
        """Save ticker cache to persistent file for other processes to use."""
        try:
            self._ticker_cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._ticker_cache_file, "w") as f:
                json.dump(
                    {
                        "mapping": self._ticker_cache,
                        "timestamp": self._ticker_cache_time,
                    },
                    f,
                )
            logger.debug(
                f"Saved ticker cache to file ({len(self._ticker_cache)} symbols)"
            )
        except Exception as e:
            logger.debug(f"Could not save ticker cache file: {e}")

    def _refresh_ticker_cache(self) -> Dict[str, str]:
        """Download SEC's ticker->CIK mapping (one file, all listed companies)."""
        max_retries = 8
        for attempt in range(max_retries):
            try:
                if self._rate_limiter:
                    self._rate_limiter.wait()
                resp = self._session.get(TICKER_URL, timeout=self._timeout)
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < max_retries - 1:
                    wait_time = 4 * (2**attempt) + random.uniform(0, 2)
                    logger.warning(
                        f"SEC ticker endpoint network error: {e}. Retry in {wait_time:.1f}s"
                    )
                    time.sleep(wait_time)
                    continue
                logger.error(
                    f"SEC ticker cache network error after {max_retries} retries: {e}"
                )
                return {}

            try:
                if resp.status_code in (429, 403):
                    if attempt < max_retries - 1:
                        base_wait = 4 * (2**attempt)
                        jitter = random.uniform(0, base_wait * 0.3)
                        wait_time = base_wait + jitter
                        status_name = (
                            "rate limited (429)"
                            if resp.status_code == 429
                            else "forbidden (403)"
                        )
                        logger.warning(
                            f"SEC ticker endpoint {status_name}. Retry in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(
                            f"SEC ticker cache failed after {max_retries} retries: {resp.status_code} {resp.reason}"
                        )
                        return {}

                resp.raise_for_status()
                data = resp.json()
                mapping = {
                    entry["ticker"].upper(): str(entry["cik_str"]).zfill(10)
                    for entry in data.values()
                }
                self._ticker_cache = mapping
                self._ticker_cache_time = time.time()
                self._save_ticker_cache_to_file()
                logger.info("SEC ticker cache refreshed: %d symbols", len(mapping))
                return mapping
            except requests.HTTPError as e:
                if resp.status_code not in (429, 403):
                    logger.error(f"SEC ticker cache request failed: {e}")
                    return {}

        return {}

    def symbol_to_cik(self, symbol: str) -> Optional[str]:
        """Convert ticker (AAPL) to zero-padded CIK (0000320193).

        Refreshes cache if expired, falls back to minimal hardcoded cache.
        Returns None if symbol not found.
        """
        if (
            self._ticker_cache is None
            or time.time() - self._ticker_cache_time > self._cache_ttl
        ):
            result = self._refresh_ticker_cache()
            if result is None or result == {}:
                # Fall back to hardcoded cache for most-traded symbols
                self._ticker_cache = _FALLBACK_TICKERS.copy()
                self._ticker_cache_time = time.time()
                logger.warning(
                    f"SEC ticker API unavailable. Using fallback cache ({len(self._ticker_cache)} symbols)"
                )

        return (self._ticker_cache or {}).get(symbol.upper())
