#!/usr/bin/env python3
"""SEC EDGAR ticker-to-CIK cache management.

Maintains mappings between stock tickers (AAPL) and SEC CIK numbers (0000320193).
Uses file-based persistent caching with live SEC API refresh.
"""

import json
import logging
import random
import re
import socket
import tempfile
import time
from pathlib import Path
from typing import cast

import requests

logger = logging.getLogger(__name__)

BROWSE_EDGAR_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
_CIK_TAG_RE = re.compile(r"<cik>(\d+)</cik>")

TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
DEFAULT_TIMEOUT = 10.0

# CRITICAL, MANUALLY VERIFIED OVERRIDES for tickers where SEC's own
# company_tickers.json maps to the wrong CIK - not a duplicate-ticker collision in
# our mapping logic (this ticker has exactly one entry in SEC's file), SEC's source
# data itself points at a non-operating-company entity.
#
# XOM: SEC's company_tickers.json maps "XOM" to CIK 2115436 ("ExxonMobil Holdings
# Corp"), which files zero 10-Ks and has zero us-gaap XBRL facts (confirmed live via
# companyfacts - "facts" key present but no "us-gaap" sub-key) - it appears to be a
# stock-plan-administration subsidiary (its recent filings are almost entirely
# "S-8 POS"). The real, publicly-traded Exxon Mobil Corp (NYSE: XOM, the one with
# 10-Ks/segment data/insider Forms 3-4-5) is CIK 34088 ("EXXON MOBIL CORP") - which
# does not appear in company_tickers.json under any ticker at all (confirmed via a
# full scan). Found 2026-07-27 via load_sec_segment_info.py returning
# data_unavailable("no_us_gaap_facts") for XOM despite it obviously being a real,
# segment-reporting filer - traced to this CIK mismatch, which had already silently
# corrupted company_info_sec.entity_name/shares_outstanding for XOM (entity_name
# stored as "ExxonMobil Holdings Corp", shares_outstanding NULL, yet
# data_unavailable=FALSE). Spot-checked 12 other large caps (CVX/JPM/WMT/KO/PG/GE/
# DIS/JNJ/PFE/MRK/T/VZ) - all resolved correctly; this looks like a one-off SEC data
# quirk specific to XOM's corporate history, not a systemic collision-handling bug.
CIK_OVERRIDES: dict[str, str] = {
    "XOM": "0000034088",  # EXXON MOBIL CORP (real 10-K filer) - see comment above
}

