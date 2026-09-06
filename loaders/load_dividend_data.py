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
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from loaders.helpers.sec_base import SecLoaderBase
from loaders.runner import run_loader
from loaders.timeout_config import configure_socket_timeout
from utils.external.fx_rates import MAJOR_CURRENCIES, FxRateCache
from utils.external.sec_edgar import SecEdgarClient
from utils.infrastructure.timezone import EASTERN_TZ
from utils.loaders.transient_errors import TransientAPIError

logger = logging.getLogger(__name__)
configure_socket_timeout(30)

# CRITICAL: SEC API calls can hang indefinitely even with socket timeout.
# ThreadPoolExecutor enforces a hard timeout at the Python level.
# This is the only reliable way to prevent 5+ hour hangs observed 2026-08-04.
_API_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sec-api-")

# Module-level (not per-instance) so the historical-rate cache is shared across every
# symbol processed in a run - same rationale as sec_statements.py's own _fx_rate_cache.
_fx_rate_cache = FxRateCache()

# IFRS taxonomy equivalents of the two US-GAAP per-share dividend concepts this loader
# already checks. FIX 2026-08-18 (goal: find/fix real loader gaps): foreign private
# issuers (20-F/40-F filers) tag dividends under ifrs-full, never us-gaap - live-confirmed
# via ERIC (DividendsPaidOrdinarySharesPerShare, DividendsRecognisedAsDistributionsTo
# OwnersPerShare) and TU (DividendsPaidOrdinarySharesPerShare), both real, current dividend
# payers (per value_metrics.dividend_yield) that this loader was marking
# no_dividend_xbrl_concepts because it only ever looked at us-gaap. "OtherShares" variants
# (e.g. BWMX's DividendsPaidOtherSharesPerShare) deliberately excluded - that concept can
# represent a different, non-ordinary share class, not a straightforward GAAP-concept
# equivalent.
_IFRS_DIVIDEND_PER_SHARE_CONCEPTS = (
    "DividendsPaidOrdinarySharesPerShare",
    "DividendsRecognisedAsDistributionsToOwnersPerShare",
)

# FIX 2026-08-19 (goal: "no SEC data" audit - dividend_data's dominant gap): live sampling
# of 60 random symbols marked no_dividend_xbrl_concepts despite a real, positive
# value_metrics.dividend_yield found the SINGLE largest remaining pattern (roughly 75% of
# that sample, once the already-fixed IFRS/currency cases were excluded) is filers that
# tag a real cash dividend, but only as a TOTAL DOLLAR AMOUNT concept - never any per-share
# concept at all. Confirmed live: STZ, DHR, FOXA, IR and 40+ others in the sample report
# real dividends exclusively via PaymentsOfDividends/DividendsCommonStockCash-family
# concepts (US GAAP) or DividendsPaid-family concepts (IFRS), with zero presence of any
# per-share XBRL tag. Deriving a per-share figure by dividing by shares outstanding was
# considered and rejected: several of these filers (e.g. STZ) have multi-class share
# structures where a naive division would silently produce a wrong per-share value - worse
# than no data for a table whose docstring purpose is precision ("position management",
# "dividend capture strategies"). Instead these concepts are extracted as a direct,
# unmodified XBRL fact into the existing (always-NULL until now) total_dividend_amount
# column, with dividend_per_share left NULL rather than guessed - real total-dividend data
# beats a false "no data" marker, without the derivation risk. Ordered most-specific-to-
# common-shareholders first; PaymentsOfDividends/DividendsPaid are broader (may include
# preferred/NCI at some filers) but are the ONLY concept many filers ever tag - same
# precedent as this codebase's existing PaymentsOf*Dividend* dividends_paid handling
# (commit 8bf6ad23e). Only tried as a fallback when zero per-share results exist for the
# symbol (see fetch_incremental below), so a filer with real per-share data is never
# double-counted against its own total.
_TOTAL_DIVIDEND_CONCEPTS_GAAP = (
    "PaymentsOfDividendsCommonStock",
    "DividendsCommonStockCash",
    "DividendsCommonStock",
    "PaymentsOfDividends",
    "PaymentsOfOrdinaryDividends",
)
_TOTAL_DIVIDEND_CONCEPTS_IFRS = (
    "DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities",
    "DividendsRecognisedAsDistributionsToOwnersOfParent",
    "DividendsPaid",
)

# DECIMAL(15,2) (migration 1155) overflows at |value| >= 10**13 - same "reject at the
# column's own overflow line" convention as the per-share magnitude guard below.
_MAX_PLAUSIBLE_TOTAL_DIVIDEND = 10**13

# dividend_data.source is VARCHAR(120) (migration 1212). FIXED 2026-08-19 (live-crashed during
# a triggered backfill, minutes after landing): migration 1210 widened this column to 80 chars
# to cover the longest per-share concept name known at the time, but the total-dollar fallback
# (added the same day, after 1210 was written) uses a longer "SEC_XBRL_TOTAL_" prefix -
# DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities alone produced an 82-char
# source string, 2 over the limit, live-crashing the COPY for BEPC/BVN/BWLP/CAAP/DEO/ENLT/FMX/
# GRFS and more real IFRS dividend payers within minutes. Migration 1212 widened the column
# again (120), but a hardcoded Python f-string has no way to know the column's own limit changed
# - truncating defensively here means any FUTURE SEC concept name longer than this can never
# crash a symbol's entire dividend row again; source is free-text provenance metadata, not a
# financial value, so truncation is safe (unlike every other bound in this file, which rejects
# rather than truncates).
_SOURCE_MAX_LEN = 120


