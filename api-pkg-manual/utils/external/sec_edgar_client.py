#!/usr/bin/env python3
"""SEC EDGAR client — core API methods and rate limiting.

Handles SEC EDGAR XBRL API calls with rate limiting and retry logic.
Uses TickerCache for ticker-to-CIK conversion.
"""

import logging
import os
import random
import threading
import time
from typing import Any, cast

import requests

from utils.external import sec_statements
from utils.external.sec_ticker_cache import TickerCache

logger = logging.getLogger(__name__)

EDGAR_BASE = os.getenv("EDGAR_BASE_URL", "https://data.sec.gov")
TICKER_URL = os.getenv("SEC_TICKER_URL", "https://www.sec.gov/files/company_tickers.json")
DEFAULT_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "algo-trading argeropolos@gmail.com",
)


class RateLimiter:
    """SEC requires <10 req/sec. We target 8/sec for safety margin."""

    def __init__(self, requests_per_second: int = 8):
        self.min_interval = 1.0 / requests_per_second
        self._last_request = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_request
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_request = time.monotonic()


class SecEdgarClient:
    """Client for SEC EDGAR XBRL APIs.

    Args:
        user_agent: Required by SEC. Format: "AppName admin@example.com"
        cache_ttl: Seconds to cache the symbol-to-CIK mapping.
    """

    def __init__(
        self,
        user_agent: str | None = None,
        cache_ttl: int = 86400,
        timeout: float = 10.0,
    ):
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        if "@" not in self.user_agent:
            logger.warning(
                "SEC requires User-Agent with contact email. Set SEC_USER_AGENT env var: 'AppName admin@example.com'"
            )
        self.timeout = timeout
        # Rate limiter: SEC allows 10 req/sec. With many parallel ECS tasks,
        # we need to be conservative. Using 2 req/sec per task limits total impact.
        # If 5+ tasks run in parallel = 10 req/sec. If fewer, we stay under limit.
        self._rate_limiter = RateLimiter(2)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json",
            }
        )
        # Delegate ticker cache to TickerCache class
        self._ticker_cache_manager = TickerCache(
            cache_ttl=cache_ttl,
            timeout=timeout,
            rate_limiter=self._rate_limiter,
            session=self._session,
        )

    # ----- Symbol/CIK lookups -----

    def symbol_to_cik(self, symbol: str) -> str:
        """Convert ticker (AAPL) to zero-padded CIK (0000320193).
        Raises ValueError if symbol not found in SEC cache."""
        return self._ticker_cache_manager.symbol_to_cik(symbol)

    # ----- Core API -----

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        """All XBRL facts for a company. Single endpoint, returns everything.

        Returns: {
            "cik": 320193,
            "entityName": "Apple Inc.",
            "facts": {
                "us-gaap": {
                    "Revenues": {"label": "...", "units": {"USD": [...]}},
                    "Assets": {...},
                    ...
                }
            }
        }
        """
        url = f"{EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik}.json"
        return self._get_json(url)

    def get_concept(
        self,
        cik: str,
        taxonomy: str,
        concept: str,
    ) -> dict[str, Any]:
        """Specific concept (e.g. Revenues) — lighter than full company facts."""
        url = f"{EDGAR_BASE}/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{concept}.json"
        return self._get_json(url)

    def get_submissions(self, cik: str) -> dict[str, Any]:
        """List of all filings for a company (10K, 10Q, 8K, etc.)."""
        url = f"{EDGAR_BASE}/submissions/CIK{cik}.json"
        return self._get_json(url)

    def _get_json(self, url: str) -> dict[str, Any]:
        """Fetch JSON from SEC API with retry logic for transient errors.

        Retries on transient errors (429, 403, 502, 503, 504) with exponential backoff.
        With 8+ parallel ECS tasks hitting the 10 req/sec SEC limit, we need longer
        backoff times to avoid cascading failures. Server errors (502, 503, 504) are
        treated as transient per HTTP standards - retry with exponential backoff.
        """
        max_retries = 8
        for attempt in range(max_retries):
            try:
                self._rate_limiter.wait()
                resp = self._session.get(url, timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < max_retries - 1:
                    wait_time = 4 * (2**attempt) + random.uniform(0, 2)
                    logger.warning(
                        f"SEC API network error for {url}: {e}. Retry in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait_time)
                    continue
                raise RuntimeError(f"SEC API network error after {max_retries} retries: {e}") from e

            # 404 means the data doesn't exist - permanent error, don't retry
            if resp.status_code == 404:
                raise FileNotFoundError(f"SEC filing not found: {url}")

            # Handle transient server errors with exponential backoff:
            # 429 = Rate limit, 403 = Forbidden/Throttle, 502 = Bad Gateway,
            # 503 = Service Unavailable, 504 = Gateway Timeout
            if resp.status_code in (429, 403, 502, 503, 504):
                if attempt < max_retries - 1:
                    base_wait = 4 * (2**attempt)
                    jitter = random.uniform(0, base_wait * 0.3)
                    wait_time = base_wait + jitter
                    status_names = {
                        429: "rate limited (429)",
                        403: "forbidden (403)",
                        502: "bad gateway (502)",
                        503: "service unavailable (503)",
                        504: "gateway timeout (504)",
                    }
                    status_name = status_names.get(resp.status_code, f"transient {resp.status_code}")
                    logger.warning(
                        f"SEC API {status_name} for {url}. Retry in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    raise RuntimeError(
                        f"SEC API failed after {max_retries} retries on transient error {resp.status_code} {resp.reason}: {url}"
                    )

            # Other HTTP errors (2xx/3xx/4xx except 404)
            try:
                resp.raise_for_status()
                return cast(dict[str, Any], resp.json())
            except requests.HTTPError as e:
                raise RuntimeError(f"SEC API error for {url}: {e}") from e

        raise RuntimeError("SEC API request exhausted all retries")

    # ----- High-level extraction helpers -----

    def get_annual_concept(
        self,
        symbol: str,
        concept: str,
        taxonomy: str = "us-gaap",
    ) -> list[dict[str, Any]]:
        """Fetch annual values for a GAAP concept. Filters to FY periods.

        Returns: [
            {"fiscal_year": 2024, "value": 391035000000, "filed": "2024-11-01"},
            ...
        ]
        """
        cik = self.symbol_to_cik(symbol)
        data = self.get_concept(cik, taxonomy, concept)

        units = data.get("units")
        results: list[dict[str, Any]] = []
        if units is None:
            return results
        for unit, entries in units.items():
            for entry in entries:
                if entry.get("fp") != "FY":
                    continue
                results.append(
                    {
                        "fiscal_year": entry.get("fy"),
                        "value": entry.get("val"),
                        "unit": unit,
                        "filed": entry.get("filed"),
                        "period_end": entry.get("end"),
                        "form": entry.get("form"),
                    }
                )

        # Sort by fiscal year, filed date — both required for correct financial statement ordering
        def sort_key(r: dict[str, Any]) -> tuple[int | float, str]:
            year = r.get("fiscal_year")
            filed = r.get("filed")
            if year is None:
                raise ValueError(
                    f"SEC Edgar data missing fiscal_year for {symbol} concept {concept}. "
                    f"Cannot sort or use undated financial statements. "
                    f"Check SEC data source or API response."
                )
            if not filed:
                raise ValueError(
                    f"SEC Edgar data missing filed date for {symbol} {year} {concept}. "
                    f"Cannot establish statement recency. "
                    f"Check SEC data source or API response."
                )
            return (int(year), filed)

        results.sort(key=sort_key)
        return results

    def get_quarterly_concept(
        self,
        symbol: str,
        concept: str,
        taxonomy: str = "us-gaap",
    ) -> list[dict[str, Any]]:
        """Same as annual, but returns quarterly periods (Q1-Q4)."""
        cik = self.symbol_to_cik(symbol)
        data = self.get_concept(cik, taxonomy, concept)

        units = data.get("units")
        results: list[dict[str, Any]] = []
        if units is None:
            return results
        for unit, entries in units.items():
            for entry in entries:
                if entry.get("fp") not in ("Q1", "Q2", "Q3", "Q4"):
                    continue
                results.append(
                    {
                        "fiscal_year": entry.get("fy"),
                        "fiscal_period": entry.get("fp"),
                        "value": entry.get("val"),
                        "unit": unit,
                        "filed": entry.get("filed"),
                        "period_end": entry.get("end"),
                        "form": entry.get("form"),
                    }
                )
        # Validate fiscal_year exists before sorting quarterly data
        for r in results:
            if r.get("fiscal_year") is None:
                raise ValueError(
                    f"SEC Edgar quarterly data missing fiscal_year for {symbol} {concept}. "
                    f"Cannot sort quarterly statements without year information. "
                    f"Check SEC data source or API response."
                )
        results.sort(key=lambda r: (int(r["fiscal_year"]), r["fiscal_period"] or ""))
        return results

    # ----- Financial statements (balance sheet, income statement, cash flow) -----

    def get_balance_sheet(self, symbol: str, period: str = "annual") -> list[dict[str, Any]]:
        """Aggregate balance sheet rows from key concepts."""
        return sec_statements.get_balance_sheet(self, symbol, period)

    def get_income_statement(self, symbol: str, period: str = "annual") -> list[dict[str, Any]]:
        """Aggregate income statement rows from key concepts."""
        return sec_statements.get_income_statement(self, symbol, period)

    def get_cash_flow(self, symbol: str, period: str = "annual") -> list[dict[str, Any]]:
        """Aggregate cash flow rows from key concepts."""
        return sec_statements.get_cash_flow(self, symbol, period)
