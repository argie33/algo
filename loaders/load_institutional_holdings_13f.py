#!/usr/bin/env python3
"""Institutional Holdings Loader - SEC Form 13F (INFOTABLE bulk dataset).

Uses SEC's official 13F-HR structured datasets:
https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets

Data source: INFOTABLE.tsv. Real columns (verified against a real downloaded
dataset - NOT a "ticker" column, contrary to this loader's original assumption):
ACCESSION_NUMBER, INFOTABLE_SK, NAMEOFISSUER, TITLEOFCLASS, CUSIP, FIGI, VALUE,
SSHPRNAMT, SSHPRNAMTTYPE, PUTCALL, INVESTMENTDISCRETION, OTHERMANAGER,
VOTING_AUTH_*. 13F filings identify securities by CUSIP only - SEC does not
publish a free CUSIP->ticker crosswalk, and none exists elsewhere in this
codebase (see migrations 1124/1151, utils/sec_form13f_aggregator.py).

Updated: SEC publishes rolling ~3-month windows keyed to the 45-day-after-quarter-end
filing deadline (e.g. "01jun2025-31aug2025_form13f.zip", not a plain
"{year}-Q{quarter}" label - the dataset filenames are discovered by scraping SEC's own
listing page rather than guessed via calendar-quarter date arithmetic, since the
window boundaries don't align to calendar quarters cleanly).
Coverage: Institutional managers with $100M+ in assets (excludes small institutions)

Architecture:
- fetch_global() downloads & parses the latest published 13F bulk dataset once,
  aggregating shares held per CUSIP across all institutional managers
- Without a CUSIP->ticker crosswalk, per-symbol ownership % cannot be computed from
  this alone - fails fast with an explicit reason rather than fabricating estimates
- fetch_incremental() returns cached global results per symbol (once a crosswalk
  exists to populate them)

Run:
    python3 loaders/load_institutional_holdings_13f.py [--symbols AAPL,MSFT]
"""

import csv
import io
import logging
import re
import sys
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)

SEC_13F_DATASETS_PAGE = "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
_ZIP_LINK_RE = re.compile(
    r'href="(/files/[a-z]+/data/form-13f-data-sets/(\d{2}[a-z]{3}\d{4})-(\d{2}[a-z]{3}\d{4})_form13f\.zip)"',
    re.IGNORECASE,
)


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

            try:
                holdings_by_cusip = self._fetch_and_parse_13f_bulk(url)
            except Exception as e:
                logger.warning(
                    f"[13F] Bulk dataset fetch/parse failed ({type(e).__name__}: {str(e)[:200]}); "
                    f"falling back to per-manager aggregation"
                )
                return self._calculate_and_cache_ownership(self._aggregate_top_manager_13fs(), period_end)

            # Real SEC data, correctly reached and parsed - but 13F filings identify
            # securities by CUSIP only. Without a CUSIP->ticker crosswalk (not
            # implemented anywhere in this codebase - see module docstring), these
            # holdings cannot be attributed to a stock symbol. Fail fast here rather
            # than pass CUSIP keys into _calculate_and_cache_ownership, which queries
            # company_info_sec by symbol and would silently return zero rows.
            msg = (
                f"[13F CRITICAL] Downloaded and parsed real SEC 13F bulk data from {url}: "
                f"{len(holdings_by_cusip)} CUSIPs, period end {period_end}. Cannot compute "
                f"per-symbol institutional_ownership_pct without a CUSIP->ticker crosswalk "
                f"(not yet implemented - see migrations 1124/1151). This is a missing "
                f"feature, not a data-availability problem: SEC's data was reachable and "
                f"parsed correctly. ACTION: implement a CUSIP->ticker mapping before this "
                f"loader can populate institutional_holdings_13f."
            )
            logger.critical(msg)
            raise RuntimeError(msg)

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
                    SELECT institutional_ownership_pct, filing_date, data_source
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
                        "number_of_institutional_holders": None,
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
            with urllib.request.urlopen(req, timeout=30) as response:
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

    def _fetch_and_parse_13f_bulk(self, url: str) -> dict[str, int]:
        """Download and parse SEC's INFOTABLE.tsv from the discovered bulk dataset URL.

        Returns: dict of {CUSIP: total_shares_held_by_all_institutions}. Keyed by
            CUSIP, NOT ticker - 13F filings never carry a ticker field (verified
            against a real downloaded dataset's actual column headers).
        """
        req = urllib.request.Request(url, headers={"User-Agent": "algo-trading argeropolos@gmail.com"})
        with urllib.request.urlopen(req, timeout=120) as response:
            zip_data = response.read()

        holdings_by_cusip: dict[str, int] = defaultdict(int)
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
                            raise ValueError(f"[13F] CSV row missing required 'SSHPRNAMT' field for CUSIP {row.get('CUSIP')}")

                        cusip = row["CUSIP"].strip().upper()
                        shares_str = row["SSHPRNAMT"]
                        if cusip and shares_str:
                            if not shares_str.isdigit():
                                raise ValueError(f"[13F] Invalid SSHPRNAMT '{shares_str}' for CUSIP {cusip} (expected integer)")
                            shares = int(shares_str)
                            if shares > 0:
                                holdings_by_cusip[cusip] += shares

            logger.info(f"[13F] Aggregated {len(holdings_by_cusip)} CUSIPs from bulk data")
            return holdings_by_cusip

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
        self, holdings_by_ticker: dict[str, int], filing_date: date
    ) -> list[dict[str, Any]]:
        """Calculate institutional ownership % for each ticker.

        Uses shares_outstanding from company_info_sec table.
        """
        logger.info("[13F] Calculating institutional ownership percentages...")
        records = []
        now_et = datetime.now(EASTERN_TZ)

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

                        records.append(
                            {
                                "symbol": ticker,
                                "filing_date": filing_date,
                                "institutional_ownership_pct": pct,
                                "number_of_institutional_holders": None,  # Aggregate doesn't track manager count
                                "data_unavailable": False,
                                "reason": None,
                                "sec_filing_url": None,
                                "most_recent_filing_date": filing_date,
                                "data_source": "sec_form13f_bulk",
                                "updated_at": now_et,
                            }
                        )
                        logger.debug(f"[13F] {ticker}: {inst_shares:,.0f} / {shares_os:,.0f} = {pct:.1f}%")
                    else:
                        logger.debug(f"[13F] {ticker}: skipped (shares_outstanding unavailable)")
                except Exception as e:
                    logger.debug(f"[13F] {ticker}: error - {e}")

        logger.info(f"[13F] Calculated ownership % for {len(records)} tickers")
        return records


def main() -> int:
    """Entry point for load_institutional_holdings_13f.py."""
    try:
        return run_loader(InstitutionalHoldings13FLoader, global_mode=True)
    except Exception as e:
        logger.error(f"[INSTITUTIONAL_13F FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
