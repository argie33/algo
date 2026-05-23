"""
SEC EDGAR direct client for official fundamentals.

Free, unlimited, official US SEC fundamentals via XBRL.
- 10K/10Q/8K filings
- All XBRL-tagged GAAP concepts (revenue, EPS, balance sheet, cash flow)
- Insider transactions (Form 4)
- Restated earnings, footnotes
- Historical back to 2009 (XBRL mandate start)

Why this beats yfinance:
- Official source — same data the SEC requires companies to file
- More accurate — yfinance scrapes Yahoo, which scrapes SEC anyway
- Reliable — SEC API has 99.99% uptime, yfinance breaks weekly
- Free — yfinance pricing has tightened; SEC is permanently free
- Legal — yfinance scraping is grey area; SEC API is sanctioned

Rate limit: 10 requests/second (very generous).
Required: User-Agent header with contact email (SEC requirement).

Usage:
    client = SecEdgarClient(user_agent="your-app you@example.com")
    cik = client.symbol_to_cik("AAPL")
    facts = client.get_company_facts(cik)
    revenue = client.get_concept(cik, "us-gaap", "Revenues")
"""


import json
import logging
import os
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger(__name__)

EDGAR_BASE = "https://data.sec.gov"
TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
DEFAULT_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "stocks-platform admin@example.com",  # User MUST override per SEC policy
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
        user_agent: Optional[str] = None,
        cache_ttl: int = 86400,
        timeout: float = 10.0,
    ):
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        if "@" not in self.user_agent:
            log.warning(
                "SEC requires User-Agent with contact email. "
                "Set SEC_USER_AGENT env var: 'AppName admin@example.com'"
            )
        self.timeout = timeout
        # Rate limiter: SEC allows 10 req/sec. With many parallel ECS tasks,
        # we need to be conservative. Using 2 req/sec per task limits total impact.
        # If 5+ tasks run in parallel = 10 req/sec. If fewer, we stay under limit.
        self._rate_limiter = RateLimiter(2)
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json",
        })
        self._ticker_cache: Optional[Dict[str, str]] = None
        self._ticker_cache_time = 0.0
        self._cache_ttl = cache_ttl
        # File-based cache to survive across processes/containers
        self._ticker_cache_file = Path("/tmp/sec_ticker_cache.json")
        self._load_ticker_cache_from_file()

    # ----- Symbol/CIK lookups -----

    def _load_ticker_cache_from_file(self) -> None:
        """Try to load ticker cache from persistent file (survives across processes)."""
        try:
            if self._ticker_cache_file.exists():
                with open(self._ticker_cache_file, 'r') as f:
                    data = json.load(f)
                    self._ticker_cache = data.get('mapping', {})
                    self._ticker_cache_time = data.get('timestamp', 0)
                    age = time.time() - self._ticker_cache_time
                    if age < self._cache_ttl:
                        log.debug(f"Loaded ticker cache from file ({len(self._ticker_cache)} symbols, {age:.0f}s old)")
                    else:
                        log.debug("Ticker cache file expired, will refresh from API")
                        self._ticker_cache = None
        except Exception as e:
            log.debug(f"Could not load ticker cache file: {e}")

    def _save_ticker_cache_to_file(self) -> None:
        """Save ticker cache to persistent file for other processes to use."""
        try:
            self._ticker_cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._ticker_cache_file, 'w') as f:
                json.dump({
                    'mapping': self._ticker_cache,
                    'timestamp': self._ticker_cache_time,
                }, f)
            log.debug(f"Saved ticker cache to file ({len(self._ticker_cache)} symbols)")
        except Exception as e:
            log.debug(f"Could not save ticker cache file: {e}")

    def _refresh_ticker_cache(self) -> Dict[str, str]:
        """Download SEC's ticker→CIK mapping (one file, all listed companies).

        With retry logic for 429 rate limit errors. Uses much longer backoff for parallel ECS tasks.
        With 8+ parallel loaders, we need 60s+ total wait time to avoid thundering herd.
        """
        import random
        max_retries = 8
        for attempt in range(max_retries):
            try:
                self._rate_limiter.wait()
                resp = self._session.get(TICKER_URL, timeout=self.timeout)

                # Handle rate limiting with aggressive exponential backoff + jitter
                if resp.status_code == 429:
                    if attempt < max_retries - 1:
                        # Much longer exponential backoff: 4s, 8s, 16s, 32s, 64s, 128s, 256s
                        # With 8 parallel tasks, stagger the retries to avoid thundering herd
                        base_wait = 4 * (2 ** attempt)
                        jitter = random.uniform(0, base_wait * 0.3)  # Add 0-30% jitter
                        wait_time = base_wait + jitter
                        total_wait = sum(4 * (2 ** i) for i in range(attempt + 1))
                        log.warning(f"SEC ticker endpoint rate limited (429). Retry in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries}, total wait so far: {total_wait}s)")
                        time.sleep(wait_time)
                        continue
                    else:
                        log.error("SEC ticker cache failed after 8 retries (total ~500s): 429 Too Many Requests - will use cached data if available")
                        return {}

                resp.raise_for_status()
                data = resp.json()
                # Format: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
                mapping = {
                    entry["ticker"].upper(): str(entry["cik_str"]).zfill(10)
                    for entry in data.values()
                }
                self._ticker_cache = mapping
                self._ticker_cache_time = time.time()
                self._save_ticker_cache_to_file()  # Save for other processes
                log.info("SEC ticker cache loaded: %d symbols", len(mapping))
                return mapping
            except requests.HTTPError as e:
                if resp.status_code != 429:
                    log.error(f"SEC ticker cache request failed: {e}")
                    return {}

        return {}

    def symbol_to_cik(self, symbol: str) -> Optional[str]:
        """Convert ticker (AAPL) to zero-padded CIK (0000320193)."""
        if (
            self._ticker_cache is None
            or time.time() - self._ticker_cache_time > self._cache_ttl
        ):
            self._refresh_ticker_cache()
        return (self._ticker_cache or {}).get(symbol.upper())

    # ----- Core API -----

    def get_company_facts(self, cik: str) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
        """Specific concept (e.g. Revenues) — lighter than full company facts."""
        url = f"{EDGAR_BASE}/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{concept}.json"
        return self._get_json(url)

    def get_submissions(self, cik: str) -> Dict[str, Any]:
        """List of all filings for a company (10K, 10Q, 8K, etc.)."""
        url = f"{EDGAR_BASE}/submissions/CIK{cik}.json"
        return self._get_json(url)

    def _get_json(self, url: str) -> Dict[str, Any]:
        """Fetch JSON from SEC API with retry logic for rate limiting.

        With 8+ parallel ECS tasks hitting the 10 req/sec SEC limit, we need
        much longer backoff times to avoid cascading failures.
        """
        import random
        max_retries = 8
        for attempt in range(max_retries):
            self._rate_limiter.wait()
            resp = self._session.get(url, timeout=self.timeout)

            # 404 means the data doesn't exist
            if resp.status_code == 404:
                return {}

            # Handle rate limiting with exponential backoff + jitter
            if resp.status_code == 429:
                if attempt < max_retries - 1:
                    # Much longer exponential backoff: 4s, 8s, 16s, 32s, 64s, 128s, 256s
                    base_wait = 4 * (2 ** attempt)
                    jitter = random.uniform(0, base_wait * 0.3)  # Add 0-30% jitter
                    wait_time = base_wait + jitter
                    log.debug(f"SEC API rate limited (429) for {url}. Retry in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    log.warning(f"SEC API failed after {max_retries} retries (total ~500s): {url}")
                    return {}

            # Other HTTP errors
            try:
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError as e:
                log.debug(f"SEC API error for {url}: {e}")
                return {}

        return {}

    # ----- High-level extraction helpers -----

    def get_annual_concept(
        self,
        symbol: str,
        concept: str,
        taxonomy: str = "us-gaap",
    ) -> List[Dict[str, Any]]:
        """Fetch annual values for a GAAP concept. Filters to FY periods.

        Returns: [
            {"fiscal_year": 2024, "value": 391035000000, "filed": "2024-11-01"},
            ...
        ]
        """
        cik = self.symbol_to_cik(symbol)
        if not cik:
            return []
        try:
            data = self.get_concept(cik, taxonomy, concept)
        except requests.HTTPError as e:
            log.debug("SEC %s/%s for %s: %s", taxonomy, concept, symbol, e)
            return []

        units = data.get("units", {})
        results: List[Dict[str, Any]] = []
        for unit, entries in units.items():
            for entry in entries:
                if entry.get("fp") != "FY":
                    continue
                results.append({
                    "fiscal_year": entry.get("fy"),
                    "value": entry.get("val"),
                    "unit": unit,
                    "filed": entry.get("filed"),
                    "period_end": entry.get("end"),
                    "form": entry.get("form"),
                })
        results.sort(key=lambda r: (r["fiscal_year"] or 0, r.get("filed") or ""))
        return results

    def get_quarterly_concept(
        self,
        symbol: str,
        concept: str,
        taxonomy: str = "us-gaap",
    ) -> List[Dict[str, Any]]:
        """Same as annual, but returns quarterly periods (Q1-Q4)."""
        cik = self.symbol_to_cik(symbol)
        if not cik:
            return []
        try:
            data = self.get_concept(cik, taxonomy, concept)
        except requests.HTTPError:
            return []

        units = data.get("units", {})
        results: List[Dict[str, Any]] = []
        for unit, entries in units.items():
            for entry in entries:
                if entry.get("fp") not in ("Q1", "Q2", "Q3", "Q4"):
                    continue
                results.append({
                    "fiscal_year": entry.get("fy"),
                    "fiscal_period": entry.get("fp"),
                    "value": entry.get("val"),
                    "unit": unit,
                    "filed": entry.get("filed"),
                    "period_end": entry.get("end"),
                    "form": entry.get("form"),
                })
        results.sort(key=lambda r: (r["fiscal_year"] or 0, r["fiscal_period"]))
        return results

    def get_balance_sheet(self, symbol: str, period: str = "annual") -> List[Dict[str, Any]]:
        """Aggregate balance sheet rows from key concepts."""
        concepts = [
            "Assets", "AssetsCurrent", "Liabilities", "LiabilitiesCurrent",
            "StockholdersEquity", "CashAndCashEquivalentsAtCarryingValue",
            "AccountsReceivableNetCurrent", "InventoryNet",
            "PropertyPlantAndEquipmentNet", "Goodwill", "LongTermDebt",
        ]
        return self._aggregate_concepts(symbol, concepts, period)

    def get_income_statement(self, symbol: str, period: str = "annual") -> List[Dict[str, Any]]:
        concepts = [
            "Revenues", "SalesRevenueNet",  # Revenue (try both concept names)
            "CostOfRevenue", "CostsAndExpenses",  # Cost (try both)
            "GrossProfit", "OperatingExpenses",
            "OperatingIncomeLoss", "NetIncomeLoss", "EarningsPerShareBasic",
            "EarningsPerShareDiluted", "WeightedAverageNumberOfSharesOutstandingBasic",
        ]
        return self._aggregate_concepts(symbol, concepts, period)

    def get_cash_flow(self, symbol: str, period: str = "annual") -> List[Dict[str, Any]]:
        concepts = [
            "NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInInvestingActivities",
            "NetCashProvidedByUsedInFinancingActivities",
            "PaymentsToAcquirePropertyPlantAndEquipment",
            "Depreciation", "DepreciationAndAmortization",
        ]
        return self._aggregate_concepts(symbol, concepts, period)

    def _aggregate_concepts(
        self,
        symbol: str,
        concepts: List[str],
        period: str,
    ) -> List[Dict[str, Any]]:
        """Pivot multiple concepts into rows keyed by (fiscal_year, fiscal_period).

        Optimized: Uses get_company_facts (1 API call) instead of multiple get_concept calls.
        """
        cik = self.symbol_to_cik(symbol)
        if not cik:
            return []

        # Fetch all facts for this company in a single API call
        try:
            all_facts = self.get_company_facts(cik)
        except Exception:
            all_facts = {}

        if not all_facts:
            return []

        # Extract concepts from all_facts (us-gaap taxonomy)
        us_gaap_facts = all_facts.get("facts", {}).get("us-gaap", {})
        rows: Dict[Any, Dict[str, Any]] = {}
        fp_filter = "FY" if period == "annual" else ("Q1", "Q2", "Q3", "Q4")

        for concept in concepts:
            concept_data = us_gaap_facts.get(concept, {})
            units = concept_data.get("units", {})

            for unit, entries in units.items():
                for entry in entries:
                    fp = entry.get("fp")
                    if period == "annual" and fp != "FY":
                        continue
                    if period == "quarterly" and fp not in fp_filter:
                        continue

                    key = (
                        entry.get("fy"),
                        fp if period == "quarterly" else "FY",
                        entry.get("end"),
                    )
                    row = rows.setdefault(key, {
                        "symbol": symbol,
                        "fiscal_year": entry.get("fy"),
                        "fiscal_period": fp if period == "quarterly" else "FY",
                        "period_end": entry.get("end"),
                        "filed": entry.get("filed"),
                        "form": entry.get("form"),
                    })
                    # Snake-case the concept for column compatibility
                    col = _to_snake(concept)
                    # Keep latest filing if multiple for same period
                    if col not in row or (entry.get("filed") or "") > (row.get(f"_filed_{col}") or ""):
                        row[col] = entry.get("val")
                        row[f"_filed_{col}"] = entry.get("filed")

        # Drop helper fields, return sorted
        result = []
        for row in rows.values():
            result.append({k: v for k, v in row.items() if not k.startswith("_filed_")})
        result.sort(key=lambda r: (r["fiscal_year"] or 0, r["fiscal_period"]))
        return result


def _to_snake(name: str) -> str:
    """CamelCase → snake_case. Used for converting XBRL concept names to columns."""
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and not name[i - 1].isupper():
            out.append("_")
        out.append(ch.lower())
    return "".join(out)
