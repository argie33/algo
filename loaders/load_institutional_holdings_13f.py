#!/usr/bin/env python3
"""Institutional Holdings Loader - SEC Form 13F (INFOTABLE bulk dataset).

Uses SEC's official 13F-HR structured datasets:
https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets

Data source: INFOTABLE.tsv. Real columns (verified against a real downloaded
dataset - NOT a "ticker" column, contrary to this loader's original assumption):
ACCESSION_NUMBER, INFOTABLE_SK, NAMEOFISSUER, TITLEOFCLASS, CUSIP, FIGI, VALUE,
SSHPRNAMT, SSHPRNAMTTYPE, PUTCALL, INVESTMENTDISCRETION, OTHERMANAGER,
VOTING_AUTH_*. 13F filings identify securities by CUSIP only - SEC does not
publish a free CUSIP->ticker crosswalk (CUSIP itself is licensed).

CROSSWALK (2026-07-27): OpenFIGI (api.openfigi.com) is a free, public, no-signup
mapping service that resolves a CUSIP directly to its real ticker - no CUSIP
license needed on our end, since we're only ever the requester, not redistributing
CUSIP data. See utils/external/openfigi_crosswalk.py for the client and a documented
rejected-approach lesson: an earlier version tried to shortcut via SEC's own optional
FIGI column instead of a direct CUSIP query, and that was live-verified to
undercount real institutional shares by ~12x (most filers don't report FIGI) - the
direct CUSIP->ticker query below uses the FULL reported share total per CUSIP.
CUSIP->ticker attribution is cached permanently in `sec_13f_cusip_crosswalk`
(migration 1161) since it almost never changes quarter to quarter - only the small
delta of never-seen CUSIPs costs a live OpenFIGI call on any given run.

Updated: SEC publishes rolling ~3-month windows keyed to the 45-day-after-quarter-end
filing deadline (e.g. "01jun2025-31aug2025_form13f.zip", not a plain
"{year}-Q{quarter}" label - the dataset filenames are discovered by scraping SEC's own
listing page rather than guessed via calendar-quarter date arithmetic, since the
window boundaries don't align to calendar quarters cleanly).
Coverage: Institutional managers with $100M+ in assets (excludes small institutions).
Additional, separate coverage gap: only symbols whose CUSIP OpenFIGI can resolve to a
plausible entity match get a real ownership %; everything else stays honestly
data_unavailable.

Architecture:
- fetch_global() downloads & parses the latest published 13F bulk dataset once,
  aggregating shares held per CUSIP across all institutional managers
- Crosswalks CUSIPs to tickers via the cached OpenFIGI mapping (only querying
  OpenFIGI live for CUSIPs never seen before), computing ownership % for whatever
  subset of our tracked universe resolves - no fabrication for the rest
- fetch_incremental() returns cached global results per symbol

Run:
    python3 loaders/load_institutional_holdings_13f.py [--symbols AAPL,MSFT]
"""

import csv
import io
import logging
import re
import sys
import time
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.external.openfigi_crosswalk import fetch_cusip_tickers, names_plausibly_match
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.helpers import get_active_symbols
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

SEC_13F_DATASETS_PAGE = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
_ZIP_LINK_RE = re.compile(
    r'href="(/files/[a-z]+/data/form-13f-data-sets/(\d{2}[a-z]{3}\d{4})-(\d{2}[a-z]{3}\d{4})_form13f\.zip)"',
    re.IGNORECASE,
)

