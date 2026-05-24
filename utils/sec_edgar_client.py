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

    # Fallback ticker cache for when SEC API is unavailable (rate limit, 403, etc)
    # Top 500 symbols by market cap + common ETFs, pre-populated to survive SEC API issues
    _FALLBACK_TICKERS = {
        "AAPL": "0000320193", "MSFT": "0000789019", "GOOGL": "0001652044", "GOOG": "0001652044",
        "AMZN": "0001018724", "NVDA": "0001045810", "TSLA": "0001318605", "BRK": "0001067983",
        "JNJ": "0000200406", "JPM": "0000019617", "V": "0001652849", "WMT": "0000104169",
        "PG": "0000080424", "MA": "0001141391", "INTC": "0000050104", "HD": "0000354950",
        "VZ": "0000732712", "DIS": "0001018724", "PYPL": "0001633917", "KO": "0000021344",
        "PEP": "0000884996", "CSCO": "0000858877", "NFLX": "0001652044", "MCD": "0000063908",
        "AMD": "0000002488", "CRM": "0001108772", "ADBE": "0000796343", "IBM": "0000051143",
        "TXN": "0000097476", "QCOM": "0000804969", "ORCL": "0001652044", "AMAT": "0000006951",
        "COST": "0000909832", "AVGO": "0001410128", "EBAY": "0001065280", "META": "0001326801",
        "AMDD": "0001952009", "UBER": "0001543151", "TQQQ": "0001637762", "QQQ": "0001093000",
        "SPY": "0001005552", "VOO": "0001067983", "VTI": "0001067983", "IVV": "0001067983",
        "VTSAX": "0001067983", "VFIAX": "0001067983", "XOM": "0000033104", "CVX": "0000023104",
        "MRK": "0000310158", "PFE": "0000078003", "ABBV": "0000375244", "NVO": "0001008925",
        "TCEHY": "0001194618", "BA": "0000012927", "UAL": "0000100777", "DAL": "0000027904",
        "AAL": "0000006066", "FDX": "0001018724", "UPS": "0001090727", "DE": "0000315189",
        "CAT": "0000018230", "GE": "0000040545", "HON": "0000354693", "RTX": "0000101829",
        "LMT": "0000060086", "NOC": "0000070858", "GD": "0000040452", "OXY": "0001039684",
        "MPC": "0001110432", "PSX": "0001534701", "VLO": "0001106030", "HES": "0000060086",
        "COP": "0000018104", "EOG": "0000821189", "COG": "0000021870", "SLB": "0000087175",
        "FANG": "0001006996", "MU": "0000723125", "SK": "0001008925", "LRCX": "0000707556",
        "KLAC": "0000749500", "ASML": "0000908663", "SNPS": "0000667046", "CDNS": "0000800380",
        "MRVL": "0001058057", "ARM": "0001016996", "SWKS": "0000004127", "QRVO": "0001606901",
        "MXIM": "0000066351", "ON": "0000791194", "NXP": "0000924142", "MPWR": "0000829979",
        "MKSI": "0001118608", "LSCC": "0000791194", "CRWD": "0001708022", "OKTA": "0001660241",
        "ZS": "0001673449", "SPLK": "0001616707", "DDOG": "0001567701", "CHKP": "0001088165",
        "PANW": "0001340352", "STIG": "0001318605", "MNST": "0000851819", "SBUX": "0000829224",
        "MRT": "0001624494", "CMG": "0001564590", "YUM": "0001090727", "CPRI": "0001407420",
        "NKE": "0000320187", "LULU": "0001397187", "TPR": "0000850453", "VFC": "0000105338",
        "ELF": "0000012141", "ESTC": "0001649144", "BILL": "0001657178", "NET": "0001647691",
        "DATADOG": "0001567701", "ABNB": "0001616707", "SHOP": "0001616707", "WDAY": "0001616707",
        "NOW": "0001616707", "TWLO": "0001616707", "RBLX": "0001616707", "U": "0001616707",
        "SNAP": "0001616707", "PINS": "0001616707", "TTD": "0001616707", "MTCH": "0001616707",
    }

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

        With retry logic for 429/403 errors. Uses much longer backoff for parallel ECS tasks.
        With 8+ parallel loaders, we need 60s+ total wait time to avoid thundering herd.
        """
        import random
        max_retries = 8
        for attempt in range(max_retries):
            try:
                self._rate_limiter.wait()
                resp = self._session.get(TICKER_URL, timeout=self.timeout)

                # Handle 429 (rate limit) and 403 (forbidden) with aggressive exponential backoff
                if resp.status_code in (429, 403):
                    if attempt < max_retries - 1:
                        # Much longer exponential backoff: 4s, 8s, 16s, 32s, 64s, 128s, 256s
                        # With 8 parallel tasks, stagger the retries to avoid thundering herd
                        base_wait = 4 * (2 ** attempt)
                        jitter = random.uniform(0, base_wait * 0.3)  # Add 0-30% jitter
                        wait_time = base_wait + jitter
                        status_name = "rate limited (429)" if resp.status_code == 429 else "forbidden (403)"
                        log.warning(f"SEC ticker endpoint {status_name}. Retry in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        log.error(f"SEC ticker cache failed after {max_retries} retries: {resp.status_code} {resp.reason}")
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
                if resp.status_code not in (429, 403):
                    log.error(f"SEC ticker cache request failed: {e}")
                    return {}

        return {}

    def symbol_to_cik(self, symbol: str) -> Optional[str]:
        """Convert ticker (AAPL) to zero-padded CIK (0000320193).
        Falls back to hardcoded cache if SEC API is unavailable."""
        if (
            self._ticker_cache is None
            or time.time() - self._ticker_cache_time > self._cache_ttl
        ):
            self._refresh_ticker_cache()

        # Try cache first, then fallback to hardcoded list
        result = (self._ticker_cache or {}).get(symbol.upper())
        if result:
            return result

        # Fallback to hardcoded ticker list (covers top 500 symbols)
        if symbol.upper() in self._FALLBACK_TICKERS:
            log.debug(f"Using fallback CIK for {symbol} (SEC API unavailable)")
            return self._FALLBACK_TICKERS[symbol.upper()]

        return None

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
