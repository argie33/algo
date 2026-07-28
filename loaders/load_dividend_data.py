#!/usr/bin/env python3
"""Dividend Data Loader - SEC EDGAR.

Loads dividend information from SEC filings including ex-dates, payment dates,
and dividend amounts. Used for position management and dividend tracking.

Data source: SEC EDGAR XBRL financial statements + 8-K filings
Update frequency: Daily (dividend events are reported as filed)

Dividend events are critical for:
- Dividend capture strategies
- Position management (hold through ex-date)
- Tax-efficient trading
- Portfolio yield calculation

Run:
    python3 loaders/load_dividend_data.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from loaders.helpers.sec_base import SecLoaderBase
from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.sec_edgar import SecEdgarClient
from utils.infrastructure.timezone import EASTERN_TZ

logger = logging.getLogger(__name__)
configure_socket_timeout(30)


class DividendDataLoader(SecLoaderBase):
    """Load dividend data from SEC EDGAR XBRL.

    Extracts official dividend data from SEC companyfacts API using XBRL
    concepts: CommonStockDividendsPerShareDeclared and CommonStockDividendsPerShareCashPaid.

    These are authoritative sources maintained by companies in their 10-K/10-Q filings
    per ASC 505 (Equity) disclosure requirements.

    Returns:
    - dividend_per_share: Declared dividend per share (from XBRL, earliest-filed value per
      period - see _extract_dividends_from_xbrl_concept for why later filings can't be trusted)
    - declaration_date: Filing date of the earliest XBRL fact for that dividend period. For
      periods before the filer's XBRL mandate (~2009-2011 depending on filer size), the
      "earliest" available fact is itself from a later filing's historical comparative table
      (confirmed live: MSFT's FY2008 dividend first appears in XBRL in its 2010 10-K) - SEC
      simply has no earlier machine-readable disclosure for these periods, not a loader bug.
    - ex_dividend_date: Estimated from period end date (fiscal quarter/year end)
    - payment_date: Estimated as 30-60 days after ex-dividend date (typical corporate practice)

    For precise ex-dates, investors should use broker API (ex-dates are published
    separately by corporate actions systems, not in SEC filings).
    """

    table_name = "dividend_data"
    # Matches the real DB constraint (migration 1155's uq_dividend_event). A prior version
    # declared a 3-column key including dividend_per_share, which doesn't match any real
    # constraint - BulkInsertManager's auto-constraint logic then silently created a SECOND,
    # conflicting unique constraint on the live table matching the wrong declaration, and
    # _validate_row() treated dividend_per_share as a required (non-NULL) PK field, crashing
    # every symbol that legitimately has no dividend data (the data_unavailable marker sets it
    # to None by design - see _unavailable_record()). Confirmed live: this crashed the loader
    # for the vast majority of non-dividend-paying symbols in the universe, which is why this
    # table only ever had 2 test symbols (AAPL/MSFT, both real dividend payers) despite being a
    # real, wired, SEC XBRL-backed loader.
    primary_key = ("symbol", "ex_dividend_date")
    watermark_field = "ex_dividend_date"
    exclude_etfs_from_symbols = True
    max_fail_rate = 70.0  # Many companies don't pay dividends; allow data_unavailable

    def __init__(self, backfill_days: int | None = None):
        super().__init__(backfill_days)
        self.sec_client = SecEdgarClient()

    def _extract_dividends_from_xbrl_concept(
        self, symbol: str, us_gaap: dict, concept_name: str
    ) -> list[dict[str, Any]]:
        """Extract dividend data from a specific XBRL concept.

        Args:
            symbol: Stock ticker
            us_gaap: Dict of us-gaap XBRL concepts from companyfacts
            concept_name: Name of XBRL concept (e.g., "CommonStockDividendsPerShareDeclared")

        Returns:
            List of dividend records with symbol, dates, and amounts
        """
        results = []

        if concept_name not in us_gaap:
            return results

        concept_data = us_gaap[concept_name]
        if not isinstance(concept_data, dict) or "units" not in concept_data:
            return results

        # companyfacts repeats every historical fact once per filing that carries it in a
        # comparative table (a 10-K's dividend footnote typically shows 2-3 fiscal years side
        # by side) - so the SAME real-world (start, end) period can appear many times across
        # different accessions. Worse, a later stock split retroactively restates the per-share
        # VALUE too: confirmed live for AAPL's 2011-09-25..2012-09-29 period, which reports
        # val=2.65 as originally filed in the 2012 10-K but val=0.38 in the 2014 10-K/2015 8-K
        # after Apple's 2014 7-for-1 split (2.65/7 ~= 0.38). Since dividend_per_share is part of
        # this loader's dedup/primary key, the pre-split and post-split restatements of the
        # identical dividend don't dedupe against each other - both would land as separate,
        # seemingly-legitimate dividends for the same quarter. Keep only the earliest-filed
        # occurrence of each period end date: that's the fact as originally declared/
        # disclosed, not a later split-adjusted restatement - which also fixes declaration_date
        # (derived from `filed`) landing years after the ex-date estimate it's paired with.
        earliest_fact_by_period: dict[str, dict[str, Any]] = {}
        for unit, facts_list in concept_data.get("units", {}).items():
            # XBRL facts are organized by unit. Both concepts this method is called with
            # ("...PerShareDeclared"/"...PerShareCashPaid") are per-share ratio concepts, whose
            # standard US-GAAP taxonomy unit is "USD/shares" - not a plain dollar amount. SEC
            # filers occasionally mistag facts under an unexpected unit (restatements, filer XBRL
            # errors); blindly trusting any unit key here would silently store that filer's raw
            # value as dividend_per_share even if it wasn't actually a per-share figure, corrupting
            # the field with no downstream validation to catch it. Skip anything that isn't the
            # expected per-share unit rather than guess.
            if unit != "USD/shares":
                logger.warning(
                    f"[{symbol}] {concept_name}: skipping unexpected XBRL unit '{unit}' "
                    "(expected 'USD/shares' for a per-share concept) - not treating as dividend_per_share"
                )
                continue
            if not isinstance(facts_list, list):
                continue

            for fact in facts_list:
                if not isinstance(fact, dict):
                    continue

                value = fact.get("val")
                if value is None or value == 0:
                    continue  # Skip zero dividends

                filed_str = fact.get("filed")
                end_str = fact.get("end")
                if not filed_str or not end_str:
                    continue

                existing = earliest_fact_by_period.get(end_str)
                if existing is None or filed_str < existing["filed"]:
                    earliest_fact_by_period[end_str] = fact

        for fact in earliest_fact_by_period.values():
            try:
                value = fact["val"]
                filed_str = fact["filed"]
                end_str = fact["end"]

                # Parse dates
                try:
                    declaration_date = datetime.strptime(filed_str, "%Y-%m-%d").date()
                    period_end = datetime.strptime(end_str, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue

                # Estimate ex-date: typically within 30-60 days after period end
                ex_dividend_date = period_end + timedelta(days=45)
                payment_date = ex_dividend_date + timedelta(days=3)

                results.append(
                    {
                        "symbol": symbol,
                        "declaration_date": declaration_date,
                        "ex_dividend_date": ex_dividend_date,
                        "record_date": None,
                        "payment_date": payment_date,
                        "dividend_per_share": Decimal(str(value)),
                        "dividend_yield_pct": None,
                        "total_dividend_amount": None,
                        "dividend_type": "regular",
                        "currency": "USD",
                        "data_unavailable": False,
                        "data_unavailable_reason": None,
                        "source": f"SEC_XBRL_{concept_name}",
                    }
                )

            except (ValueError, TypeError, AttributeError, KeyError) as e:
                logger.debug(f"[{symbol}] Error parsing XBRL fact: {e}")
                continue

        return results

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch dividend data for symbol from SEC XBRL companyfacts.

        Uses official XBRL concepts from 10-K/10-Q filings:
        - CommonStockDividendsPerShareDeclared
        - CommonStockDividendsPerShareCashPaid

        Returns: Dividend records extracted from XBRL, or data_unavailable marker.
        """
        now_et = datetime.now(EASTERN_TZ).date()

        try:
            # Get CIK for symbol
            cik = self.sec_client.symbol_to_cik(symbol)

            # Fetch companyfacts XBRL
            facts_response = self.sec_client.get_company_facts(cik)
            if not facts_response or "facts" not in facts_response:
                return [self._unavailable_record(symbol, now_et, "no_companyfacts")]

            us_gaap = facts_response.get("facts", {}).get("us-gaap", {})
            if not us_gaap:
                return [self._unavailable_record(symbol, now_et, "no_us_gaap_facts")]

            results = []

            # Extract dividends from XBRL concepts
            declared = self._extract_dividends_from_xbrl_concept(
                symbol, us_gaap, "CommonStockDividendsPerShareDeclared"
            )
            paid = self._extract_dividends_from_xbrl_concept(
                symbol, us_gaap, "CommonStockDividendsPerShareCashPaid"
            )

            results.extend(declared)
            results.extend(paid)

            # Remove duplicates on the actual primary key (symbol, ex_dividend_date,
            # dividend_per_share) - declared/paid concepts can report the same
            # estimated ex-date + amount, and the DB upsert can't affect the same
            # row twice within one batch.
            seen = set()
            unique_results = []
            for r in results:
                key = (r["symbol"], r["ex_dividend_date"], r["dividend_per_share"])
                if key not in seen:
                    seen.add(key)
                    unique_results.append(r)

            if unique_results:
                return unique_results

            # No dividend data found in XBRL
            return [self._unavailable_record(symbol, now_et, "no_dividend_xbrl_concepts")]

        except Exception as e:
            logger.debug(f"[{symbol}] Dividend fetch error: {type(e).__name__}: {e}")
            return [self._unavailable_record(symbol, now_et, f"fetch_error:{type(e).__name__}")]


    def _unavailable_record(self, symbol: str, measurement_date: date, reason: str) -> dict[str, Any]:
        """Return a data_unavailable marker for this symbol."""
        return {
            "symbol": symbol,
            "declaration_date": None,
            "ex_dividend_date": measurement_date,
            "record_date": None,
            "payment_date": None,
            "dividend_per_share": None,
            "dividend_yield_pct": None,
            "total_dividend_amount": None,
            "dividend_type": None,
            "currency": "USD",
            "data_unavailable": True,
            "data_unavailable_reason": reason,
            "source": "NONE",
        }


def main() -> int:
    """Run the dividend data loader."""
    try:
        return run_loader(DividendDataLoader)
    except Exception as e:
        logger.error(f"[DIVIDEND FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
