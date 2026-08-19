#!/usr/bin/env python3
"""Form 8-K Current Reports Loader - SEC EDGAR.

Loads SEC Form 8-K filings (Current Reports) to identify material events
that may impact trading signals. 8-K filings must be made within 4 business
days of a material event.

Data source: SEC EDGAR Submissions API
Update frequency: Daily (events are reported as filed)

Material events tracked:
- Item 1.01: Bankruptcy or material loss
- Item 2.01: Completion of acquisition/disposition
- Item 2.04: Material definitive agreement changes
- Item 3.01: Default under material agreement
- Item 5.02: Changes in directors/officers
- Item 8.01: Other events (catch-all for material events)

Run:
    python3 loaders/load_current_reports_8k.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime
from typing import Any

import requests

from loaders.helpers.sec_base import SecLoaderBase
from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.db.context import DatabaseContext
from utils.external.sec_edgar import SecEdgarClient
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.retry_helper import retry_with_backoff

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class CurrentReports8KLoader(SecLoaderBase):
    """Load SEC Form 8-K Current Reports.

    Form 8-K must be filed within 4 business days of a material event.
    This loader tracks all 8-K filings to identify corporate events that
    may impact stock prices and trading signals.

    Key features:
    - Official SEC EDGAR source (authoritative)
    - Material event classification (Items 1.01-8.01)
    - Event summary and description extraction
    - Daily update cadence
    """

    table_name = "current_reports_8k"
    primary_key = ("symbol", "accession_number")
    watermark_field = "filing_date"
    exclude_etfs_from_symbols = True
    max_fail_rate = 2.0  # SEC API occasionally fails on isolated symbols
    # ROOT-CAUSE FIX 2026-08-16: universe (4,922 symbols) * SEC EDGAR per-symbol latency
    # (~10s observed) is ~13.7h of work against a 120-minute timeout - this loader can
    # never finish a full alphabetical pass. Without rotation, symbols get() always
    # returns in fixed `ORDER BY symbol` order, so every run starts at 'A' and the same
    # ~18% prefix (through ~'COCP') gets covered forever while everything after it is never
    # checked for 8-K filings. Rotating the start point daily spreads coverage across the
    # full universe over successive days instead. See runner.py's rotate_symbols_daily.
    rotate_symbols_daily = True

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        self.sec_client = SecEdgarClient()

    @staticmethod
    def _default_items() -> dict[str, bool]:
        """All item flags False - baseline for a fresh filing or an extraction failure."""
        return {
            "item_1_01": False,  # Bankruptcy/material loss
            "item_1_02": False,  # Unregistered sales
            "item_1_03": False,  # Bankruptcy proceedings
            "item_2_01": False,  # Acquisition/disposition
            "item_2_02": False,  # Results of operations
            "item_2_03": False,  # Material obligations
            "item_2_04": False,  # Definitive agreement changes
            "item_2_05": False,  # Exit/disposal costs
            "item_2_06": False,  # Material impairments
            "item_2_07": False,  # Regulation FD
            "item_2_08": False,  # Other events
            "item_3_01": False,  # Default under agreement
            "item_3_02": False,  # Unregistered sales
            "item_3_03": False,  # Material modification
            "item_4_01": False,  # Accountant changes
            "item_4_02": False,  # Non-reliance
            "item_5_01": False,  # Costs
            "item_5_02": False,  # Bankruptcy
            "item_5_03": False,  # Amendment to articles
            "item_5_05": False,  # Amendments
            "item_5_07": False,  # Matters to vote
            "item_6_01": False,  # Bankruptcy
            "item_7_01": False,  # Regulation FD
            "item_8_01": False,  # Other events
            "item_9_01": False,  # Exhibits
        }

    def _extract_8k_items(self, filing_text: str) -> dict[str, bool]:
        """Extract which 8-K items are disclosed in filing.

        Scans filing text for Item tags that indicate material events.
        Returns dict with item flags set to True if item is disclosed.
        """
        items = self._default_items()

        # Simple heuristic: search for Item tags in filing text
        text_upper = filing_text.upper()

        item_patterns = {
            "item_1_01": "ITEM 1.01",
            "item_2_01": "ITEM 2.01",
            "item_2_02": "ITEM 2.02",
            "item_2_03": "ITEM 2.03",
            "item_2_04": "ITEM 2.04",
            "item_2_05": "ITEM 2.05",
            "item_2_06": "ITEM 2.06",
            "item_2_07": "ITEM 2.07",
            "item_2_08": "ITEM 2.08",
            "item_3_01": "ITEM 3.01",
            "item_3_02": "ITEM 3.02",
            "item_3_03": "ITEM 3.03",
            "item_4_01": "ITEM 4.01",
            "item_4_02": "ITEM 4.02",
            "item_5_02": "ITEM 5.02",
            "item_5_03": "ITEM 5.03",
            "item_5_07": "ITEM 5.07",
            "item_8_01": "ITEM 8.01",
            "item_9_01": "ITEM 9.01",
        }

        for key, pattern in item_patterns.items():
            if pattern in text_upper:
                items[key] = True

        return items

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch Form 8-K filings for symbol since given date.

        Args:
            symbol: Stock symbol
            since: Only fetch filings on or after this date

        Returns:
            List of 8-K filing records or data_unavailable marker
        """
        try:
            now_et = datetime.now(EASTERN_TZ).date()
            # Get CIK for symbol
            cik = self._get_cik(symbol)
            if not cik:
                return self._unavailable_record(symbol, now_et, "symbol_not_found")

            # Get submissions (SEC API returns columnar format: dict of arrays)
            submissions = self.sec_client.get_submissions(cik)
            if not submissions:
                return self._unavailable_record(symbol, now_et, "no_submissions")

            # Extract columnar data from SEC API
            filings = submissions.get("filings")
            recent = filings.get("recent") if isinstance(filings, dict) else None
            if not isinstance(recent, dict) or "form" not in recent:
                return self._unavailable_record(symbol, now_et, "invalid_submissions_format")

            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            accessions = recent.get("accessionNumber", [])

            # Process each filing, building 8-K records from parallel arrays
            results = []
            for i, form in enumerate(forms[:100]):  # Limit to 100 most recent
                if form != "8-K":
                    continue

                filing_date_str = dates[i] if i < len(dates) else None
                if not filing_date_str:
                    continue

                filing_date = self._parse_date(filing_date_str)
                if filing_date < (since or date(1990, 1, 1)):
                    continue  # Skip filings before watermark

                accession_number_raw = accessions[i] if i < len(accessions) else ""
                accession_number = accession_number_raw.replace("-", "")

                try:
                    # get_filing_plaintext() builds the SEC archive URL's directory
                    # segment from a dash-stripped accession number but the .txt
                    # filename itself from the DASHED form (SEC's own convention,
                    # e.g. .../000032019326000011/0000320193-26-000011.txt) - passing
                    # the already-dash-stripped accession_number here 404s on every
                    # filing (confirmed live against SEC EDGAR), which silently broke
                    # item extraction for the entire life of this loader. Must pass
                    # the raw dashed value the SEC submissions API actually returned.
                    filing_text = self.sec_client.get_filing_plaintext(cik, accession_number_raw)
                    items = self._extract_8k_items(filing_text)

                    # Extract summary from first 500 chars of filing
                    summary = filing_text[:500] if filing_text else ""
                    item_extraction_failed_reason = None

                except Exception as e:
                    # Item flags are genuinely unknown here, not "no items disclosed" -
                    # defaulting to all-False items while also claiming data_unavailable
                    # False would tell downstream material-event signals a filing was
                    # checked and clean when it was never actually read. Record the
                    # filing's existence/date (still useful) but flag this row unavailable
                    # so it reads as "unknown", not "no material items".
                    logger.debug(f"[{symbol}] 8-K parsing error: {type(e).__name__}: {e}")
                    items = self._default_items()
                    summary = None
                    item_extraction_failed_reason = f"item_extraction_failed:{type(e).__name__}"

                record = {
                    "symbol": symbol,
                    "filing_date": filing_date,
                    "accession_number": accession_number,
                    "form_type": "8-K",
                    **items,
                    "event_summary": summary,
                    "material_items_text": None,
                    "data_unavailable": item_extraction_failed_reason is not None,
                    "data_unavailable_reason": item_extraction_failed_reason,
                }

                results.append(record)

            # FIX 2026-08-18 (goal: find/fix real algo+loader issues): a symbol with valid SEC
            # submissions but zero Form 8-K filings among them (foreign private issuers file
            # Form 6-K instead - live-confirmed on AEM/AEG/AGRO/AER/ACB, all real companies with
            # real CIKs and real submissions) used to fall through to a bare `return results`
            # (empty list) here, indistinguishable from "not checked yet". No row ever gets
            # written for that symbol, so it has no watermark and gets re-fetched from scratch
            # on every single run forever - live-confirmed via data_loader_status_history:
            # this loader FAILED every run since 2026-08-16 (0%->12%->20%->43%->49%->83.04%
            # completion over 2+ days, ~5h/run), and 837/4934 universe symbols have zero rows
            # in current_reports_8k despite the loader successfully querying valid SEC data for
            # them every time. This loader already has an _unavailable_record() mechanism built
            # exactly for "ETF/foreign-issuer symbol with no SEC 8-K coverage" (see its own
            # docstring) but never actually called it in this case. Only fires on `since is
            # None` (this symbol's genuinely first-ever check, no existing watermark) so it
            # writes the marker once, advances the watermark, and never re-marks on later
            # incremental runs - same "before writing the marker, check for prior real coverage
            # first" precedent as the analyst-coverage marker-masking fix
            # (marker_masks_real_data_in_event_log_tables_bug_class_20260818).
            # FIXED 2026-08-19 (goal: "no SEC data"/missing factor inputs audit, same-day
            # follow-up to the _get_cik retry fix above): `since is None` alone missed a real
            # case - a symbol whose PRIOR run permanently wrote "symbol_not_found" (from a
            # transient CIK-resolution failure, now fixed to retry) has a real watermark
            # (since is NOT None), so a later run finding zero new 8-Ks just returns [] here
            # and silently leaves that stale, wrong marker as the "latest" row forever - the
            # CIK now resolves fine (we're past line 157, cik was truthy), but nothing ever
            # overwrites the bad old record. Live-confirmed: re-running this loader today for
            # AEP/ELSE/FGMC/NXH/VMRK (all live-verified as real, CIK-resolvable filers) wrote
            # nothing new despite `since is None` returning here. A prior "symbol_not_found"
            # is a resolution-layer failure, not a legitimate "checked, no new 8-Ks" state
            # like every other reason this branch guards against re-marking - it must be
            # retried until corrected, not treated as permanently settled once real CIK
            # resolution succeeds.
            if not results and (since is None or self._last_reason_was_symbol_not_found(symbol)):
                return self._unavailable_record(symbol, now_et, "no_8k_filings_in_recent_submissions")

            return results

        except RuntimeError:
            # FIX 2026-08-10: _get_cik() deliberately raises RuntimeError for network/API
            # failures ("Network/API errors must not be masked" - see its own docstring),
            # but the blanket `except Exception` below used to catch it anyway and convert
            # it into an ordinary data_unavailable record - the exact masking _get_cik was
            # written to prevent. That silently defeated this loader's max_fail_rate=2.0
            # circuit breaker: a full SEC EDGAR outage looked like COMPLETED/~100% with
            # every symbol marked data_unavailable instead of a failed run. Re-raise so
            # OptimalLoader._safe_load_symbol counts it as a real symbols_failed.
            raise

        except Exception as e:
            logger.error(f"[{symbol}] 8-K fetch error: {type(e).__name__}: {e}")
            now_et = datetime.now(EASTERN_TZ).date()
            return self._unavailable_record(symbol, now_et, f"fetch_error:{type(e).__name__}")

    def _parse_date(self, date_str: str) -> date:
        """Parse SEC date string (YYYY-MM-DD format). Fail-fast on parse errors."""
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError) as e:
            raise ValueError(
                f"Cannot parse SEC filing date '{date_str}': must be YYYY-MM-DD format. "
                f"Data quality issue or format change in SEC EDGAR responses."
            ) from e

    @staticmethod
    def _last_reason_was_symbol_not_found(symbol: str) -> bool:
        """True if this symbol's most recent stored row is a "symbol_not_found" marker.

        See the fetch_incremental caller's comment: that reason means the CIK-resolution
        layer itself failed last time, which the _get_cik retry fix above can now recover
        from - but only if this run actually re-marks the row when there's nothing new to
        report. A quick, targeted read (only reached when results is already empty), not a
        per-symbol cost paid on every run.
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT data_unavailable_reason FROM current_reports_8k
                    WHERE symbol = %s ORDER BY filing_date DESC LIMIT 1
                    """,
                    (symbol,),
                )
                row = cur.fetchone()
                return bool(row and row[0] == "symbol_not_found")
        except Exception as e:
            logger.debug(f"[{symbol}] Could not check prior reason: {type(e).__name__}: {e}")
            return False

    def _get_cik(self, symbol: str) -> str | None:
        """Get CIK for symbol using SEC Edgar client (authoritative source).

        Raises:
            RuntimeError: If SEC Edgar API call fails (network error, timeout, etc.)
            (Does not raise if symbol simply not found - that's a legitimate data gap)
        """
        try:
            # FIXED 2026-08-19 (goal: "no SEC data"/missing factor inputs audit): a single
            # symbol_to_cik() ValueError was treated as permanent "not in SEC" with zero
            # retry - but that call's own last-resort path (sec_ticker_cache.py's
            # _lookup_via_browse_edgar, a slow legacy CGI endpoint) only retries transient
            # HTTP/network failures itself, and only twice with a few seconds' backoff -
            # not enough margin for a longer SEC-side rate-limit/outage window. Live-
            # confirmed: AEP (American Electric Power, a real S&P 500 utility with CIK
            # 4904 - documented in that same module as the canary case for this exact
            # ticker-not-in-bulk-files pattern) got permanently marked "symbol_not_found"
            # in this table on 2026-08-17, yet resolves correctly on a fresh, unretried
            # call today - a transient failure baked in as permanent because this loader's
            # incremental scheduling never revisits a symbol once it has any row on file,
            # "symbol_not_found" included. One retry with a real backoff here (not the
            # network-only retry inside symbol_to_cik itself) gives a slow SEC response
            # window a real chance to clear before writing a marker that effectively never
            # gets re-checked.
            cik = retry_with_backoff(
                lambda: self.sec_client.symbol_to_cik(symbol),
                context=f"{symbol} CIK lookup",
                max_retries=1,
                backoff_seconds=5.0,
            )
            return str(cik).zfill(10)
        except ValueError:
            # Symbol not found in SEC even after a retry - legitimate, not an error
            logger.debug(f"[{symbol}] Symbol not found in SEC Edgar")
            return None
        except (ConnectionError, TimeoutError, requests.RequestException) as e:
            # Network/API errors should fail-fast - don't mask them
            raise RuntimeError(
                f"[8K] SEC Edgar API failed for {symbol}: {type(e).__name__}: {e}. "
                f"Network/API errors must not be masked."
            ) from e
        except Exception as e:
            # Unexpected errors - also fail-fast to alert operators
            raise RuntimeError(f"[8K] Unexpected error fetching CIK for {symbol}: {type(e).__name__}: {e}") from e

    def _unavailable_record(self, symbol: str, measurement_date: date, reason: str) -> list[dict[str, Any]]:
        """Return a data_unavailable marker for this symbol.

        LIVE-REPRODUCED 2026-08-16: accession_number is NOT NULL (it's part of this table's
        composite primary key with symbol, varchar(20)) and used to be "" here. bulk_insert_manager's
        COPY path applies FORCE_NULL to every column and collapses None->"" before writing the CSV
        buffer (utils/bulk_insert_manager.py's normalized[k] = "" if v is None else v), so it can't
        tell a deliberate empty string apart from a real None - FORCE_NULL converted this "" straight
        back to NULL on the way into Postgres, which then failed the NOT NULL/PK constraint on every
        single unavailable-marker row (i.e. every ETF/foreign-issuer symbol with no SEC 8-K coverage -
        confirmed live via AEP/AFBI/AGG all failing with the same "null value in column
        accession_number" error during a full-universe run). A short non-empty sentinel side-steps the
        ambiguity without touching the shared COPY/CSV code path other loaders also depend on.
        """
        return [
            {
                "symbol": symbol,
                "filing_date": measurement_date,
                "accession_number": "UNAVAILABLE",
                "form_type": "8-K",
                "item_1_01": False,
                "item_1_02": False,
                "item_1_03": False,
                "item_2_01": False,
                "item_2_02": False,
                "item_2_03": False,
                "item_2_04": False,
                "item_2_05": False,
                "item_2_06": False,
                "item_2_07": False,
                "item_2_08": False,
                "item_3_01": False,
                "item_3_02": False,
                "item_3_03": False,
                "item_4_01": False,
                "item_4_02": False,
                "item_5_01": False,
                "item_5_02": False,
                "item_5_03": False,
                "item_5_05": False,
                "item_5_07": False,
                "item_6_01": False,
                "item_7_01": False,
                "item_8_01": False,
                "item_9_01": False,
                "event_summary": None,
                "material_items_text": None,
                "data_unavailable": True,
                "data_unavailable_reason": reason,
            }
        ]


def main() -> int:
    """Run the 8-K loader."""
    try:
        return run_loader(CurrentReports8KLoader)
    except Exception as e:
        logger.error(f"[8K FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