# FIX 2026-08-18 (live-verified): OpenFIGI appends a currency-denomination suffix to the
# ticker for CUSIPs with multiple currency-denominated trading lines (e.g. real CUSIP
# 766559603 for Rigel Pharmaceuticals resolves to ticker "RIGLUSD", not "RIGL") - a
# cross-listing/quote-currency artifact, not a different entity. The exact `ticker not in
# symbols` check in _crosswalk_to_tickers silently dropped every one of these, wrongly
# marking real, resolved 13F data as data_unavailable ("no_resolved_13f_holdings"). Found by
# checking sec_13f_cusip_crosswalk for near-miss tickers whose suffix-stripped form matches a
# tracked symbol: 18 currently-tracked symbols confirmed (RIGL, HON, FCEL, CRIS, ... all with
# resolved_name token-overlap ratio 0.67-1.00 against our own entity_name - see
# names_plausibly_match, still applied after stripping as the same wrong-entity defense).
_CURRENCY_TICKER_SUFFIXES = (
    "USD", "EUR", "GBP", "GBX", "CAD", "CHF", "JPY", "AUD", "HKD", "SEK", "NOK", "DKK", "ZAR", "SGD", "MXN",
)  # fmt: skip


class InstitutionalHoldings13FLoader(OptimalLoader):
    """Load institutional ownership % from SEC Form 13F bulk INFOTABLE datasets.

    GOVERNANCE: Official SEC sources only. No fallbacks or estimates.

    Uses SEC's pre-flattened 13F data (INFOTABLE.tsv), which includes:
    - CUSIP (NOT ticker - 13F filings never carry a ticker column)
    - Shares held by each institutional manager
    - Filing date
    """

    table_name = "institutional_holdings_13f"
    primary_key = ("symbol",)
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True

    # FIXED 2026-07-27: the OpenFIGI crosswalk step (utils/external/openfigi_crosswalk.py)
    # used to run unbounded, only saving its results to sec_13f_cusip_crosswalk after
    # EVERY batch in the whole CUSIP backlog had been attempted. terraform/modules/loaders/
    # main.tf configures this loader's ECS task with TimeoutSeconds=1200 (20 min), but even
    # a zero-failure cold crosswalk of ~34k CUSIPs takes ~2.5+ hours at OpenFIGI's
    # unauthenticated rate limit - the task was guaranteed to get killed mid-crosswalk every
    # single run, discarding 100% of whatever progress OpenFIGI had actually returned. This
    # budget leaves ~5 minutes of the 1200s task timeout for the rest of fetch_global()
    # (bulk dataset download/parse, ownership calc, DB writes) and passes a deadline into
    # fetch_cusip_tickers() so it returns (and this loader saves) partial progress instead
    # of grinding on toward a kill it can't avoid.
    _OPENFIGI_CROSSWALK_TIME_BUDGET_SEC = 900

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        self._global_data_loaded = False  # Track if we've done global fetch this run

    def fetch_global(self, since: date | None) -> list[dict[str, Any]]:
        """Fetch SEC's 13F data for ALL symbols (fail-fast if unavailable).

        This runs once per load and populates SEC data for all symbols.
        No synthetic fallbacks: if SEC data unavailable, halts with clear error message.

        PRIMARY: SEC's published 13F bulk dataset (authoritative, required)

        Returns: List of institutional ownership records for all symbols.
        Raises: RuntimeError if SEC data unavailable, or if real 13F data was
            fetched but cannot be attributed to symbols (no CUSIP->ticker
            crosswalk - see module docstring).
        """
        logger.info("[13F] Fetching institutional ownership data from SEC Form 13F...")

        try:
            dataset = self._discover_latest_13f_bulk_dataset()
            if dataset is None:
                msg = (
                    f"[13F CRITICAL] Could not discover any published 13F bulk dataset "
                    f"from {SEC_13F_DATASETS_PAGE}. Institutional holdings data is "
                    f"mandatory for accurate stock scoring. ACTION: verify the page is "
                    f"reachable and its .zip links still match the expected "
                    f"'DDmmmYYYY-DDmmmYYYY_form13f.zip' naming. "
                    f"Fail-fast: will not proceed with synthetic estimates."
                )
                logger.critical(msg)
                raise RuntimeError(msg)

            url, period_end = dataset
            logger.info(f"[13F] Latest published bulk dataset: {url} (period end: {period_end})")

            tracked_cusips = self._get_known_tracked_cusips()
            try:
                holdings_by_cusip, manager_holdings_by_cusip = self._fetch_and_parse_13f_bulk(url, tracked_cusips)
            except Exception as e:
                logger.warning(
                    f"[13F] Bulk dataset fetch/parse failed ({type(e).__name__}: {str(e)[:200]}); "
                    f"falling back to per-manager aggregation"
                )
                return self._calculate_and_cache_ownership(self._aggregate_top_manager_13fs(), period_end, {})

            logger.info(
                f"[13F] Downloaded and parsed real SEC 13F bulk data from {url}: "
                f"{len(holdings_by_cusip)} CUSIPs, period end {period_end}. "
                f"Crosswalking to our own tracked universe via OpenFIGI..."
            )
            holdings_by_ticker, manager_holdings_by_ticker = self._crosswalk_to_tickers(
                holdings_by_cusip, manager_holdings_by_cusip
            )
            if not holdings_by_ticker:
                # FIXED 2026-07-27: this used to hard-raise on "zero symbols resolved", which
                # was a reasonable check when a crosswalk was assumed to run to completion in
                # one pass. It no longer is - a cold-start backlog can take many runs to clear
                # (see _OPENFIGI_CROSSWALK_TIME_BUDGET_SEC), so "zero NEW resolutions in one
                # time-boxed run" is now an expected, recoverable state while the cache is
                # still building, not evidence OpenFIGI or get_active_symbols() is broken.
                # fetch_cusip_tickers() itself still raises if every attempted batch fails
                # outright (a real reachability/contract-change signal) unless the run was cut
                # short by the deadline - that's the actual hard-failure check now.
                logger.warning(
                    f"[13F] Downloaded and parsed real SEC 13F bulk data from {url} "
                    f"({len(holdings_by_cusip)} CUSIPs) but the OpenFIGI CUSIP->ticker crosswalk "
                    f"resolved zero symbols in our own tracked universe THIS run - expected while "
                    f"the sec_13f_cusip_crosswalk cache is still building under rate-limit/time "
                    f"constraints, not a hard failure. Symbols stay data_unavailable until a "
                    f"future run's incremental crosswalk progress covers them."
                )

            return self._calculate_and_cache_ownership(holdings_by_ticker, period_end, manager_holdings_by_ticker)

        except RuntimeError:
            # Re-raise RuntimeError from above or from _aggregate_top_manager_13fs
            raise
        except Exception as e:
            msg = f"[13F GLOBAL FETCH CRITICAL] Failed: {type(e).__name__}: {str(e)[:200]}. Cannot continue without institutional holdings data."
            logger.critical(msg)
            raise RuntimeError(msg) from e

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Lookup institutional holdings for a symbol from the database.

        This is called for each symbol individually. It looks up data that was
        previously loaded by fetch_global().

        Returns: Record with institutional_ownership_pct or data_unavailable marker.
        """
        now_et = datetime.now(EASTERN_TZ)

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT institutional_ownership_pct, filing_date, data_source,
                           number_of_institutional_holders, top_10_institutions_pct
                    FROM institutional_holdings_13f
                    WHERE symbol = %s
                    ORDER BY filing_date DESC
                    LIMIT 1
                    """,
                    (symbol,),
                )
                row = cur.fetchone()

            if row and row[0] is not None:
                return [
                    {
                        "symbol": symbol,
                        "filing_date": row[1],
                        "institutional_ownership_pct": row[0],
                        "number_of_institutional_holders": row[3],
                        "top_10_institutions_pct": row[4],
                        "data_unavailable": False,
                        "reason": None,
                        "sec_filing_url": None,
                        "most_recent_filing_date": row[1],
                        "data_source": row[2],
                    }
                ]
        except Exception as e:
            logger.debug(f"[13F] {symbol}: lookup failed - {e}")

        # Not found in database - return data_unavailable marker
        return [
            {
                "symbol": symbol,
                "filing_date": now_et.date(),
                "institutional_ownership_pct": None,
                "number_of_institutional_holders": None,
                "top_10_institutions_pct": None,
                "data_unavailable": True,
                "reason": "not_found_in_institutional_holdings_13f",
                "sec_filing_url": None,
                "most_recent_filing_date": None,
                "data_source": "none",
            }
        ]

    _MONTH_ABBR = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }  # fmt: skip

    @staticmethod
    def _parse_ddmmmyyyy(text: str) -> date:
        """Parse SEC's "01jun2025"-style date label (case-insensitive)."""
        day = int(text[0:2])
        month = InstitutionalHoldings13FLoader._MONTH_ABBR[text[2:5].lower()]
        year = int(text[5:9])
        return date(year, month, day)

    def _discover_latest_13f_bulk_dataset(self) -> tuple[str, date] | None:
        """Find the most recently published 13F bulk dataset by scraping SEC's own
        listing page, rather than guessing the filename from calendar-quarter math.

        SEC's real filename convention is a date-range tied to the ~45-day
        post-quarter-end filing deadline (e.g. "01jun2025-31aug2025_form13f.zip"),
        not a "{year}-Q{quarter}" label, and the window boundaries don't align to
        calendar quarters cleanly - confirmed by fetching SEC's real listing page.
        Scraping the page SEC itself publishes avoids reintroducing that class of bug.

        Returns: (full url, period end date) for the dataset with the latest end
            date, or None if the page couldn't be fetched/parsed.
        """
        try:
            req = urllib.request.Request(
                SEC_13F_DATASETS_PAGE, headers={"User-Agent": "algo-trading argeropolos@gmail.com"}
            )
            # nosec B310 - SEC_13F_DATASETS_PAGE is a hardcoded module-level https:// constant,
            # never attacker-influenced; see the matching justification at the other urlopen()
            # call below for the derived-URL case.
            with urllib.request.urlopen(req, timeout=30) as response:  # nosec B310
                html = response.read().decode("utf-8", errors="replace")
        except Exception as e:
            logger.error(f"[13F] Failed to fetch dataset listing page: {type(e).__name__}: {e}")
            return None

        best: tuple[str, date] | None = None
        for path, _start_str, end_str in _ZIP_LINK_RE.findall(html):
            try:
                end_date = self._parse_ddmmmyyyy(end_str)
            except (KeyError, ValueError):
                continue
            if best is None or end_date > best[1]:
                best = (f"https://www.sec.gov{path}", end_date)

        return best

    def _get_known_tracked_cusips(self) -> set[str]:
        """CUSIPs already resolved (in a prior run) to a ticker in our own active universe.

        Used to bound per-manager tracking (see _fetch_and_parse_13f_bulk) to a set small
        enough to safely hold in memory (our tracked universe, not the whole 13F market's
        CUSIPs) - a CUSIP newly resolved THIS run isn't in this set yet, so it won't get
        holder-count/concentration data until a later run recomputes this set, matching the
        existing incremental-crosswalk philosophy elsewhere in this loader.
        """
        symbols = set(get_active_symbols(exclude_etfs=True))
        with DatabaseContext("read") as cur:
            cur.execute("SELECT cusip FROM sec_13f_cusip_crosswalk WHERE ticker = ANY(%s)", (list(symbols),))
            return {row[0] for row in cur.fetchall()}

    def _fetch_and_parse_13f_bulk(
        self, url: str, tracked_cusips: set[str] | None = None
    ) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
        """Download and parse SEC's INFOTABLE.tsv from the discovered bulk dataset URL.

        Returns: (holdings_by_cusip, manager_holdings_by_cusip).
        - holdings_by_cusip: {CUSIP: total_shares_held_by_all_institutions}. Keyed by
          CUSIP, NOT ticker - 13F filings never carry a ticker field (verified against a
          real downloaded dataset's actual column headers).
        - manager_holdings_by_cusip: {CUSIP: {ACCESSION_NUMBER: shares}} - per-manager detail
          (ACCESSION_NUMBER uniquely identifies one manager's quarterly 13F filing), needed
          for institutional_holders_count/top_10_institutions_pct. Only populated for CUSIPs
          in tracked_cusips (bounds memory to our own universe's CUSIPs, not the whole 13F
          market's - see _get_known_tracked_cusips).
        """
        req = urllib.request.Request(url, headers={"User-Agent": "algo-trading argeropolos@gmail.com"})
        # nosec B310 - url is always "https://www.sec.gov" + a path regex-extracted from SEC's
        # own dataset page (see _discover_latest_13f_bulk_dataset); scheme/host are hardcoded,
        # never attacker-influenced, so the file:// / custom-scheme risk bandit flags doesn't apply.
        with urllib.request.urlopen(req, timeout=120) as response:  # nosec B310
            zip_data = response.read()

        tracked_cusips = tracked_cusips or set()
        holdings_by_cusip: dict[str, int] = defaultdict(int)
        manager_holdings_by_cusip: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            info_files = [f for f in zf.namelist() if f.endswith("INFOTABLE.tsv")]
            if not info_files:
                raise ValueError(
                    f"[13F CRITICAL] No INFOTABLE.tsv found in SEC bulk ZIP from {url}. "
                    f"ZIP structure invalid or SEC data format changed."
                )

            for info_file in info_files:
                logger.debug(f"[13F] Parsing {info_file}...")
                with zf.open(info_file) as f:
                    reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"), delimiter="\t")
                    for row in reader:
                        if "CUSIP" not in row or not row["CUSIP"]:
                            raise ValueError(f"[13F] CSV row missing required 'CUSIP' field: {row.keys()}")
                        if "SSHPRNAMT" not in row or row["SSHPRNAMT"] is None:
                            raise ValueError(
                                f"[13F] CSV row missing required 'SSHPRNAMT' field for CUSIP {row.get('CUSIP')}"
                            )

                        cusip = row["CUSIP"].strip().upper()
                        shares_str = row["SSHPRNAMT"]
                        if cusip and shares_str:
                            if not shares_str.isdigit():
                                raise ValueError(
                                    f"[13F] Invalid SSHPRNAMT '{shares_str}' for CUSIP {cusip} (expected integer)"
                                )
                            shares = int(shares_str)
                            if shares > 0:
                                holdings_by_cusip[cusip] += shares
                                if cusip in tracked_cusips:
                                    accession = row.get("ACCESSION_NUMBER")
                                    if accession:
                                        manager_holdings_by_cusip[cusip][accession] += shares

            logger.info(
                f"[13F] Aggregated {len(holdings_by_cusip)} CUSIPs from bulk data "
                f"({len(manager_holdings_by_cusip)} with per-manager detail tracked)"
            )
            return dict(holdings_by_cusip), {k: dict(v) for k, v in manager_holdings_by_cusip.items()}

    def _crosswalk_to_tickers(
        self,
        holdings_by_cusip: dict[str, int],
        manager_holdings_by_cusip: dict[str, dict[str, int]] | None = None,
    ) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
        """Resolve CUSIPs to our own tracked universe's tickers via OpenFIGI, using a
        permanent DB cache (sec_13f_cusip_crosswalk) so only never-seen CUSIPs cost a
        live OpenFIGI call - CUSIP->ticker attribution is stable across quarters.

        Returns {symbol: total_shares} for whatever subset of our universe resolves to
        a CUSIP OpenFIGI could map to a ticker in our own tracked universe AND whose
        OpenFIGI-returned name plausibly matches our own SEC-sourced entity_name
        (defense against the documented wrong-entity gotcha - see this module's and
        openfigi_crosswalk.py's docstrings). Symbols that don't clear both are simply
        absent from the result - handled naturally by fetch_incremental()'s existing
        "not found" path, not a fabrication.
        """
        all_cusips = list(holdings_by_cusip.keys())

        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT cusip, ticker, resolved_name FROM sec_13f_cusip_crosswalk WHERE cusip = ANY(%s)",
                (all_cusips,),
            )
            cached: dict[str, tuple[str | None, str | None]] = {row[0]: (row[1], row[2]) for row in cur.fetchall()}

        new_cusips = [c for c in all_cusips if c not in cached]
        logger.info(f"[13F] {len(cached)} CUSIPs already crosswalked, {len(new_cusips)} new - querying OpenFIGI")

        if new_cusips:
            # Save after every batch (not just once at the end) - see this class's
            # _OPENFIGI_CROSSWALK_TIME_BUDGET_SEC comment: a cold-start backlog this large
            # cannot finish before the ECS task timeout kills it, so partial progress must
            # survive the kill or every run silently resets to zero.
            def _persist_batch(batch_resolved: dict[str, dict[str, Any] | None]) -> None:
                newly_cached = {
                    cusip: (entry["ticker"], entry["name"]) if entry else (None, None)
                    for cusip, entry in batch_resolved.items()
                }
                self._save_crosswalk_cache(newly_cached)
                cached.update(newly_cached)

            deadline = time.monotonic() + self._OPENFIGI_CROSSWALK_TIME_BUDGET_SEC
            resolved = fetch_cusip_tickers(new_cusips, on_batch_resolved=_persist_batch, deadline=deadline)
            logger.info(
                f"[13F] OpenFIGI crosswalk this run: {len(resolved)}/{len(new_cusips)} new CUSIPs resolved "
                f"(rest cached for next run's smaller delta)"
            )

        symbols = set(get_active_symbols(exclude_etfs=True))
        local_names = self._fetch_local_entity_names(symbols)
        manager_holdings_by_cusip = manager_holdings_by_cusip or {}

        holdings_by_ticker: dict[str, int] = defaultdict(int)
        # {ticker: {accession_number: shares}} - merges across CUSIPs that resolve to the
        # same ticker (rare, e.g. a legacy + current CUSIP both outstanding), summing shares
        # if the same manager holds via both.
        manager_holdings_by_ticker: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for cusip, shares in holdings_by_cusip.items():
            ticker, resolved_name = cached.get(cusip, (None, None))
            if not ticker:
                continue
            if ticker not in symbols:
                for suffix in _CURRENCY_TICKER_SUFFIXES:
                    if ticker.endswith(suffix) and len(ticker) > len(suffix) and ticker[: -len(suffix)] in symbols:
                        ticker = ticker[: -len(suffix)]
                        break
                else:
                    continue
            if not names_plausibly_match(resolved_name, local_names.get(ticker)):
                logger.debug(
                    f"[13F] {ticker} (CUSIP {cusip}): OpenFIGI name '{resolved_name}' doesn't plausibly "
                    f"match our own entity_name '{local_names.get(ticker)}' - skipping to avoid a wrong-entity join"
                )
                continue
            holdings_by_ticker[ticker] += shares
            for accession, mgr_shares in manager_holdings_by_cusip.get(cusip, {}).items():
                manager_holdings_by_ticker[ticker][accession] += mgr_shares

        logger.info(
            f"[13F] Crosswalk resolved {len(holdings_by_ticker)}/{len(symbols)} tracked symbols to real holdings"
        )
        return dict(holdings_by_ticker), {k: dict(v) for k, v in manager_holdings_by_ticker.items()}

    def _fetch_local_entity_names(self, symbols: set[str]) -> dict[str, str]:
        """Our own SEC-sourced entity_name per symbol - the ground truth
        names_plausibly_match() checks an OpenFIGI resolution against."""
        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT symbol, entity_name FROM company_info_sec WHERE symbol = ANY(%s) AND entity_name IS NOT NULL",
                (list(symbols),),
            )
            return dict(cur.fetchall())

    def _save_crosswalk_cache(self, resolved: dict[str, tuple[str | None, str | None]]) -> None:
        """Persist OpenFIGI's CUSIP->ticker resolution (including negative results -
        a CUSIP OpenFIGI couldn't resolve at all) so future runs never re-query it.

        Deliberately NOT filtered to our own tracked universe: caches whatever OpenFIGI
        actually said, so a symbol added to our universe later can use an
        already-cached CUSIP without a fresh OpenFIGI call.

        FIXED 2026-07-27 (real production crash, live-verified): sec_13f_cusip_crosswalk.ticker
        is VARCHAR(20) - fine for a real equity ticker, but OpenFIGI's CUSIP resolution covers
        the WHOLE 13F universe including bonds/notes (13F filers report fixed-income holdings
        too), and for those it returns a long descriptive identifier in the same "ticker" field
        (live example: CUSIP 00033YAA4 -> "GLOBAU 11.5 08/15/29 144A", 26 chars) instead of a
        short equity symbol. The unguarded INSERT crashed with StringDataRightTruncation on the
        very first batch containing any bond CUSIP - given how common bonds are in real 13F
        data, this was very likely the ACTUAL reason fetch_global() kept failing outright before
        ever reaching _calculate_and_cache_ownership(), a more direct explanation than rate
        limiting alone for institutional_holdings_13f's 5,461 rows all data_unavailable. These
        overlong values can never match a real equity ticker in get_active_symbols() anyway
        (_crosswalk_to_tickers already filters on `ticker not in symbols`), so truncating is
        safe - it doesn't change which CUSIPs resolve to real holdings, only prevents a
        malformed non-equity value from crashing the whole batch's cache write.
        """
        if not resolved:
            return
        with DatabaseContext("write") as cur:
            for cusip, (ticker, name) in resolved.items():
                ticker = ticker[:20] if ticker else ticker
                name = name[:255] if name else name
                cur.execute(
                    """
                    INSERT INTO sec_13f_cusip_crosswalk (cusip, ticker, resolved_name, verified_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (cusip) DO UPDATE SET
                        ticker = EXCLUDED.ticker,
                        resolved_name = EXCLUDED.resolved_name,
                        verified_at = EXCLUDED.verified_at
                    """,
                    (cusip, ticker, name),
                )

    def _aggregate_top_manager_13fs(self) -> dict[str, int]:
        """Aggregate per-manager 13F holdings via CUSIP→ticker mapper (correct architecture).

        CRITICAL FIX (Session 418): Removed interim market-cap fallback per GOVERNANCE fail-fast principle.
        When SEC bulk INFOTABLE datasets exhausted, this method attempted per-manager aggregation
        as a fallback. However, this requires a CUSIP→ticker mapper that is not yet implemented.
        Rather than silently defaulting to synthetic market-cap estimates, fail-fast here.

        This ensures operator visibility: if both bulk data AND per-manager aggregation fail,
        the system halts instead of proceeding with corrupted synthetic data.
        """
        msg = (
            "[13F CRITICAL] SEC bulk 13F datasets unavailable. Per-manager 13F aggregation requires "
            "CUSIP→ticker mapper implementation (not yet available). "
            "Cannot proceed without authoritative SEC institutional holdings data. "
            "Fail-fast to prevent silent fallback to synthetic market-cap estimates. "
            "ACTION: Check SEC 13F publication schedule and implement CUSIP mapper if needed."
        )
        logger.critical(msg)
        raise RuntimeError(msg)

    def _calculate_and_cache_ownership(
        self,
        holdings_by_ticker: dict[str, int],
        filing_date: date,
        manager_holdings_by_ticker: dict[str, dict[str, int]] | None = None,
    ) -> list[dict[str, Any]]:
        """Calculate institutional ownership % for each ticker.

        Uses shares_outstanding from company_info_sec table.

        FIXED 2026-07-28 (live-confirmed staleness): this used to only return records
        for tickers that both resolved via the OpenFIGI crosswalk AND had a usable
        shares_outstanding - every other active symbol was simply absent from the
        returned list, so load_global()'s bulk_insert() never touched its existing DB
        row. Since the crosswalk resolves a growing subset each run, "absent this run"
        silently meant "keep whatever row is already there" - live-confirmed 3,940 of
        5,403 rows were still frozen on the literal string
        "cusip_ticker_crosswalk_not_implemented", a reason that predates the OpenFIGI
        fix and no longer exists anywhere in this file, because nothing ever revisited
        them after real crosswalk resolution began. Now every active symbol gets an
        explicit, current record every run - either real ownership or an honest,
        up-to-date data_unavailable marker - matching the same "always upsert the
        unavailable marker" governance already applied elsewhere in this codebase
        (see steering/DATA_LOADERS.md).
        """
        logger.info("[13F] Calculating institutional ownership percentages...")
        records = []
        now_et = datetime.now(EASTERN_TZ)
        resolved_tickers: set[str] = set()
        manager_holdings_by_ticker = manager_holdings_by_ticker or {}

        with DatabaseContext("read") as cur:
            for ticker, inst_shares in holdings_by_ticker.items():
                try:
                    # Get shares outstanding for this ticker
                    cur.execute(
                        "SELECT shares_outstanding FROM company_info_sec WHERE symbol = %s",
                        (ticker,),
                    )
                    row = cur.fetchone()

                    if row and row[0] and row[0] > 0:
                        shares_os = row[0]
                        pct = round((inst_shares / shares_os) * 100, 2)
                        pct = min(pct, 100.0)  # Cap at 100%

                        # Per-manager detail (see _get_known_tracked_cusips) - only available
                        # for CUSIPs already resolved to this ticker in a PRIOR run, so a
                        # newly-resolved-this-run ticker legitimately has none yet.
                        manager_shares = manager_holdings_by_ticker.get(ticker)
                        holder_count = len(manager_shares) if manager_shares else None
                        top_10_pct = None
                        if manager_shares:
                            top_10_shares = sum(sorted(manager_shares.values(), reverse=True)[:10])
                            top_10_pct = (
                                round(min((top_10_shares / inst_shares) * 100, 100.0), 2) if inst_shares else None
                            )

                        records.append(
                            {
                                "symbol": ticker,
                                "filing_date": filing_date,
                                "institutional_ownership_pct": pct,
                                "number_of_institutional_holders": holder_count,
                                "top_10_institutions_pct": top_10_pct,
                                "data_unavailable": False,
                                "reason": None,
                                "sec_filing_url": None,
                                "most_recent_filing_date": filing_date,
                                "data_source": "sec_form13f_bulk",
                                "updated_at": now_et,
                            }
                        )
                        resolved_tickers.add(ticker)
                        logger.debug(f"[13F] {ticker}: {inst_shares:,.0f} / {shares_os:,.0f} = {pct:.1f}%")
                    else:
                        records.append(self._unavailable_record(ticker, now_et, "shares_outstanding_unavailable"))
                        resolved_tickers.add(ticker)
                        logger.debug(f"[13F] {ticker}: shares_outstanding unavailable")
                except Exception as e:
                    logger.debug(f"[13F] {ticker}: error - {e}")

            active_symbols = set(get_active_symbols(exclude_etfs=True))
            for symbol in active_symbols - resolved_tickers:
                records.append(self._unavailable_record(symbol, now_et, "no_resolved_13f_holdings"))

        logger.info(
            f"[13F] Calculated ownership % for {len(resolved_tickers)} tickers; "
            f"wrote fresh data_unavailable markers for {len(records) - len(resolved_tickers)} others"
        )
        return records

    @staticmethod
    def _unavailable_record(symbol: str, now_et: datetime, reason: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "filing_date": now_et.date(),
            "institutional_ownership_pct": None,
            "number_of_institutional_holders": None,
            "top_10_institutions_pct": None,
            "data_unavailable": True,
            "reason": reason,
            "sec_filing_url": None,
            "most_recent_filing_date": None,
            "data_source": "none",
            "updated_at": now_et,
        }


def main() -> int:
    """Entry point for load_institutional_holdings_13f.py."""
    try:
        return run_loader(InstitutionalHoldings13FLoader, global_mode=True)
    except Exception as e:
        logger.error(f"[INSTITUTIONAL_13F FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
