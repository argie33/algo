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
from typing import cast

import requests

logger = logging.getLogger(__name__)

TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
DEFAULT_TIMEOUT = 10.0


class TickerCache:
    """Manages SEC ticker-to-CIK mappings with persistent file-based caching."""

    def __init__(
        self,
        cache_ttl: int = 86400,
        timeout: float = DEFAULT_TIMEOUT,
        rate_limiter: object | None = None,
        session: requests.Session | None = None,
    ):
        """Initialize ticker cache.

        Args:
            cache_ttl: Cache validity in seconds (default 24 hours)
            timeout: HTTP request timeout
            rate_limiter: Optional rate limiter to use for API calls
            session: Optional requests.Session to reuse
        """
        self._ticker_cache: dict[str, str] | None = None
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
                with open(self._ticker_cache_file) as f:
                    data = json.load(f)
                    self._ticker_cache = data.get("mapping")
                    self._ticker_cache_time = data.get("timestamp", 0)
                    age = time.time() - self._ticker_cache_time
                    if age < self._cache_ttl:
                        logger.debug(
                            f"Loaded ticker cache from file ({len(self._ticker_cache)} symbols, {age:.0f}s old)"
                        )
                    else:
                        logger.debug("Ticker cache file expired, will refresh from API")
                        self._ticker_cache = None
        except (json.JSONDecodeError, ValueError) as e:
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
            logger.debug(f"Saved ticker cache to file ({len(self._ticker_cache or {})} symbols)")
        except (json.JSONDecodeError, ValueError) as e:
            logger.debug(f"Could not save ticker cache file: {e}")

    def _refresh_ticker_cache(self) -> dict[str, str]:
        """Download SEC's ticker->CIK mapping (one file, all listed companies)."""
        max_retries = 8
        for attempt in range(max_retries):
            try:
                if self._rate_limiter:
                    cast(object, self._rate_limiter).wait()  # type: ignore
                resp = self._session.get(TICKER_URL, timeout=self._timeout)
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < max_retries - 1:
                    wait_time = 4 * (2**attempt) + random.uniform(0, 2)
                    logger.warning(f"SEC ticker endpoint network error: {e}. Retry in {wait_time:.1f}s")
                    time.sleep(wait_time)
                    continue
                raise RuntimeError(f"SEC ticker cache unavailable after {max_retries} retries: {e}") from e

            try:
                if resp.status_code in (429, 403):
                    if attempt < max_retries - 1:
                        base_wait = 4 * (2**attempt)
                        jitter = random.uniform(0, base_wait * 0.3)
                        wait_time = base_wait + jitter
                        status_name = "rate limited (429)" if resp.status_code == 429 else "forbidden (403)"
                        logger.warning(
                            f"SEC ticker endpoint {status_name}. Retry in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        raise RuntimeError(
                            f"SEC ticker cache failed after {max_retries} retries: {resp.status_code} {resp.reason}"
                        )

                resp.raise_for_status()
                data = resp.json()
                mapping = {entry["ticker"].upper(): str(entry["cik_str"]).zfill(10) for entry in data.values()}
                self._ticker_cache = mapping
                self._ticker_cache_time = time.time()
                self._save_ticker_cache_to_file()
                logger.info(f"SEC ticker cache refreshed: {len(mapping)} symbols")
                return mapping
            except requests.HTTPError as e:
                if resp.status_code not in (429, 403):
                    raise RuntimeError(f"SEC ticker cache request failed: {e}") from e

        raise RuntimeError("SEC ticker cache refresh exhausted all retries")

    def symbol_to_cik(self, symbol: str) -> str:
        """Convert ticker (AAPL) to zero-padded CIK (0000320193).

        Refreshes cache if expired. Raises RuntimeError if symbol not found.
        """
        if self._ticker_cache is None or time.time() - self._ticker_cache_time > self._cache_ttl:
            self._refresh_ticker_cache()

        cik = (self._ticker_cache or {}).get(symbol.upper())
        if not cik:
            raise ValueError(f"Symbol {symbol} not found in SEC ticker cache")
        return cik
