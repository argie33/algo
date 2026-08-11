#!/usr/bin/env python3
"""Market Constituents Loader - S&P 500 + Russell 2000 symbol membership (Market-wide).

Consolidates:
- load_stock_symbols.py (NASDAQ/NYSE tradable symbols)
- load_sp500_constituents.py (S&P 500 membership flag)
- load_russell2000_constituents.py (Russell 2000 membership flag)

Into a single atomic transaction to eliminate fragile cron-based ordering.

Run:
    python3 load_market_constituents.py
"""

import csv
import json
import logging
import os
import re
import socket
import sys
from datetime import date
from io import StringIO
from typing import Any, cast

import pandas as pd
import requests

from loaders.runner import run_loader
from utils.db import DatabaseContext
from utils.infrastructure.url_validator import validate_url
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

NASDAQ_URL = os.getenv("NASDAQ_SYMBOLS_URL", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt")
OTHER_URL = os.getenv("OTHER_SYMBOLS_URL", "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt")
# NO FREE OFFICIAL SOURCE EXISTS for S&P 500 *index membership* - it's S&P Dow Jones
# Indices' proprietary data, not published by SEC/NASDAQ. Live-verified 2026-08-10: the
# usual "official-ish" fallback (ETF-sponsor holdings feeds, which track the index almost
# exactly) doesn't help either - iShares IVV's holdings endpoint returns an HTML
# compliance/geo-gate interstitial instead of the CSV, and SSGA's SPY holdings file 301s
# to a similar gate; both would need the same browser-spoofing this is trying to avoid,
# plus session/cookie handling on top. Wikipedia's table (community-maintained, sourced
# from S&P's own press releases) is the least-bad option - same class of accepted
# tradeoff as the NAAIM/AAII survey scrapes and yfinance analyst ratings (see
# loaders/DEPRECATED_LOADERS.md). This only sets the is_sp500 enrichment flag, not the
# base tradable universe (that's NASDAQ/OTHER above, both real official feeds).
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

# GOVERNANCE 2026-08-04: symbols the upstream NASDAQ/NYSE symbol directory's "ETF" column
# misclassifies as non-ETF (root cause of migration 069's JHDV/JVAL data patch). Without
# this override, _upsert_etf_symbols()'s TRUNCATE+rebuild silently drops them from
# etf_symbols again (and stock_symbols.etf reverts to 'N') on the very next loader run,
# undoing that migration - the loader itself must correct this every run, not a one-off
# manual DB patch. Add future confirmed upstream misclassifications here.
KNOWN_ETF_MISCLASSIFICATIONS = {"JHDV", "JVAL"}

EXCLUSION_PATTERNS = [
    r"\bpreferred\b",
    r"\bwarrant(s)?\b",
    r"\bunit(s)?\b",
    r"\bconvertible\b",
    r"\bpreferred share(s)?\b",
    r"\btest stock\b",
    r"\bfund\b",
    r"\bblank check\b",
    r"\bspac\b",
    r"\bspecial purpose\b",
    r"\betn\b",
    r"\bexchange[- ]traded note\b",
    # NOTE: Removed bare \betf\b pattern that was excluding ALL ETFs (SPY, IWM, GLD, etc.)
    # These broad-market index ETFs are tradeable instruments.  Only exclude leveraged/inverse:
    r"\b[2-9]x\b",  # Leveraged ETFs (2x, 3x, etc.) - covered separately below
    r"\binverse\b",  # Inverse ETFs - covered separately below
    r"\bnotes?\b.*\bdue\b",  # bonds/notes with maturity date
    r"\bclosed[- ]end\b",
    r"\b2x\b",
    r"\b3x\b",
    r"\binverse\b",
    # GOVERNANCE 2026-07-28: preferred/subordinated-debt securities that don't say the
    # literal word "preferred" - live-confirmed 58 already-active symbols in the local
    # DB (dual-class-looking "$"-suffix tickers like BAC$E, ALL$B, plus plain tickers
    # like AFGC/DTB/RZC) flowing through technical indicators/scoring/signals as if they
    # were common equity, none matched by the patterns above. "Preference Shares"
    # (British/insurance-industry spelling), "Subordinated Debentures"/"Subordinated
    # Notes" (junior debt, not equity), and "Pfd Ser"/"Pfd Stock" (abbreviated
    # depositary-share preferred notation) are all real, common NASDAQ/NYSE listing-file
    # phrasings this loader had never covered. Deliberately NOT a bare `\bpfd\b` - that
    # false-positived on BNS ("Bank Nova Scotia Halifax Pfd 3 Ordinary Shares"), a real,
    # actively-traded common ADR with a garbled security_name in the raw feed.
    r"\bpreference\b",
    r"\bdebenture",
    r"\bsubordinated\b",
    r"\bpfd (ser|stock)",
    # GOVERNANCE 2026-08-03: rights offerings, when-issued shares, and depositary-share
    # preferred notation that don't match any pattern above - live-confirmed 28
    # already-active symbols in the local DB (SPAC rights like AIIA.R/JENA.R, when-issued
    # like REZI.V/ADIG.V, bare "X% Series Y" preferred like DBRG$H/NLY$F, and "Depositary
    # Shares"/"Dep Shs" preferred like EQH$A/MS$F) flowing through price_daily and every
    # downstream loader as if they were common equity - this is the root cause of
    # price_daily's chronic ~4% "missing symbol" gap (yfinance has no ticker for most of
    # these instrument types at all). Verified against Bank Nova Scotia's known-tricky
    # "...Pfd 3 Ordinary Shares" and Apple/McCormick "...Common Stock" security_names to
    # confirm none of these new patterns false-positive on real common equity.
    r"\brights?\b",
    r"\bwhen-issued\b",
    r"\bdepositary shares?\b",
    r"\bdep shs?\b",
    r"\bpfd\b.{0,20}\bser\b",
    r"\d+(\.\d+)?%\s+series\s+[a-z]\b",
]

# GOVERNANCE 2026-08-03: a bare `\binvestment corp\b` pattern used to sit in
# EXCLUSION_PATTERNS above. Live-confirmed it silently excluded AGNC ("AGNC Investment
# Corp. - Common Stock", a large actively-traded mortgage REIT) and SAR ("Saratoga
# Investment Corp New", a real BDC common stock) from the entire trading universe -
# neither is a SPAC. The pattern exists to catch serial-SPAC-sponsor shell companies
# (Hennessy Capital Investment Corp. VIII, NewHold Investment Corp III/IV, Origin
# Investment Corp I, Vine Hill Capital Investment Corp. II, Bain Capital GSS Investment
# Corp.) whose base equity lines ("... Class A Ordinary Shares") aren't caught by any
# other pattern (their units/warrants/rights lines already are, via the patterns above).
# Real US operating companies list "Common Stock"; these SPACs (offshore blank-check
# vehicles) list "Ordinary Shares" instead - only exclude "investment corp" names that
# also carry that SPAC share-class language, not the bare phrase on its own. Verified
# against the full live nasdaqlisted.txt/otherlisted.txt feeds: this change flips exactly
# AGNC and SAR to included and leaves every SPAC-family row (units/warrants/rights/base
# shares) excluded, same as before.
#
# GOVERNANCE 2026-08-04: `\binvestment corp\b` alone missed the more common SPAC-sponsor
# naming convention, "... Acquisition Corp[oration]" (Abony Acquisition Corp. I, Alpex
# Acquisition Corporation, Iron Dome Acquisition I Corp., etc.) - live-confirmed 75
# already-active symbols in the local DB whose base "Class A Ordinary Share(s)" equity
# line was never excluded by any pattern (their units/rights lines already were), showing
# up as chronic "missing" gaps against price_daily since yfinance has no ticker for them.
# Same false-positive guard as above applies here: only excludes when the SPAC
# "Ordinary Shares"/"Rights" share-class language is also present, so a real operating
# company that happens to have "Acquisition Corp" in its legal name but lists "Common
# Stock" is untouched.
#
# GOVERNANCE 2026-08-04 (same day, follow-up): the pattern above required "acquisition"/
# "investment" immediately adjacent to "corp", but the most common real-world SPAC-sponsor
# convention numbers the entity BETWEEN those two words ("Acquisition I Corp", "Acquisition
# II Corp.", "M3-Brigade Acquisition V Corp.", "StoneBridge Acquisition II Corporation") -
# including the exact "Iron Dome Acquisition I Corp." example cited above, which the
# adjacency-only regex never actually matched. Live-confirmed 2026-08-04: 16 already-active
# symbols in the local DB (APAC, DBCA, DMII, IDAC, LCCC, MBVI, NCO, PACH, MBAV, AESP, TVA,
# TVIV, VLOS, ARCL, MCAH, BCAR among them) still slipping through - all real, currently
# yfinance-quotable pre-merger SPAC units trading near their ~$10 trust value, not
# no-data symbols, so they were silently inflating the tradable universe with shells that
# provide no real operating signal rather than showing up as a data gap. Allow an optional
# short numbering token (roman numeral, plain digit, or ordinal like "1st") between the
# sponsor word and "corp" - bounded to avoid matching arbitrary intervening company-name
# words. No "Corp <numeral>" (numeral-after-corp) ordering found in current live data;
# add that ordering here too if a future audit finds one.
CORP_SPONSOR_PATTERN = re.compile(
    r"\b(investment|acquisition)\s+(?:[ivxlcdm]+|\d+(?:st|nd|rd|th)?)?\s*corp(oration)?\b",
    re.IGNORECASE,
)
SPAC_SHARE_CLASS_PATTERN = re.compile(r"\bordinary share(s)?\b|\brights?\b", re.IGNORECASE)


def should_exclude(name: str) -> bool:
    if any(re.search(p, name, flags=re.IGNORECASE) for p in EXCLUSION_PATTERNS):
        return True
    if CORP_SPONSOR_PATTERN.search(name) and SPAC_SHARE_CLASS_PATTERN.search(name):
        return True
    return False


class MarketConstituentsLoader(OptimalLoader):
    """Load all tradable symbols and mark S&P 500 / Russell 2000 membership."""

    table_name = "stock_symbols"
    primary_key = ("symbol",)
    watermark_field = "created_at"

    def _deactivate_stale_excluded_symbols(self) -> None:
        """Re-apply should_exclude() to already-`active=true` rows and flip any new matches.

        GOVERNANCE 2026-08-04: excluded symbols are simply omitted from the `rows` list
        fetch_global() returns, so the bulk-insert write path below never touches them -
        a symbol that was `active=true` under an OLDER, looser EXCLUSION_PATTERNS/
        CORP_SPONSOR_PATTERN stays `active=true` forever, even after a pattern tightens to
        newly cover it. Live-confirmed: the 2026-08-03 `\\brights?\\b` pattern addition left
        59 already-active SPAC-rights symbols (AACPR, AESPR, ...) untouched, silently
        inflating price_daily's "active universe" denominator and pinning its completion %
        below the 98% mark_completed() safety threshold every single day since - the
        dashboard's Data Freshness table showed price_daily as chronically FAILED for a
        reason with nothing to do with the price loader itself. This reconciles existing
        rows against the CURRENT patterns on every run, using each row's own stored
        security_name (no need to re-fetch anything).
        """
        with DatabaseContext("read") as cur:
            cur.execute("SELECT symbol, security_name FROM stock_symbols WHERE active = true")
            active_rows = cur.fetchall()

        stale = [symbol for symbol, name in active_rows if name and should_exclude(name)]
        if not stale:
            return

        logger.warning(
            f"[MARKET_CONSTITUENTS] Deactivating {len(stale)} already-active symbol(s) that now "
            f"match should_exclude() under current patterns: {stale[:10]}"
            + (f" ...and {len(stale) - 10} more" if len(stale) > 10 else "")
        )
        with DatabaseContext("write") as cur:
            cur.execute(
                """
                UPDATE stock_symbols
                SET active = false, data_unavailable = true,
                    data_unavailable_reason = 'excluded_by_naming_pattern'
                WHERE symbol = ANY(%s)
                """,
                (stale,),
            )

    def fetch_global(self, since: date | None) -> list[dict[str, Any]]:
        """Fetch all symbols and mark index membership.

        ATOMIC OPERATION:
        1. Fetch NASDAQ/NYSE symbols (primary dataset)
        2. Fetch S&P 500 constituents (enrichment)
        3. Fetch Russell 2000 constituents (enrichment)
        4. Return combined dataset with flags

        This eliminates the fragile cron-based ordering where sp500 and russell
        loaders depend on stock_symbols running first.
        """
        socket.setdefaulttimeout(15.0)

        try:
            self._deactivate_stale_excluded_symbols()

            # STEP 1: Fetch NASDAQ/NYSE symbols
            logger.info("STEP 1/3: Fetching NASDAQ/NYSE tradable symbols")
            base_symbols = self._fetch_nasdaq_symbols()

            if not base_symbols:
                raise RuntimeError(
                    "[MARKET_CONSTITUENTS] No tradable symbols fetched from NASDAQ/NYSE. "
                    "Cannot load market constituents without base symbol list."
                )

            logger.info(f"Fetched {len(base_symbols)} base symbols from NASDAQ/NYSE")

            # STEP 2: Fetch and index S&P 500 constituents (critical enrichment for signal generation)
            logger.info("STEP 2/3: Fetching S&P 500 constituents")
            sp500_set = set()
            sp500_fetch_failed = False
            try:
                sp500_symbols = self._fetch_sp500_symbols()
                if sp500_symbols:
                    sp500_set = set(sp500_symbols)
                    logger.info(f"Fetched {len(sp500_set)} S&P 500 constituents")
                else:
                    logger.critical(
                        "[MARKET_CONSTITUENTS] S&P 500 fetch returned 0 symbols. "
                        "This indicates a data source issue (Wikipedia unavailable or format changed). "
                        "Marking S&P 500 enrichment as failed to alert operator."
                    )
                    sp500_fetch_failed = True
            except Exception as e:
                logger.critical(
                    f"[MARKET_CONSTITUENTS] Failed to fetch S&P 500: {type(e).__name__}: {e}. "
                    f"Cannot enrich market constituents with S&P 500 membership. "
                    f"Data source issue or network timeout - check Wikipedia/data source availability."
                )
                sp500_fetch_failed = True

            # STEP 3: Fetch and index Russell 2000 constituents (optional enrichment)
            logger.info("STEP 3/3: Fetching Russell 2000 constituents")
            russell_set = set()
            try:
                russell_symbols = self._fetch_russell2000_symbols()
                if russell_symbols:
                    russell_set = set(russell_symbols)
                    logger.info(f"Fetched {len(russell_set)} Russell 2000 constituents")
                else:
                    logger.warning(
                        "[MARKET_CONSTITUENTS] Russell 2000 fetch returned 0 symbols. "
                        "This is optional enrichment data - continuing without it."
                    )
            except Exception as e:
                logger.warning(
                    f"[MARKET_CONSTITUENTS] Failed to fetch Russell 2000 ({type(e).__name__}: {e}). "
                    f"This is optional enrichment - continuing without it."
                )

            # CRITICAL: Fail if S&P 500 fetch failed - this is essential enrichment
            if sp500_fetch_failed:
                raise RuntimeError(
                    "[MARKET_CONSTITUENTS] S&P 500 constituent fetch failed and returned 0 symbols. "
                    "Cannot proceed with incomplete enrichment. This indicates a data source issue. "
                    "OPERATOR ACTION: Check if Wikipedia is accessible and not blocked. "
                    "The loader requires S&P 500 data to properly enrich market constituents."
                )

            # Enrich base symbols with index membership flags
            enriched_count = 0
            for i, row in enumerate(base_symbols):
                if "symbol" not in row or not row.get("symbol"):
                    raise ValueError(
                        f"CRITICAL: Market constituent row {i} missing required 'symbol' field. "
                        f"Cannot determine index membership without symbol. Row: {row}"
                    )
                sym = row["symbol"]
                row["is_sp500"] = sym in sp500_set
                row["is_russell2000"] = sym in russell_set
                enriched_count += 1

            # Validate enrichment completed for all rows
            if enriched_count < len(base_symbols):
                raise RuntimeError(
                    f"CRITICAL: Enrichment incomplete. "
                    f"Processed {enriched_count}/{len(base_symbols)} symbols. "
                    "Cannot proceed with partial index membership data."
                )

            # Verify all rows were enriched with flags
            missing_flags = [i for i, r in enumerate(base_symbols) if "is_sp500" not in r or "is_russell2000" not in r]
            if missing_flags:
                raise RuntimeError(
                    f"CRITICAL: Enrichment validation failed. "
                    f"Rows {missing_flags} missing index membership flags. "
                    "Cannot proceed with incomplete enrichment."
                )

            sp500_count = sum(1 for r in base_symbols if r.get("is_sp500"))
            russell_count = sum(1 for r in base_symbols if r.get("is_russell2000"))

            logger.info(
                f"Enriched {len(base_symbols)} symbols with index membership. "
                f"S&P 500: {sp500_count} "
                f"Russell 2000: {russell_count}"
            )

            # Add data availability markers (successful load)
            for row in base_symbols:
                row["data_unavailable"] = False
                row["data_unavailable_reason"] = None

            return base_symbols

        except (requests.RequestException, requests.Timeout, json.JSONDecodeError) as e:
            raise RuntimeError(f"[MARKET_CONSTITUENTS] Failed to fetch constituent data: {e}") from e

    def _fetch_nasdaq_symbols(self) -> list[dict[str, Any]]:  # noqa: C901
        # Validate URLs
        for url, url_name in [
            (NASDAQ_URL, "NASDAQ_SYMBOLS_URL"),
            (OTHER_URL, "OTHER_SYMBOLS_URL"),
        ]:
            is_valid, error_msg = validate_url(url, allowed_domains=["nasdaqtrader.com"])
            if not is_valid:
                raise RuntimeError(
                    f"[MARKET_CONSTITUENTS] SSRF validation failed for {url_name}: {error_msg}. "
                    "Cannot fetch tradable symbols without valid data source."
                )

        try:
            logger.debug("Downloading NASDAQ list")
            try:
                nas_text = requests.get(NASDAQ_URL, timeout=15).text
            except requests.exceptions.Timeout as e:
                raise RuntimeError(
                    f"[MARKET_CONSTITUENTS] NASDAQ symbols fetch timeout ({NASDAQ_URL}). "
                    "nasdaqtrader.com is unreachable or slow."
                ) from e

            logger.debug("Downloading OTHER list")
            try:
                oth_text = requests.get(OTHER_URL, timeout=15).text
            except requests.exceptions.Timeout as e:
                raise RuntimeError(
                    f"[MARKET_CONSTITUENTS] Other symbols fetch timeout ({OTHER_URL}). "
                    "nasdaqtrader.com is unreachable or slow."
                ) from e

            rows = []
            etf_rows = []
            seen_symbols: set[str] = set()

            # BUGFIX 2026-07-20: nasdaqlisted.txt and otherlisted.txt use DIFFERENT column
            # schemas (confirmed live against both feeds). nasdaqlisted.txt: "Symbol",
            # "Market Category" (Q/G/S), has "Financial Status". otherlisted.txt (the feed
            # for NYSE/NYSE American/NYSE Arca/BATS/IEXG-listed stocks - i.e. most non-NASDAQ
            # names): "ACT Symbol", "Exchange" (N/A/P/Z/V), NO "Financial Status" column at
            # all. The old single shared parse loop looked up "Symbol"/"Market Category"
            # unconditionally, so EVERY row of otherlisted.txt failed the "Symbol" presence
            # check and was silently skipped - meaning stock_symbols has never contained a
            # single true NYSE-listed company (AbbVie, Abbott, Alcoa, ADM, ...) via this
            # loader; only NASDAQ + the NASDAQ feed's own "NYSE MKT" rows ever landed there.
            schemas = [
                {
                    "text": nas_text,
                    "symbol_field": "Symbol",
                    "exchange_field": "Market Category",
                    "exchange_map": {"Q": "NASDAQ", "G": "NASDAQ", "S": "NYSE MKT"},
                    "has_financial_status": True,
                },
                {
                    "text": oth_text,
                    "symbol_field": "ACT Symbol",
                    "exchange_field": "Exchange",
                    "exchange_map": {"N": "NYSE", "A": "NYSE MKT", "P": "NYSE ARCA", "Z": "BATS", "V": "IEXG"},
                    "has_financial_status": False,
                },
            ]

            for schema in schemas:
                symbol_field = cast(str, schema["symbol_field"])
                exchange_field = cast(str, schema["exchange_field"])
                exchange_map = cast(dict[str, str], schema["exchange_map"])
                reader = csv.DictReader(cast(str, schema["text"]).splitlines(), delimiter="|")
                for r in reader:
                    # CRITICAL: Symbol is required - explicit validation, no defaults
                    if symbol_field not in r or not r[symbol_field]:
                        logger.warning(
                            f"[MARKET_CONSTITUENTS] Skipping row with missing or empty '{symbol_field}' field."
                        )
                        continue
                    sym = r[symbol_field].strip()
                    if sym.startswith("File Creation Time"):
                        continue
                    if sym in seen_symbols:
                        # Cross-listed on both feeds (rare) - keep the first classification.
                        continue

                    # CRITICAL: Security Name is required
                    if "Security Name" not in r:
                        raise ValueError(
                            f"[MARKET_CONSTITUENTS] Symbol {sym} missing required 'Security Name' field. "
                            "Cannot process market constituent without name."
                        )
                    name = r["Security Name"].strip()
                    if not name:
                        raise ValueError(
                            f"[MARKET_CONSTITUENTS] Symbol {sym} has empty 'Security Name' field. "
                            "Cannot process market constituent with empty name."
                        )

                    # ETFs go to separate table (not stock_symbols)
                    required_classifier_fields = ["ETF", "Test Issue"] + (
                        ["Financial Status"] if schema["has_financial_status"] else []
                    )
                    for field in required_classifier_fields:
                        if field not in r:
                            raise ValueError(
                                f"[MARKET_CONSTITUENTS] Symbol {sym} missing required field '{field}'. "
                                f"Cannot safely classify security. Available fields: {list(r.keys())}"
                            )

                    if r["ETF"].upper() == "Y" or sym in KNOWN_ETF_MISCLASSIFICATIONS:
                        etf_rows.append(
                            {
                                "symbol": sym,
                                "security_name": name,
                                "data_unavailable": False,
                                "data_unavailable_reason": None,
                            }
                        )
                        seen_symbols.add(sym)
                        continue

                    if should_exclude(name):
                        continue
                    if r["Test Issue"].upper() == "Y":
                        continue
                    # otherlisted.txt has no "Financial Status" (deficient-issuer) column -
                    # that NASDAQ-specific flag simply doesn't exist for NYSE/other listings.
                    if schema["has_financial_status"] and r["Financial Status"].strip() == "D":
                        continue
                    if "etf" in name.lower() or "fund" in name.lower():
                        logger.debug(f"Excluding {sym} ({name}) by security name pattern")
                        continue

                    if exchange_field not in r or not r[exchange_field]:
                        logger.warning(f"[MARKET_CONSTITUENTS] Symbol {sym} missing exchange field. Skipping.")
                        continue
                    exchange_code = r[exchange_field].upper().strip()
                    # FAIL-FAST: Skip symbols with unmapped exchange codes instead of using "UNKNOWN"
                    if exchange_code not in exchange_map:
                        logger.warning(
                            f"[MARKET_CONSTITUENTS] Symbol {sym} has unmapped exchange code '{exchange_code}'. "
                            f"Skipping. This indicates: (1) New exchange code from API, or (2) Data quality issue. "
                            f"Known codes: {list(exchange_map.keys())}"
                        )
                        continue
                    exchange = exchange_map[exchange_code]
                    rows.append(
                        {
                            "symbol": sym,
                            "security_name": name,
                            "exchange": exchange,
                            "etf": "N",
                        }
                    )
                    seen_symbols.add(sym)

            # Upsert ETFs to separate table
            if etf_rows:
                self._upsert_etf_symbols(etf_rows)

            if not rows:
                raise RuntimeError(
                    "[MARKET_CONSTITUENTS] No tradable symbols parsed from NASDAQ/NYSE data. "
                    "Cannot proceed with market constituent list."
                )
            return rows

        except (requests.RequestException, json.JSONDecodeError) as e:
            raise RuntimeError(
                f"[MARKET_CONSTITUENTS] Failed to fetch NASDAQ symbols: {e}. "
                "Cannot load market constituents without base symbol data."
            ) from e

    def _fetch_sp500_symbols(self) -> list[str]:
        is_valid, error_msg = validate_url(SP500_URL, allowed_domains=["wikipedia.org"])
        if not is_valid:
            raise RuntimeError(
                f"[MARKET_CONSTITUENTS] SSRF validation failed for S&P 500 URL: {error_msg}. "
                "Cannot fetch S&P 500 constituent data."
            )

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            response = requests.get(SP500_URL, headers=headers, timeout=15)
            response.raise_for_status()

            tables = pd.read_html(StringIO(response.text))
            if not tables:
                raise RuntimeError(
                    "[MARKET_CONSTITUENTS] Could not parse S&P 500 table from Wikipedia. "
                    "Cannot load S&P 500 constituent membership data."
                )

            df = tables[0]
            col = "Symbol" if "Symbol" in df.columns else "Ticker"

            if col not in df.columns:
                raise RuntimeError(
                    f"[MARKET_CONSTITUENTS] S&P 500 table missing {col} column. "
                    "Cannot extract S&P 500 constituents without symbol data."
                )

            symbols: list[str] = df[col].str.strip().tolist()
            return symbols

        except requests.exceptions.Timeout as e:
            raise RuntimeError(
                "[MARKET_CONSTITUENTS] S&P 500 fetch timeout. Wikipedia API is unreachable or slow."
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"[MARKET_CONSTITUENTS] Failed to fetch S&P 500: {e}. Cannot load S&P 500 constituent data."
            ) from e

    def _fetch_russell2000_symbols(self) -> list[str]:
        """Fetch Russell 2000 constituents from reliable source (optional enrichment).

        Returns empty list if unavailable - Russell 2000 is optional enrichment data.
        The loader continues without it rather than failing.
        """
        urls = [
            "https://www.multpl.com/russell-2000/table/by-date",
            "https://en.wikipedia.org/wiki/Russell_2000",
        ]

        for url_index, url in enumerate(urls, 1):
            is_valid, error_msg = validate_url(url, allowed_domains=["multpl.com", "wikipedia.org"])
            if not is_valid:
                logger.debug(
                    f"[MARKET_CONSTITUENTS] Russell 2000 URL validation failed ({url_index}/{len(urls)}): {error_msg}. "
                    "Attempting next source."
                )
                continue

            try:
                logger.debug(f"Attempting Russell 2000 fetch from source {url_index}/{len(urls)}: {url}")
                headers = {"User-Agent": "Mozilla/5.0"}
                response = requests.get(url, headers=headers, timeout=15)
                response.raise_for_status()

                tables = pd.read_html(StringIO(response.text))
                if not tables:
                    logger.debug(
                        f"[MARKET_CONSTITUENTS] No tables found at Russell 2000 source ({url_index}/{len(urls)}). Attempting next source."
                    )
                    continue

                for table in tables:
                    for col in ["Ticker", "Symbol", "symbol"]:
                        if col in table.columns:
                            symbols: list[str] = table[col].str.strip().tolist()
                            if symbols:
                                logger.info(
                                    f"Successfully fetched Russell 2000 data from source {url_index}/{len(urls)} using column '{col}': {len(symbols)} constituents"
                                )
                                return symbols

                logger.debug(
                    f"[MARKET_CONSTITUENTS] No valid symbol column found at source {url_index}/{len(urls)}. Attempting next source."
                )

            except requests.exceptions.Timeout as e:
                logger.debug(
                    f"[MARKET_CONSTITUENTS] Timeout fetching Russell 2000 from source {url_index}/{len(urls)}: {e}. "
                    "Attempting next source."
                )
                continue
            except Exception as e:
                logger.debug(
                    f"[MARKET_CONSTITUENTS] Failed to fetch Russell 2000 from source {url_index}/{len(urls)}: {e}. "
                    "Attempting next source."
                )
                continue

        error_msg = (
            f"[MARKET_CONSTITUENTS] Russell 2000 data unavailable from all sources ({len(urls)} attempted). "
            "Cannot load Russell 2000 constituent data without valid source."
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    def _upsert_etf_symbols(self, etf_rows: list[dict[str, Any]]) -> None:
        """Refresh ETF symbols table with explicit validation (keep separate from tradable symbols)."""
        if not etf_rows:
            logger.info("No ETF symbols to upsert (empty list)")
            return

        # Validate ETF data structure before database operation
        for i, row in enumerate(etf_rows):
            if "symbol" not in row or not row["symbol"]:
                raise ValueError(
                    f"[MARKET_CONSTITUENTS] ETF row {i} missing or empty 'symbol' field. "
                    f"Cannot upsert ETF symbol without symbol. Row: {row}"
                )
            if "security_name" not in row or not row["security_name"]:
                raise ValueError(
                    f"[MARKET_CONSTITUENTS] ETF row {i} (symbol={row['symbol']}) missing or empty 'security_name' field. "
                    f"Cannot upsert ETF symbol without name."
                )

        try:
            import psycopg2

            from utils.db.context import DatabaseContext

            with DatabaseContext("write") as cur:
                cur.execute("TRUNCATE TABLE etf_symbols")
                cur.executemany(
                    "INSERT INTO etf_symbols (symbol, security_name, data_unavailable, data_unavailable_reason) VALUES (%s, %s, %s, %s)",
                    [
                        (row["symbol"], row["security_name"], row["data_unavailable"], row["data_unavailable_reason"])
                        for row in etf_rows
                    ],
                )
            logger.info(f"Successfully refreshed etf_symbols table with {len(etf_rows)} ETF symbols")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[MARKET_CONSTITUENTS] Failed to refresh etf_symbols table with {len(etf_rows)} symbols: {e}. "
                "Cannot proceed with incomplete ETF symbol update."
            ) from e


if __name__ == "__main__":
    sys.exit(run_loader(MarketConstituentsLoader, global_mode=True))