def _bounded_source(raw_source: str) -> str:
    return raw_source[:_SOURCE_MAX_LEN]


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

    @staticmethod
    def _decompose_fiscal_ytd_cumulative_series(facts_by_end_date: dict[str, dict[str, Any]]) -> None:
        """Mutates facts_by_end_date IN PLACE: converts a same-start-date, monotonically
        non-decreasing series of fiscal-year-to-date cumulative facts into their true
        incremental per-period deltas.

        Live-confirmed via ICMB (a BDC with a June fiscal year-end): its real
        CommonStockDividendsPerShareDeclared facts for FY2025 are
        (2025-01-01..2025-03-31, val=0.12), (2025-01-01..2025-06-30, val=0.24),
        (2025-01-01..2025-09-30, val=0.38), (2025-01-01..2025-12-31, val=0.52) - each a
        fiscal-year-TO-DATE cumulative total (Q2 alone = 0.24-0.12 = 0.12, Q3 alone =
        0.38-0.24 = 0.14, Q4 alone = 0.52-0.38 = 0.14), not four independent full-size
        dividends. Without this fix, all 4 raw cumulative values would be stored as if
        each were its own distinct quarterly dividend - summing to 1.26 for a trailing-
        12-month yield calculation that should only total the real 0.52 actually paid
        that fiscal year (a ~2.4x overcount), the exact mechanism behind ICMB's real
        implausible dividend_yield.

        Only fires on a genuine monotonically-non-decreasing same-start-date series (the
        structural signature of a real FYTD cumulative sequence, distinguishing it from a
        single restated/corrected re-filing of the identical period, which
        _cumulative_restatement_end_dates already handles via its own exact end-date
        key). A same-start-date series that decreases anywhere is left untouched entirely
        (a value restatement/correction this transform can't safely reason about) rather
        than guessed at.
        """
        by_start: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for end_str, fact in facts_by_end_date.items():
            start = fact.get("start")
            if not start or fact.get("val") is None:
                continue
            by_start.setdefault(start, []).append((end_str, fact))

        for group in by_start.values():
            if len(group) < 2:
                continue
            group.sort(key=lambda pair: pair[0])  # ISO end-date strings sort chronologically
            values = [fact["val"] for _, fact in group]
            if any(values[i] > values[i + 1] for i in range(len(values) - 1)):
                continue  # not a clean cumulative progression - leave every fact untouched

            previous_end = group[0][1]["start"]
            previous_val = 0.0
            for end_str, fact in group:
                val = fact["val"]
                # round() avoids float-subtraction artifacts (e.g. 0.24 - 0.12 =
                # 0.11999999999999998 in raw IEEE-754) - matches this table's own
                # DECIMAL(10,4) dividend_per_share column precision.
                delta = round(val - previous_val, 4)
                if delta > 0:
                    fact["start"] = previous_end
                    fact["val"] = delta
                # delta == 0 (no incremental payment this period, e.g. a restatement that
                # exactly repeats the prior cumulative total): leave the fact's raw value
                # as-is so _cumulative_restatement_end_dates' own exact-value containment
                # check can still see and drop it as a duplicate of the shorter period.
                previous_end = end_str
                previous_val = val

    @staticmethod
    def _cumulative_restatement_end_dates(facts_by_end_date: dict[str, dict[str, Any]]) -> set[str]:
        """End-date keys of facts that are a cumulative (YTD) restatement of an already-
        counted shorter period, not a distinct additional dividend - see
        _extract_dividends_from_xbrl_concept's own 2026-09-05 comment for the full TASK
        (TaskUs) live evidence this was found from.

        When one fact's [start, end] span strictly CONTAINS another's and they report the
        IDENTICAL value, the longer-duration fact is a restatement of the same payment(s),
        not additional income - its end date is returned so the caller can drop it and keep
        only the shorter, more precise period. Deliberately does NOT flag the case where a
        longer fact's value differs from every contained shorter fact's value (e.g. a real
        annual total that's the SUM of two distinct same-size quarterly dividends,
        0.55+0.55=1.10) - that's genuine additional information this loader can't safely
        decompose further, so it's left alone.
        """
        contained_end_dates: set[str] = set()
        for end_str, outer in facts_by_end_date.items():
            outer_start, outer_end, outer_val = outer.get("start"), outer.get("end"), outer.get("val")
            if not outer_start or not outer_end:
                continue
            for inner_end_str, inner in facts_by_end_date.items():
                if inner_end_str == end_str:
                    continue
                inner_start, inner_end, inner_val = inner.get("start"), inner.get("end"), inner.get("val")
                if not inner_start or not inner_end or inner_val != outer_val:
                    continue
                # Containment: inner's span sits fully inside outer's. outer_end != inner_end
                # is already guaranteed (both are dict keys), so containment here always means
                # outer is strictly the longer period - never two identical-span facts
                # (those already deduped by filed_str before this runs, keyed on the same
                # end date).
                if outer_start <= inner_start and inner_end <= outer_end:
                    contained_end_dates.add(end_str)
                    break
        return contained_end_dates

    def _extract_dividends_from_xbrl_concept(
        self, symbol: str, us_gaap: dict[str, Any], concept_name: str
    ) -> list[dict[str, Any]]:
        """Extract dividend data from a specific XBRL concept.

        Args:
            symbol: Stock ticker
            us_gaap: Dict of us-gaap XBRL concepts from companyfacts
            concept_name: Name of XBRL concept (e.g., "CommonStockDividendsPerShareDeclared")

        Returns:
            List of dividend records with symbol, dates, and amounts
        """
        results: list[dict[str, Any]] = []

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
        units_raw = concept_data.get("units") if "units" in concept_data else None
        units_data: dict[str, Any] = units_raw if isinstance(units_raw, dict) else {}
        for unit, facts_list in units_data.items():
            # XBRL facts are organized by unit. US-GAAP per-share dividend concepts use
            # "USD/shares"; the IFRS equivalents this loader also checks (foreign 20-F/40-F
            # filers) use "{HOME_CURRENCY}/shares" instead, e.g. TU's "CAD/shares" - see
            # _IFRS_DIVIDEND_PER_SHARE_CONCEPTS above. Convert non-USD major-currency units
            # (fx_rates.py's MAJOR_CURRENCIES whitelist - liquid, developed-market currencies
            # only) to USD via a real historical ECB rate for each fact's own period-end date,
            # same fail-closed discipline as sec_statements.py's currency handling: a missing
            # rate leaves that fact unset rather than guessing. Everything else (emerging-
            # market currencies, mistagged non-per-share units) is rejected outright, same as
            # before - blindly trusting any unit key would silently store a filer's raw local-
            # currency or non-per-share value as if it were USD dividend_per_share.
            currency_code = unit.split("/", 1)[0]
            if unit == "USD/shares":
                fx_currency = None
            elif unit == f"{currency_code}/shares" and currency_code in MAJOR_CURRENCIES:
                fx_currency = currency_code
            else:
                logger.warning(
                    f"[{symbol}] {concept_name}: skipping unexpected XBRL unit '{unit}' "
                    "(expected 'USD/shares' or a major-currency '.../shares') - not treating as dividend_per_share"
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

                if fx_currency is not None:
                    end_for_rate = fact.get("end")
                    fx_rate = _fx_rate_cache.get_usd_rate(fx_currency, end_for_rate) if end_for_rate else None
                    if fx_rate is None or fx_rate == 0:
                        continue  # No real rate for this date - fail closed, never guess
                    value = value / fx_rate

                # FIX 2026-08-17: dividend_per_share is DECIMAL(10,4) (migration 1155), so any
                # |value| >= 10**6 overflows the column at insert time. This isn't a unit-tag
                # error the check above catches - the unit IS correctly "USD/shares", the VALUE
                # itself is filer-tagging garbage (live-confirmed MDRR: val=12650000 tagged as
                # CommonStockDividendsPerShareDeclared/USD/shares, obviously a total-dollars
                # figure mistagged as per-share). Per-symbol isolation in optimal_loader.py's
                # load loop meant this only killed MDRR's own row, but it recurred every single
                # run since it's a permanent bad fact, not a transient error - MDRR would never
                # get dividend data until this magnitude bound rejects it here instead of at
                # the DB COPY boundary.
                if abs(value) >= 10**6:
                    logger.warning(
                        f"[{symbol}] {concept_name}: skipping implausible value {value!r} "
                        "(>= 1,000,000, would overflow DECIMAL(10,4) column) - filer tagging error, not a real per-share amount"
                    )
                    continue

                filed_str = fact.get("filed")
                end_str = fact.get("end")
                if not filed_str or not end_str:
                    continue

                existing = earliest_fact_by_period.get(end_str)
                if existing is None or filed_str < existing["filed"]:
                    # Store a copy with the (possibly FX-converted) `value` substituted in,
                    # not the raw `fact` dict - the loop below reads fact["val"] again to
                    # build the final record, and companyfacts payloads may be cache-shared
                    # across calls, so mutating `fact` in place would corrupt that cache and
                    # double-apply the conversion on a later lookup.
                    earliest_fact_by_period[end_str] = {**fact, "val": value}

        # FIXED 2026-09-05 (goal session: "missing SEC/XBRL data"/implausible-values sweep,
        # dividend_yield implausible_ratio investigation): earliest_fact_by_period dedupes by
        # period END DATE alone - it has no notion of a fact's DURATION, so a same-value
        # cumulative (YTD) restatement of an already-counted period survives as a completely
        # separate "dividend" because its end date differs from the shorter period's. Live-
        # confirmed via TASK (TaskUs): a real Q1 2026 special dividend (start=2026-01-01,
        # end=2026-03-31, val=3.65) and the SAME company's H1 2026 cumulative fact
        # (start=2026-01-01, end=2026-06-30, val=3.65 - i.e. Q2 contributed exactly $0) both
        # survived as independent dividend_data rows with two different derived ex-dividend
        # dates, doubling this one real payment into two ($3.65 -> $7.30) - inflating
        # dividend_yield enough to trip the implausible-ratio bound. NOT limited to the new
        # special dividend: the SAME shape affects TASK's own older, previously-trusted
        # history too - FY2021's annual fact (2021-01-01..2021-12-31, val=0.55) and the Q2
        # 2021 quarterly fact (2021-04-01..2021-06-30, val=0.55) are the same single real
        # dividend (TaskUs paid exactly once that year), not two. See
        # _cumulative_restatement_end_dates's own docstring for the fix itself (split out
        # here, pushed this function's own cyclomatic complexity over ruff's C901 limit).
        #
        # FIXED 2026-09-05 (same investigation, ICMB follow-up): TASK's shape is the
        # degenerate (zero-growth) case of a broader pattern - a filer whose cumulative
        # FYTD facts genuinely GROW each quarter (ICMB: 0.12/0.24/0.38/0.52, a real BDC
        # distribution schedule) was untouched by the exact-value check above, since every
        # value differs. _decompose_fiscal_ytd_cumulative_series runs FIRST to convert that
        # kind of series into true incremental per-period deltas (mutating values in
        # place) - see its own docstring for the full evidence. Order matters: after this
        # runs, a genuine zero-growth period (TASK's H1 fact) still has its original raw
        # value, so the exact-value containment check immediately below still catches it.
        self._decompose_fiscal_ytd_cumulative_series(earliest_fact_by_period)

        for end_str in self._cumulative_restatement_end_dates(earliest_fact_by_period):
            del earliest_fact_by_period[end_str]

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

                # Estimate ex-date: typically within 30-60 days after period end.
                # This estimate is a structural necessity, not a data-quality shortcut:
                # SEC XBRL only reports declared/paid per-share amounts tied to a fiscal
                # period, never a true ex-dividend date, yet ex_dividend_date is this
                # table's dedup/primary key (migration 1168) - some anchor date is required
                # to key each dividend record on. payment_date has no such requirement, so
                # unlike ex_dividend_date it's left None (matching record_date below)
                # rather than compounding the estimate with a second guessed date.
                ex_dividend_date = period_end + timedelta(days=45)

                results.append(
                    {
                        "symbol": symbol,
                        "declaration_date": declaration_date,
                        "ex_dividend_date": ex_dividend_date,
                        "record_date": None,
                        "payment_date": None,
                        "dividend_per_share": Decimal(str(value)),
                        "dividend_yield_pct": None,
                        "total_dividend_amount": None,
                        "dividend_type": "regular",
                        "currency": "USD",
                        "data_unavailable": False,
                        "data_unavailable_reason": None,
                        "source": _bounded_source(f"SEC_XBRL_{concept_name}"),
                    }
                )

            except (ValueError, TypeError, AttributeError, KeyError) as e:
                logger.debug(f"[{symbol}] Error parsing XBRL fact: {e}")
                continue

        return results

    def _extract_total_dividends_from_xbrl_concept(
        self, symbol: str, taxonomy: dict[str, Any], concept_name: str
    ) -> list[dict[str, Any]]:
        """Extract total-dollar dividend data from a specific XBRL concept.

        Fallback-only counterpart to _extract_dividends_from_xbrl_concept above - see
        _TOTAL_DIVIDEND_CONCEPTS_GAAP/_IFRS's module comment for why this exists and why it
        populates total_dividend_amount (a direct XBRL fact) rather than deriving
        dividend_per_share (which would require dividing by shares outstanding - rejected
        as too error-prone for filers with multi-class share structures).
        """
        results: list[dict[str, Any]] = []

        if concept_name not in taxonomy:
            return results

        concept_data = taxonomy[concept_name]
        if not isinstance(concept_data, dict) or "units" not in concept_data:
            return results

        # Same earliest-filed-per-period dedup rationale as the per-share extraction above:
        # companyfacts repeats every historical fact once per filing that carries it in a
        # comparative table, and a later filing can restate the SAME period's value (e.g.
        # after a divestiture reclassifies prior-period cash flows) - the earliest-filed
        # occurrence is the figure as originally reported for that period.
        earliest_fact_by_period: dict[str, dict[str, Any]] = {}
        units_raw = concept_data.get("units") if "units" in concept_data else None
        units_data: dict[str, Any] = units_raw if isinstance(units_raw, dict) else {}
        for unit, facts_list in units_data.items():
            # Total-dollar dividend concepts use a bare currency code as the unit (e.g.
            # "USD", "BRL"), unlike the per-share concepts above which use "USD/shares" -
            # there's no per-share suffix to strip.
            if unit == "USD":
                fx_currency = None
            elif unit in MAJOR_CURRENCIES:
                fx_currency = unit
            else:
                logger.debug(
                    f"[{symbol}] {concept_name}: skipping unexpected XBRL unit '{unit}' "
                    "(expected 'USD' or a major-currency code) - not treating as total_dividend_amount"
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

                if fx_currency is not None:
                    end_for_rate = fact.get("end")
                    fx_rate = _fx_rate_cache.get_usd_rate(fx_currency, end_for_rate) if end_for_rate else None
                    if fx_rate is None or fx_rate == 0:
                        continue  # No real rate for this date - fail closed, never guess
                    value = value / fx_rate

                if abs(value) >= _MAX_PLAUSIBLE_TOTAL_DIVIDEND:
                    logger.warning(
                        f"[{symbol}] {concept_name}: skipping implausible value {value!r} "
                        "(>= 10**13, would overflow DECIMAL(15,2) column) - filer tagging error"
                    )
                    continue

                # Duration-only concept (a total paid/declared over a period), unlike the
                # per-share concepts above which can legitimately be instant facts (a
                # point-in-time declared rate) - require both bounds so a malformed/instant
                # fact under this concept doesn't get treated as a period total.
                filed_str = fact.get("filed")
                start_str = fact.get("start")
                end_str = fact.get("end")
                if not filed_str or not start_str or not end_str:
                    continue

                existing = earliest_fact_by_period.get(end_str)
                if existing is None or filed_str < existing["filed"]:
                    earliest_fact_by_period[end_str] = {**fact, "val": value}

        for fact in earliest_fact_by_period.values():
            try:
                value = fact["val"]
                filed_str = fact["filed"]
                end_str = fact["end"]

                try:
                    declaration_date = datetime.strptime(filed_str, "%Y-%m-%d").date()
                    period_end = datetime.strptime(end_str, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue

                # Same period_end + 45d ex-date anchoring convention as the per-share path
                # above - see its comment for why this estimate is a structural necessity.
                ex_dividend_date = period_end + timedelta(days=45)

                results.append(
                    {
                        "symbol": symbol,
                        "declaration_date": declaration_date,
                        "ex_dividend_date": ex_dividend_date,
                        "record_date": None,
                        "payment_date": None,
                        "dividend_per_share": None,
                        "dividend_yield_pct": None,
                        "total_dividend_amount": Decimal(str(value)),
                        "dividend_type": "regular",
                        "currency": "USD",
                        "data_unavailable": False,
                        "data_unavailable_reason": None,
                        "source": _bounded_source(f"SEC_XBRL_TOTAL_{concept_name}"),
                    }
                )

            except (ValueError, TypeError, AttributeError, KeyError) as e:
                logger.debug(f"[{symbol}] Error parsing XBRL fact: {e}")
                continue

        return results

    def _fetch_sec_data_with_timeout(self, symbol: str, timeout_sec: float = 20.0) -> dict[str, Any]:
        """Fetch SEC company facts with hard timeout enforcement.

        Uses ThreadPoolExecutor to enforce a hard timeout at the Python level,
        preventing indefinite hangs that socket timeout alone cannot catch.

        Args:
            symbol: Stock ticker
            timeout_sec: Hard timeout in seconds (default 20s per symbol)

        Returns:
            Dict with 'cik' and 'facts_response' keys

        Raises:
            RuntimeError: If timeout exceeded or API call fails
        """

        def _fetch() -> dict[str, Any]:
            cik_time = time.time()
            cik = self.sec_client.symbol_to_cik(symbol)
            cik_elapsed = time.time() - cik_time
            if cik_elapsed > 5:
                logger.warning(f"[{symbol}] symbol_to_cik took {cik_elapsed:.1f}s (slow SEC ticker endpoint)")

            facts_time = time.time()
            facts_response = self.sec_client.get_company_facts(cik)
            facts_elapsed = time.time() - facts_time
            if facts_elapsed > 10:
                logger.warning(f"[{symbol}] get_company_facts took {facts_elapsed:.1f}s (slow SEC API)")

            return {"cik": cik, "facts_response": facts_response}

        try:
            future = _API_EXECUTOR.submit(_fetch)
            result = future.result(timeout=timeout_sec)
            return result
        except FuturesTimeoutError as e:
            # BUG FIX (2026-08-17, "no SEC data" audit): a slow/rate-limited SEC response is
            # transient, not permanent - it must NOT be raised as a plain RuntimeError, which
            # fetch_incremental below (pre-fix) caught and wrote straight to the DB as a
            # permanent fetch_error unavailable record with zero real retry.
            # TransientAPIError lets it propagate through fetch_incremental to
            # OptimalLoader.load_symbol() (utils/optimal_loader.py), which retries transient
            # errors 3x with its own exponential backoff - giving the underlying SEC client's
            # own 8-attempt retry/backoff (utils/external/sec_edgar_client.py's _get_json,
            # worst case minutes) multiple fresh 20s windows to actually recover in, instead of
            # being permanently killed by the first one.
            raise TransientAPIError(
                f"[{symbol}] SEC API call exceeded {timeout_sec}s timeout. "
                f"This indicates a slow SEC server or network issue - retrying."
            ) from e
        except FileNotFoundError:
            # 404 = CIK has no XBRL filings at all (mutual funds, shells, etc. - see
            # sec_statements.py's companyfacts 404 handling for the same permanent case).
            # This is a real, permanent absence, not a fetch failure - preserve the type so
            # fetch_incremental can label it honestly instead of a scary "fetch_error".
            raise
        except ValueError:
            # FIXED 2026-08-18 (goal: "no SEC data" audit): symbol_to_cik() raises ValueError
            # ("Symbol X not found in SEC ticker cache") when a ticker isn't resolvable via
            # any of the 3 lookup methods (bulk file, dash-substitution, browse-edgar) - a
            # PERMANENT condition (SEC's own systems don't recognize the ticker at all, e.g.
            # AEP/HIFS/TOWN-class gaps - see sec_ticker_cache.py's ValueError call sites,
            # all "not found"/"missing" cases, never transient network noise). This used to
            # fall through to the generic `except Exception` below and get wrapped as
            # TransientAPIError, wasting 3 full OptimalLoader retries (each redoing the same
            # 3-method lookup that can never succeed) before finally surfacing as an opaque
            # "fetch_error:RuntimeError" - indistinguishable from a real bug. Same permanent-
            # error treatment as the FileNotFoundError case just above.
            raise
        except Exception as e:
            # Everything else reaching here is _get_json's own already-exhausted-8-retry
            # RuntimeError (429/502/503/504 or network errors that kept recurring) - transient
            # in nature (temporary SEC-side rate limiting/outage), not a permanent absence or a
            # programming bug. Same TransientAPIError treatment as the timeout case above.
            raise TransientAPIError(f"[{symbol}] SEC API error: {type(e).__name__}: {e}") from e

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Fetch dividend data for symbol from SEC XBRL companyfacts.

        Uses official XBRL concepts from 10-K/10-Q filings:
        - CommonStockDividendsPerShareDeclared / CommonStockDividendsPerShareCashPaid (us-gaap)
        - DividendsPaidOrdinarySharesPerShare / DividendsRecognisedAsDistributionsToOwnersPerShare
          (ifrs-full - foreign private issuers filing 20-F/40-F)

        Returns: Dividend records extracted from XBRL, or data_unavailable marker.

        CRITICAL: Hard timeout (20 seconds) enforced via ThreadPoolExecutor.
        Prevents indefinite hangs on slow SEC API. 2026-08-04: observed 5+ hour hang.
        """
        now_et = datetime.now(EASTERN_TZ).date()
        start_time = time.time()

        try:
            # Fetch with hard timeout to prevent hangs (socket timeout alone insufficient)
            sec_data = self._fetch_sec_data_with_timeout(symbol, timeout_sec=20.0)
            facts_response = sec_data["facts_response"]

            if not facts_response or "facts" not in facts_response:
                return [self._unavailable_record(symbol, now_et, "no_companyfacts")]

            facts = facts_response["facts"]
            if not isinstance(facts, dict):
                return [self._unavailable_record(symbol, now_et, "no_us_gaap_facts")]
            us_gaap_raw = facts.get("us-gaap")
            us_gaap: dict[str, Any] = us_gaap_raw if isinstance(us_gaap_raw, dict) else {}
            ifrs_full_raw = facts.get("ifrs-full")
            ifrs_full: dict[str, Any] = ifrs_full_raw if isinstance(ifrs_full_raw, dict) else {}
            # FIX 2026-08-18 (goal: find/fix real loader gaps): this used to bail out here
            # ("no_us_gaap_facts") whenever a filer's us-gaap taxonomy was missing/empty,
            # before ever looking at ifrs-full - permanently blocking any all-IFRS filer
            # (no us-gaap facts at all) from ever reaching the ifrs-full extraction added
            # below, even though such a filer might genuinely tag real dividend data there.
            if not us_gaap and not ifrs_full:
                # FIXED 2026-08-19 (goal: "no SEC data" audit continuation - industry-specific
                # nuance pass): registered investment companies (closed-end funds like the
                # BlackRock BBN/BCAT/BGT/BIT/BKT-class trusts) don't file a standard 10-K at
                # all - live-confirmed via SEC's own companyfacts API: BBN's `facts` dict has
                # ONLY "cef" (20 concepts) and "ffd" (5 concepts) taxonomies, no "us-gaap" or
                # "ifrs-full" whatsoever. Inspected every "cef"/"ffd" concept name live: none
                # is a dividend/distribution amount - the "cef" taxonomy is N-2 prospectus fee-
                # table data (ManagementFeesPercent, ExpenseExampleYears1to10, ...), not
                # periodic financial-statement facts. This is a genuine, permanent structural
                # absence (SEC simply has no machine-readable distribution data for these
                # filers), same class as reit_special_entity elsewhere in this codebase - not
                # a loader gap our own extraction could ever close by trying harder concepts.
                # Distinguishing it from the generic "no_us_gaap_facts" (which reads as an SEC
                # extraction failure) so it doesn't keep showing up as a "loader is broken"
                # signal on the coverage dashboard.
                if isinstance(facts.get("cef"), dict) or isinstance(facts.get("ffd"), dict):
                    return [self._unavailable_record(symbol, now_et, "registered_investment_company_no_xbrl")]
                return [self._unavailable_record(symbol, now_et, "no_us_gaap_facts")]

            results = []

            # Extract dividends from XBRL concepts
            declared = self._extract_dividends_from_xbrl_concept(
                symbol, us_gaap, "CommonStockDividendsPerShareDeclared"
            )
            paid = self._extract_dividends_from_xbrl_concept(symbol, us_gaap, "CommonStockDividendsPerShareCashPaid")

            results.extend(declared)
            results.extend(paid)

            for ifrs_concept in _IFRS_DIVIDEND_PER_SHARE_CONCEPTS:
                results.extend(self._extract_dividends_from_xbrl_concept(symbol, ifrs_full, ifrs_concept))

            # FIX 2026-08-19: total-dollar fallback (see _TOTAL_DIVIDEND_CONCEPTS_GAAP/IFRS's
            # module comment) - only tried when the filer has zero per-share results, so a
            # filer with real per-share data is never double-counted against its own total.
            if not results:
                for gaap_concept in _TOTAL_DIVIDEND_CONCEPTS_GAAP:
                    results.extend(self._extract_total_dividends_from_xbrl_concept(symbol, us_gaap, gaap_concept))
                for ifrs_concept in _TOTAL_DIVIDEND_CONCEPTS_IFRS:
                    results.extend(self._extract_total_dividends_from_xbrl_concept(symbol, ifrs_full, ifrs_concept))

            # Remove duplicates on the actual primary key (symbol, ex_dividend_date) - see
            # migration 1168, which established the real DB constraint (uq_dividend_event)
            # is this 2-column pair, not 3. This dedup used to key on
            # (symbol, ex_dividend_date, dividend_per_share): declared/paid XBRL concepts
            # both estimate the same ex-date for a given fiscal period (period_end + 45d,
            # see _extract_dividends_from_xbrl_concept below) but frequently report
            # slightly different per-share amounts, so the 3-column key let both survive
            # as "unique" and then collide in the same INSERT batch against the real
            # 2-column constraint - live-reproduced 2026-08-04 as a CardinalityViolation
            # ("ON CONFLICT DO UPDATE command cannot affect row a second time") on 608+
            # symbols, including major dividend payers (ABBV, BA, CVX, COST, CVS, CSCO).
            # `declared` is extended into `results` before `paid`, so on a same-date
            # collision the declared-dividend record wins (first occurrence kept).
            seen = set()
            unique_results = []
            for r in results:
                key = (r["symbol"], r["ex_dividend_date"])
                if key not in seen:
                    seen.add(key)
                    unique_results.append(r)

            if unique_results:
                return unique_results

            # FIX 2026-08-19 (goal session continuation - "Scores Data Coverage" dashboard
            # showed dividend_data as the single largest "Missing SEC/XBRL data" gap, 2,549
            # active symbols / 55% of the table, all "no_dividend_xbrl_concepts"). Live-sampled
            # 8 of these (AADX, AAOI, AARD, ...) directly against SEC's real companyfacts: every
            # one has a substantive us-gaap taxonomy (113-475 concepts, real NetIncomeLoss facts
            # on file) yet zero facts under ANY of the 9 dividend concepts (2 us-gaap per-share +
            # 2 ifrs per-share + 5 us-gaap/ifrs total-dollar) this loader already checks above -
            # not a case of SEC having the data under some 10th untried concept, but a company
            # that has genuinely never declared a shareholder dividend. Downstream consumers
            # (load_value_quality_growth_metrics.py's payout_ratio/dividend_yield reasons) already
            # treat this exact situation as "non_dividend_paying_stock", a legitimate business
            # fact bucketed separately from real data gaps - but they derive that label by
            # querying this same table's own output, so dividend_data mislabeling itself as a
            # generic (gap-implying) "no_dividend_xbrl_concepts" was the root of the mislabel, not
            # an independent confirmation downstream. NetIncomeLoss/ProfitLoss presence is the
            # gate: a filer thin enough to have no real income-statement facts at all genuinely
            # can't be distinguished from "we just don't have their data" and keeps the honest
            # generic reason.
            #
            # BUG FOUND 2026-08-20 (goal session: coverage root-cause audit): this gate only
            # checked 3 of the bottom-line concepts utils/external/sec_statements.py already
            # recognizes for annual_income_statement.net_income - missing us-gaap "ProfitLoss"
            # (PRI/Primerica reports zero NetIncomeLoss entries ever, using ProfitLoss as its
            # sole bottom-line tag - see sec_statements.py's 2026-08-17 fix) and the ifrs-full
            # "ProfitLossAttributableToOwnersOfParent"/"ComprehensiveIncome" aliases (ONON,
            # ATHE - see sec_statements.py's 2026-07-31 fix). Live-confirmed: 3,119 of 3,153
            # symbols (99%) carrying "no_dividend_xbrl_concepts" already have real net_income
            # in annual_income_statement - this gate was failing almost universally, leaving
            # genuine non-dividend-payers miscategorized as a "Missing SEC/XBRL data" gap
            # instead of "Legitimate / not applicable" for nearly the entire affected cohort.
            has_real_income_statement_facts = bool(
                (us_gaap.get("NetIncomeLoss") or {}).get("units")
                or (us_gaap.get("ProfitLoss") or {}).get("units")
                or (ifrs_full.get("ProfitLoss") or {}).get("units")
                or (ifrs_full.get("ProfitLossFromContinuingOperations") or {}).get("units")
                or (ifrs_full.get("ProfitLossAttributableToOwnersOfParent") or {}).get("units")
                or (ifrs_full.get("ComprehensiveIncome") or {}).get("units")
            )
            if has_real_income_statement_facts:
                return [self._unavailable_record(symbol, now_et, "non_dividend_paying_stock")]

            # No dividend data found in XBRL, and no real income-statement facts either -
            # genuinely can't tell whether this is a non-payer or a thin/unavailable filer.
            return [self._unavailable_record(symbol, now_et, "no_dividend_xbrl_concepts")]

        except TransientAPIError:
            # Must NOT be caught here as a permanent unavailable marker - propagate so
            # OptimalLoader.load_symbol()'s retry-with-backoff (utils/optimal_loader.py) gets
            # a chance to recover from what SEC-side rate limiting/timeout made look like a
            # failure. See _fetch_sec_data_with_timeout's docstring for the full mechanism.
            raise
        except FileNotFoundError:
            # CIK has no XBRL filings at all - permanent and legitimate (mutual funds, shells),
            # not a loader failure. Honest label instead of the alarming generic fetch_error.
            elapsed = time.time() - start_time
            logger.debug(f"[{symbol}] No XBRL filings on file (404) after {elapsed:.1f}s.")
            return [self._unavailable_record(symbol, now_et, "no_xbrl_filings")]
        except ValueError:
            # FIXED 2026-08-18 (goal: "no SEC data" audit): ticker not resolvable to a CIK via
            # any lookup method - permanent (see _fetch_sec_data_with_timeout's matching
            # except ValueError). Live-confirmed real cases: small bank/thrift filers (e.g.
            # HIFS - Hingham Institution for Savings) that report to the FDIC under Exchange
            # Act Section 12(i) instead of registering with the SEC, so they have no SEC CIK
            # at all, ever - not a gap this loader (SEC-only by design) can close. Honest,
            # distinct label instead of the misleading "fetch_error:RuntimeError" this used to
            # produce after 3 wasted retries.
            elapsed = time.time() - start_time
            logger.debug(f"[{symbol}] Ticker not resolvable to a CIK after {elapsed:.1f}s.")
            # BUG FOUND 2026-08-21 (same bug class as load_sec_segment_info.py /
            # load_current_reports_8k.py / load_earnings_calendar_sec.py / the analyst
            # loaders' pre-fix marker retraction fixes): a transient CIK-resolution miss
            # gets treated identically to a genuine permanent non-filer here, even for a
            # symbol with real dividend history already on record - live-confirmed VMRK
            # (real dividend_per_share rows through 2026-08-14) shadowed by a
            # "cik_not_found" marker written 2026-08-19. Reuses the same has_real_history
            # check the fetch_error branch below already has, so a transient lookup miss
            # can't clobber known-good history here either - not a silent fallback, this
            # run genuinely has nothing new to report for a symbol with real dividend
            # data_unavailable=false rows already on file, and any pre-existing
            # data_unavailable=true marker is retracted as stale.
            if self._has_real_dividend_history(symbol):
                self._retract_stale_marker(symbol)
                return []
            return [self._unavailable_record(symbol, now_et, "cik_not_found")]
        except Exception as e:
            elapsed = time.time() - start_time
            # ALWAYS log at WARNING level - this is an operator-visible issue
            logger.warning(
                f"[{symbol}] Dividend fetch failed after {elapsed:.1f}s: {type(e).__name__}: {e}. "
                f"Marking as data unavailable."
            )
            # FIXED 2026-08-20 (goal: finance-accuracy audit): _unavailable_record keys its
            # row on (symbol, ex_dividend_date=today), the real DB unique constraint - so a
            # transient failure (SEC rate limiting/timeout) writes a BRAND NEW permanent
            # garbage row every time it happens, never overwriting anything, instead of
            # updating a single "current status" record. Live-confirmed: 1,795 such rows
            # across 1,242 symbols had accumulated, including 100+ real, active dividend
            # payers (e.g. ADNT, ADP, AEE - confirmed via a real dividend_per_share row
            # coexisting with a same-symbol fetch_error marker) whose complete, correct
            # dividend history now sits in the table alongside dated "no data" noise from
            # whatever day SEC happened to time out. Downstream consumers already guard
            # against this (every payout_ratio/dividend_yield/SGR query in
            # load_value_quality_growth_metrics.py filters `data_unavailable = FALSE`), so
            # this was never live-scoring-corrupting - but it's unbounded, meaningless table
            # growth and it does affect the coverage dashboard's "reason" cross-tab, which
            # counts a symbol's raw history rather than a fixed one-row-per-symbol status.
            # A symbol with resolved, real dividend history is not made "more true" by also
            # recording that today's re-check happened to fail - so skip writing the marker
            # for those, same as OptimalLoader already treats an empty return (no real rows,
            # no marker) as "nothing new since watermark, skip" rather than an error.
            if self._has_real_dividend_history(symbol):
                logger.debug(
                    f"[{symbol}] Fetch failed but real dividend history is already on file - "
                    "not writing a spurious data_unavailable marker row."
                )
                # Not a silent fallback: this symbol's real dividend_per_share rows already
                # represent its current, correct state - a transient re-check failure has
                # nothing new to report. OptimalLoader.load_symbol() treats an empty list the
                # same as "no new data since watermark" and skips, exactly as intended here.
                # Also retract any marker already on record (2026-08-21: this branch never
                # had a retraction step either, the same latent gap as the cik_not_found
                # branch above) - a marker coexisting with confirmed real coverage is
                # always wrong.
                self._retract_stale_marker(symbol)
                return []

            return [self._unavailable_record(symbol, now_et, f"fetch_error:{type(e).__name__}")]

    @staticmethod
    def _has_real_dividend_history(symbol: str) -> bool:
        """True if this symbol already has at least one real (non-marker) dividend row."""
        from utils.db import DatabaseContext

        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    "SELECT 1 FROM dividend_data WHERE symbol = %s AND dividend_per_share IS NOT NULL LIMIT 1",
                    (symbol,),
                )
                return cur.fetchone() is not None
        except Exception as lookup_err:
            logger.debug(f"[{symbol}] Could not check existing dividend history: {lookup_err}")
            return False

    @staticmethod
    def _retract_stale_marker(symbol: str) -> None:
        """Delete any data_unavailable marker for this symbol - only called once real
        coverage is confirmed, so a marker coexisting with it is always wrong."""
        from utils.db import DatabaseContext

        with DatabaseContext("write") as cur:
            cur.execute(
                "DELETE FROM dividend_data WHERE symbol = %s AND data_unavailable = true",
                (symbol,),
            )

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