# Ensure socket timeout is configured globally
socket.setdefaulttimeout(30)


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
        # CRITICAL FIX: Use platform-appropriate temp directory instead of hardcoded /tmp
        # On Windows, /tmp is a relative path (./tmp) which could cause permission errors
        # and file lock issues that hang the loader. Use tempfile.gettempdir() for cross-platform safety.
        temp_dir = Path(tempfile.gettempdir())
        self._ticker_cache_file = temp_dir / "sec_ticker_cache.json"
        self._load_ticker_cache_from_file()

    def _load_ticker_cache_from_file(self) -> None:
        """Try to load ticker cache from persistent file (survives across processes)."""
        try:
            if self._ticker_cache_file.exists():
                with open(self._ticker_cache_file) as f:
                    data = json.load(f)
                    self._ticker_cache = data.get("mapping")
                    # CRITICAL FIX: Explicit check for timestamp field - missing timestamp means cache is definitely stale
                    cached_timestamp = data.get("timestamp")
                    if cached_timestamp is None:
                        logger.warning("Ticker cache file missing 'timestamp' field - treating cache as stale")
                        self._ticker_cache_time = 0  # Force refresh
                    else:
                        self._ticker_cache_time = cached_timestamp
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
            # GOVERNANCE: Fail-fast on data quality issues. Log explicitly if cache is None.
            cache_len = len(self._ticker_cache) if self._ticker_cache is not None else 0
            if self._ticker_cache is None:
                logger.warning("Saved ticker cache file but cache is None (no data loaded)")
            logger.debug(f"Saved ticker cache to file ({cache_len} symbols)")
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
                # Retry on transient server errors: 429, 403, 502, 503, 504
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
                            f"SEC ticker endpoint {status_name}. Retry in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        raise RuntimeError(
                            f"SEC ticker cache failed after {max_retries} retries on transient error {resp.status_code} {resp.reason}"
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
                if resp.status_code not in (429, 403, 502, 503, 504):
                    raise RuntimeError(f"SEC ticker cache request failed: {e}") from e

        raise RuntimeError("SEC ticker cache refresh exhausted all retries")

    def _lookup_via_browse_edgar(self, symbol: str) -> str | None:
        """Resolve a ticker to a CIK via SEC's legacy browse-edgar company search.

        FIXED 2026-08-17 (goal: "no SEC data" audit): live-confirmed both of SEC's own
        "complete" ticker files (company_tickers.json AND company_tickers_exchange.json,
        ~10,400 entries each, all exchanges represented) are missing real, actively-traded,
        large-cap tickers entirely - AEP (American Electric Power, NYSE, S&P 500 utility),
        PARA (Paramount Global), JHG (Janus Henderson), AMWD, KFS, KW, NSA all confirmed
        absent from both files, yet all resolve to real 10-K filers via this endpoint
        (AEP -> CIK 4904, confirmed against a live 10-K filed 2026-02-12). This isn't a
        one-off SEC data quirk like the XOM CIK_OVERRIDES case - a live DB scan found 149
        symbols with reason='cik_not_found' in annual_income_statement, 59 of them
        plain/undecorated tickers (not preferred-share/rights/dual-class variants that have
        their own explanations), and a 20-symbol sample against this endpoint found 8-9 real
        resolvable filers - too many for manual CIK_OVERRIDES entries to keep up with.
        browse-edgar's CIK= parameter accepts a ticker directly (not just numeric CIKs) and
        is more complete than either bulk ticker file, so it's used here as a last-resort
        fallback, not the primary lookup (slower legacy CGI endpoint, atom XML instead of
        JSON, not intended for bulk traffic - only worth the cost after the fast bulk-file
        lookup and dash-fallback both miss). Kept to a small retry budget (unlike
        _refresh_ticker_cache's 8 retries, which amortizes over a 24h-cached bulk fetch) so a
        run hitting many unresolvable symbols doesn't balloon runtime. A miss here (no <cik>
        tag in the response) means the ticker is genuinely unregistered/delisted/non-filing -
        returns None, never fabricates a CIK.
        """
        max_retries = 2
        for attempt in range(max_retries):
            try:
                if self._rate_limiter:
                    cast(object, self._rate_limiter).wait()  # type: ignore
                resp = self._session.get(
                    BROWSE_EDGAR_URL,
                    params={
                        "action": "getcompany",
                        "CIK": symbol,
                        "type": "10-K",
                        "dateb": "",
                        "owner": "include",
                        "count": "1",
                        "output": "atom",
                    },
                    timeout=max(self._timeout, 15.0),
                )
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                logger.warning(f"browse-edgar CIK fallback network error for {symbol}: {e}")
                return None

            if resp.status_code in (429, 403, 502, 503, 504):
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                logger.warning(f"browse-edgar CIK fallback got HTTP {resp.status_code} for {symbol}")
                return None
            if resp.status_code != 200:
                return None

            match = _CIK_TAG_RE.search(resp.text)
            if not match:
                return None
            return match.group(1).zfill(10)
        return None

    def symbol_to_cik(self, symbol: str) -> str:
        """Convert ticker (AAPL) to zero-padded CIK (0000320193).

        Refreshes cache if expired. Raises RuntimeError if symbol not found.
        """
        override = CIK_OVERRIDES.get(symbol.upper())
        if override:
            return override

        if self._ticker_cache is None or time.time() - self._ticker_cache_time > self._cache_ttl:
            self._refresh_ticker_cache()

        # GOVERNANCE: Fail-fast on data quality issues. Cache must be loaded after refresh.
        if self._ticker_cache is None:
            raise RuntimeError("SEC ticker cache failed to load (cache is None after refresh)")
        cik = self._ticker_cache.get(symbol.upper())
        if not cik and "." in symbol:
            # Dual-class share tickers use a dot in most market-data feeds (BRK.A, TAP.A,
            # WSO.B) but SEC's own company_tickers.json uses a dash (BRK-A, TAP-A, WSO-B) -
            # live-confirmed 2026-07-28: 23 of 39 dotted tickers reporting missing_sec_data
            # (including BRK.A/BRK.B - Berkshire Hathaway itself, which has no undotted
            # ticker at all) resolve correctly once the dot is swapped for a dash. The
            # remaining dotted tickers are ".R" (rights) suffixes, which genuinely have no
            # separate SEC ticker entry - only retried here, not fabricated.
            cik = self._ticker_cache.get(symbol.upper().replace(".", "-"))
        if not cik:
            # FIXED 2026-08-17 (goal: "no SEC data" audit): last-resort browse-edgar fallback
            # for tickers missing from both SEC bulk ticker files - see
            # _lookup_via_browse_edgar's docstring for the live-verified scale (AEP/PARA/JHG/
            # AMWD/KFS/KW/NSA and more). Cache a successful resolution into the in-memory AND
            # persistent file cache so repeated lookups (this process and others sharing the
            # file) don't re-hit the slow legacy endpoint every time.
            cik = self._lookup_via_browse_edgar(symbol)
            if cik:
                self._ticker_cache[symbol.upper()] = cik
                self._save_ticker_cache_to_file()
        if not cik:
            raise ValueError(f"Symbol {symbol} not found in SEC ticker cache")
        return cik
