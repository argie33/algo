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

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date, datetime
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
        self._rate_limiter = RateLimiter(8)
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json",
        })
        self._ticker_cache: Optional[Dict[str, str]] = None
        self._ticker_cache_time = 0.0
        self._cache_ttl = cache_ttl

    # ----- Symbol/CIK lookups -----

    def _refresh_ticker_cache(self) -> Dict[str, str]:
        """Download SEC's ticker→CIK mapping (one file, all listed companies)."""
        self._rate_limiter.wait()
        resp = self._session.get(TICKER_URL, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        # Format: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
        mapping = {
            entry["ticker"].upper(): str(entry["cik_str"]).zfill(10)
            for entry in data.values()
        }
        self._ticker_cache = mapping
        self._ticker_cache_time = time.time()
        log.info("SEC ticker cache loaded: %d symbols", len(mapping))
        return mapping

    def symbol_to_cik(self, symbol: str) -> Optional[str]:
        """Convert ticker (AAPL) to zero-padded CIK (0000320193)."""
        if (
            self._ticker_cache is None
            or time.time() - self._ticker_cache_time > self._cache_ttl
        ):
            self._refresh_ticker_cache()
        return self._ticker_cache.get(symbol.upper())

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
        self._rate_limiter.wait()
        resp = self._session.get(url, timeout=self.timeout)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()

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
            "Revenues", "CostOfRevenue", "GrossProfit", "OperatingExpenses",
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
        """Pivot multiple concepts into rows keyed by (fiscal_year, fiscal_period)."""
        getter = self.get_annual_concept if period == "annual" else self.get_quarterly_concept
        rows: Dict[Any, Dict[str, Any]] = {}
        for concept in concepts:
            for entry in getter(symbol, concept):
                key = (
                    entry["fiscal_year"],
                    entry.get("fiscal_period", "FY"),
                    entry.get("period_end"),
                )
                row = rows.setdefault(key, {
                    "symbol": symbol,
                    "fiscal_year": entry["fiscal_year"],
                    "fiscal_period": entry.get("fiscal_period", "FY"),
                    "period_end": entry.get("period_end"),
                    "filed": entry.get("filed"),
                    "form": entry.get("form"),
                })
                # Snake-case the concept for column compatibility
                col = _to_snake(concept)
                # Keep latest filing if multiple for same period
                if col not in row or (entry.get("filed") or "") > (row.get(f"_filed_{col}") or ""):
                    row[col] = entry["value"]
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
