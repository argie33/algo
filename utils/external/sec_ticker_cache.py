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
#
# DMC/SHOE/GRSD: a DIFFERENT category from XOM above - not SEC source data being wrong,
# but a live availability gap this session traced 2026-08-31 while following up the
# browse-edgar fuzzy-match fix (commit 4061fd5c1, same day): all 3 are active-universe
# symbols that came back "CIK not found" after that fix correctly started rejecting
# unverified fuzzy matches (browse-edgar's CIK=<symbol> endpoint is also returning HTTP
# 403 for these right now - a separate, transient SEC-side block on that legacy CGI
# endpoint). Live-verified each via https://data.sec.gov/submissions/CIK<n>.json (the
# same authoritative source this file's own _verify_ticker_matches_cik already trusts):
# CIK 1047340's own tickers=["DMC"]/exchanges=["NYSE"] and CIK 895447's
# tickers=["SHOE"]/["Nasdaq"] and CIK 1839799's tickers=["GRSD"]/["Nasdaq"] all
# self-confirm cleanly - these are real, correct, currently-active exact matches, just
# temporarily missing from this morning's cached company_tickers.json snapshot (a known,
# already-documented gap in that bulk file - see _lookup_via_browse_edgar's own
# docstring for the AEP/PARA/JHG precedent). IMPORTANT: the original browse-edgar fix's
# commit message assumed "DMC" should mean DMC Global Inc - that assumption was WRONG,
# not just stale-cache-related: DMC Global renamed its own ticker to "BOOM" (CIK 34067,
# tickers=["BOOM"], confirmed same way) and does not use "DMC" at all anymore; our own
# stock_symbols.security_name for DMC already independently says "Del Monte Corporation
# Ordinary Shares" (NYSE) - i.e. CIK 1047340 was the correct resolution the whole time
# for OUR tracked "DMC" entry. Pinned here (rather than left to self-heal on the next
# cache refresh + a hopefully-recovered browse-edgar) since these are live, in-universe
# symbols needing real data now, and a verified-correct override never goes stale the
# way a bulk-file snapshot or a flaky legacy endpoint can.
#
# HOS: yet another category - a genuine, very recent (2026-08-31, per CIK 866829's own
# formerNames history) corporate rename that SEC's company_tickers.json "tickers" field
# hasn't caught up with yet. CIK 866829's submissions.json `name` is now "HORNBECK
# OFFSHORE SERVICES, INC." (most recent filing 2026-09-04, an S-8) with formerNames
# showing "HELIX ENERGY SOLUTIONS GROUP INC" (2006-2026-08-31) and, before that, "CAL
# DIVE INTERNATIONAL INC" - i.e. this is the same continuously-filing entity, just
# renamed, not two different companies. SEC's own bulk company_tickers.json snapshot
# still lists this CIK under the pre-rename ticker "HLX" only, so a plain ticker lookup
# for our tracked "HOS" symbol finds nothing and falls through to "no_income_statement"/
# missing-SEC-data reasons even though the real, current XBRL data exists and is being
# filed under this exact CIK right now. Found 2026-09-05 (goal session: "SEC/XBRL
# missing data to zero" sweep) via a fork's live companyfacts/submissions.json check
# flagging HOS as a suspected phantom-symbol case; confirmed directly against
# submissions.json rather than assumed. Same self-healing caveat as DMC/SHOE/GRSD above
# once SEC's snapshot catches up with the rename - safe to remove this entry then.
#
# GV/FTRK/SGRX: found 2026-09-06 (coverage campaign continuation, dividend_data/
# current_reports_8k/shares_outstanding "cik_not_found"/"symbol_not_found" buckets).
# Same root cause as the GV/HOS-shaped pattern above - SEC's own bulk company_tickers.json
# AND company_tickers_exchange.json (checked both) list only a STALE/secondary ticker per
# CIK, not the symbol's current primary listing, even though the per-company
# submissions.json (or, for SGRX, its own formerNames rename trail) confirms the right
# one. Each individually live-verified against submissions.json for (a) exact company-name
# match to our stock_symbols.security_name and (b) a real, recent (2026) 10-K/6-K filing -
# not just a name match, since a name match alone can be a dead/unrelated entity (this
# session's own search also surfaced NBN/HIFS name-matches whose CIKs turned out to be
# stale shells with no filings since 2019 / no 10-K ever - deliberately NOT added here,
# see this session's memory for the full rejection trail):
# - GV (Visionary Holdings Inc., Nasdaq): CIK 1892274's own submissions.json tickers
#   array is ['GV', 'GVHGF'] - GV is directly self-confirmed - but both SEC bulk ticker
#   files only carry the OTC-era 'GVHGF' for this CIK. Latest 10-K 2026-01-28, most
#   recent filing (6-K) 2026-09-03 - clearly live.
# - FTRK (Fast Track Group, Nasdaq): CIK 2027262's submissions.json tickers are
#   ['FTRKF', 'FTRKD'] (pre-uplisting OTC classes), not the current Nasdaq ticker FTRK
#   itself, but the entity name is an exact, unambiguous match with no formerNames
#   history (a brand-new registrant, consistent with a recent uplisting). Latest 10-K
#   2026-06-30, most recent filing (6-K) 2026-09-03 - clearly live.
# - SGRX (SANGRIX INC., Nasdaq): CIK 1735556's submissions.json ticker is still 'BTOG'
#   (its pre-rename ticker) but `name`="SANGRIX INC." and formerNames shows "BIT ORIGIN
#   Ltd" ending 2026-08-26 - i.e. this is the exact same "renamed very recently, SEC's
#   ticker field hasn't caught up" shape as HOS above. Latest 10-K 2025-10-31, most
#   recent filing (6-K) 2026-09-03 - clearly live.
# Same self-healing caveat as the entries above: safe to remove once SEC's own ticker
# snapshot catches up with each rename/uplisting.
CIK_OVERRIDES: dict[str, str] = {
    "XOM": "0000034088",  # EXXON MOBIL CORP (real 10-K filer) - see comment above
    "DMC": "0001047340",  # DEL MONTE CORP (NYSE) - see DMC/SHOE/GRSD comment above
    "SHOE": "0000895447",  # SHOE STATION GROUP INC (Nasdaq) - see comment above
    "GRSD": "0001839799",  # GRANDSTAND Ltd (Nasdaq) - see comment above
    "HOS": "0000866829",  # HORNBECK OFFSHORE SERVICES INC (formerly Helix Energy Solutions Group) - see HOS comment above
    "GV": "0001892274",  # Visionary Holdings Inc. (Nasdaq) - see GV/FTRK/SGRX comment above
    "FTRK": "0002027262",  # Fast Track Group (Nasdaq) - see GV/FTRK/SGRX comment above
    "SGRX": "0001735556",  # SANGRIX INC. (formerly BIT ORIGIN Ltd) - see GV/FTRK/SGRX comment above
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
            cik = match.group(1).zfill(10)

            # BUG FOUND 2026-08-31 (goal session: "get all the data we need" full-coverage
            # audit): browse-edgar's CIK=<symbol> search is NOT a reliable exact-ticker
            # lookup for an unregistered/mistyped symbol - it silently falls back to a
            # company-name/prefix search and returns the first hit's CIK with no exactness
            # guarantee, unlike the docstring above's "never fabricates a CIK" claim (true
            # for the fast-path bulk-file lookup, not for this fallback). Live-confirmed via
            # real SEC data three separate ways: symbol "IAC" (should be IAC/InterActiveCorp)
            # resolved here to CIK 1800227, whose OWN submissions.json lists ticker "PPLI"
            # (People Inc), not "IAC" - and "DMC"/"FDP" (DMC Global and Fresh Del Monte
            # Produce, two unrelated real companies) both resolved to CIK 1047340 (Del Monte
            # Corporation, an unrelated third company) - each pair then silently shared one
            # company's entire financial history in annual_income_statement (byte-for-byte
            # identical revenue for 2-4 consecutive fiscal years), the same corruption
            # signature as the WTRG/AWK 8-K bug fixed the same session (different root cause,
            # same symptom). Verify the resolved CIK's OWN submissions actually list this
            # ticker before trusting it - restores the "never fabricates" guarantee for this
            # path too. A verification failure (network error, unexpected shape) fails open
            # (returns the unverified CIK) rather than turning a slow/flaky verification call
            # into a new source of false negatives - this fallback already only runs for
            # tickers absent from the fast, authoritative bulk file, so an unverifiable-but-
            # plausible CIK is still strictly better than raising.
            if not self._verify_ticker_matches_cik(symbol, cik):
                logger.warning(
                    f"browse-edgar CIK fallback for {symbol} resolved to CIK {cik}, but that "
                    f"CIK's own SEC submissions record does not list {symbol} as one of its "
                    f"tickers - rejecting as a likely name/prefix-search mismatch, not a real "
                    f"ticker match."
                )
                return None
            return cik
        return None

    def _verify_ticker_matches_cik(self, symbol: str, cik: str) -> bool:
        """Return True unless SEC's own submissions record for `cik` positively contradicts
        `symbol` - i.e. it lists at least one ticker and `symbol` isn't among them.

        Fails open (True) on any network/parse problem or an empty/missing ticker list -
        this is a safety net against a specific known failure mode (browse-edgar's fuzzy
        name-search fallback), not a new hard dependency for every fallback resolution.
        """
        try:
            resp = self._session.get(
                f"https://data.sec.gov/submissions/CIK{cik}.json",
                timeout=self._timeout,
            )
            if resp.status_code != 200:
                return True
            tickers = resp.json().get("tickers") or []
            if not tickers:
                return True
            return symbol.upper() in {t.upper() for t in tickers}
        except (requests.ConnectionError, requests.Timeout, ValueError):
            return True

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
