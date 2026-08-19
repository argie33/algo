#!/usr/bin/env python3
"""SEC-Derived Valuations Loader - Replace yfinance PE/PB/PS/PEG/FCF/MarketCap.

Computes audited, current valuations from SEC financial data + price_daily:
  - PE Ratio: TTM EPS (from income statement) / Stock Price
  - PB Ratio: Book Value Per Share (from balance sheet) / Stock Price
  - PS Ratio: Revenue Per Share (from income statement) / Stock Price
  - PEG Ratio: PE Ratio / Earnings Growth Rate %
  - FCF Yield: Free Cash Flow (from cash flow statement) / Market Cap
  - Market Cap: Stock Price x Shares Outstanding (from income statement)
  - Shares Outstanding: WeightedAverageNumberOfSharesOutstandingBasic (from SEC, migration 1171),
    falling back to net_income/eps derivation, then company_info_sec, if unavailable

Data Quality:
  - All metrics computed from SEC audited data (vs. yfinance estimates)
  - Current (updated daily as prices update)
  - Explicit data_unavailable markers on computation failures (fail-fast if SEC data unavailable)
  - No fallback to yfinance (SEC data only)

Run: python3 loaders/load_sec_valuations.py [--symbols AAPL,MSFT] [--parallelism 4]
"""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.loaders.exception_handler import handle_exception, handle_invalid_data
from utils.optimal_loader import OptimalLoader
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)

# BUG FOUND 2026-08-16: total_debt/total_cash/ebitda/enterprise_value are all NUMERIC(15,2)
# columns (max abs value < 10^13, i.e. $10 trillion) but were written with no sanity bound at
# all - unlike pe_ratio/pb_ratio/ps_ratio/ev_ebitda/ev_revenue just below, which all already
# have explicit bounds. Live-confirmed: BBAR/BCH/BMA/BSAC/HDB/HMC (all foreign ADR filers -
# Argentine/Chilean/Indian/Japanese banks and companies) hit NumericValueOutOfRange on this
# exact column class, crashing the whole sec_valuations INSERT and losing every other computed
# ratio for that symbol too - same root cause and same crash-and-lose-everything failure mode
# already documented for loaders/load_value_quality_growth_metrics.py's identical
# MAX_ABSOLUTE_DOLLAR_VALUE guard (foreign filers reporting balance-sheet figures in local
# currency without USD conversion - see that file's docstring for the VFS/KEP example). This
# bound only prevents the crash symptom, same scope as that fix; the currency-conversion root
# cause is a separate, larger fix.
MAX_ABSOLUTE_DOLLAR_VALUE = 1_000_000_000_000.0  # $1 trillion - no real company exceeds this


class SecValuationsLoader(OptimalLoader):
    """Compute valuations from SEC audited data instead of yfinance estimates.

    CRITICAL: This loader replaces ~5,300 yfinance quoteSummary calls per day
    with computation from already-fetched SEC financial statements.
    Eliminates $25/month in API costs + reduces rate-limiting risk.
    """

    table_name = "sec_valuations"
    primary_key = ("symbol",)
    watermark_field = "computed_at"
    exclude_etfs_from_symbols = True

    # Sanity floor for the "search all fiscal years" share-count fallbacks below. Real SEC
    # XBRL data occasionally contains a single implausible outlier entry for a concept (live-
    # confirmed: ERIE's WeightedAverageNumberOfDilutedSharesOutstanding has exactly one
    # reported value across its whole filing history, 2542 shares, for a multi-billion-dollar
    # company that has millions of shares outstanding - almost certainly a filer tagging
    # error). Every real US-listed operating company has at least this many shares
    # outstanding, so this floor rejects that class of bad data without excluding real
    # micro-caps.
    MIN_PLAUSIBLE_SHARES_OUTSTANDING = 100_000

    # FIXED 2026-08-18 (goal session, currency-poisoned-row cleanup follow-up): live-crashed
    # via NMR (Nomura Holdings, a JPY-reporting IFRS filer - JPY is FX-CONVERTED not rejected
    # outright, unlike KRW/VND above, since it's in MAJOR_CURRENCIES): the derived-shares-out
    # fallback (`shares = net_income / eps`, just below) computed 2,942,280,410,000,000 shares
    # - a currency-scale mismatch between net_income (converted) and eps (apparently not
    # converted the same way, or converted with a different effective scale) produced an
    # absurd ratio. NUMERIC(15,0) couldn't even hold the value, aborting the whole COPY batch
    # (1 bad symbol out of 15 failed the whole run's 5% error threshold, rolling back all 15 -
    # not just NMR). The existing MIN floor above catches implausibly-small outliers; nothing
    # caught implausibly-LARGE ones. No real company (even the most share-heavy real large-caps
    # after multiple splits) has anywhere near 100 billion shares outstanding - this ceiling is
    # generous enough to never reject a genuine value while catching this and any similar
    # future currency/scale-mismatch derivation error before it ever reaches the DB.
    MAX_PLAUSIBLE_SHARES_OUTSTANDING = 100_000_000_000

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:  # noqa: C901 -- pre-existing complexity debt, not introduced by this change; CI ruff-gate cleanup pass 2026-08-11
        """Compute SEC-derived valuations for one symbol.

        Returns:
            List with single valuation dict or data_unavailable marker
        """
        try:
            # Fetch latest financial data for symbol
            with DatabaseContext("read") as cur:
                # Get income statement data from most recent annual filing
                # CRITICAL: Use NULL checks instead of COALESCE(col, 0) to detect missing financial data
                # Defaulting to 0 for revenue/EPS would cause wrong valuations (zero division, phantom metrics)
                # NOTE: Removed data_unavailable = FALSE filter to prevent premature early exit
                # FIXED: plain `ORDER BY fiscal_year DESC` picked the latest fiscal year even when
                # it's a partial/estimate-stage filing with NULL revenue AND NULL EPS, while an
                # older year has real data - same "latest year is empty" bug class as the FCF fix
                # in load_value_quality_growth_metrics.py. Live-confirmed: MC (Moelis), CLSK
                # (CleanSpark), FRD (Friedman Industries) all have real revenue/net_income one
                # fiscal year back but were failing "income_statement_revenue_and_eps_null" on the
                # latest year alone. Prioritizing rows with revenue or EPS present, then by
                # fiscal_year DESC, still returns two genuinely consecutive fiscal years for the
                # prior_year_eps growth-rate calc below (whichever two are most recent AND usable).
                cur.execute(
                    """
                    SELECT
                        fiscal_year,
                        revenue,
                        net_income,
                        earnings_per_share,
                        operating_income,
                        pretax_income,
                        depreciation_expense,
                        amortization_expense,
                        shares_outstanding_basic,
                        income_tax_expense
                    FROM annual_income_statement
                    WHERE symbol = %s
                    ORDER BY (CASE WHEN revenue IS NOT NULL OR earnings_per_share IS NOT NULL OR net_income IS NOT NULL THEN 0 ELSE 1 END), fiscal_year DESC
                    LIMIT 2
                    """,
                    (symbol,),
                )
                income_rows = cur.fetchall()
                if not income_rows:
                    return [self._unavailable_marker(symbol, "no_income_statement")]

                (
                    ttm_fiscal_year,
                    ttm_revenue,
                    _ttm_net_income,
                    ttm_eps_basic,
                    operating_income,
                    pretax_income,
                    depreciation_expense,
                    amortization_expense,
                    reported_shares_outstanding,
                    income_tax_expense,
                ) = income_rows[0]

                # FIXED 2026-08-18 (goal: "no SEC data" audit): the ORDER BY above ranks a row
                # tier-0 if ANY of revenue/EPS/net_income is present - not specifically revenue -
                # so a filer whose latest fiscal year has a real net_income but a not-yet-tagged
                # revenue figure (common for a just-filed/preliminary period) wins the tiebreak
                # over an older row that has real, complete revenue. ttm_revenue then comes back
                # None even though a usable figure exists one row back, silently killing
                # ev_revenue/ps_ratio. Live-confirmed CRAI (CRA International, ~$750M/year real
                # revenue): FY2026 row has net_income=$54.8M but revenue=NULL and won tier 0,
                # masking FY2025's real revenue=$751.58M sitting in income_rows[1]. A universe-
                # wide scan found 723 symbols where the anchor row has this exact NULL-revenue-
                # but-real-EPS-or-net-income shape. Only income_rows[1] (already fetched, no
                # extra query) is checked - same small-window "same-year-substitute" fallback
                # already used elsewhere in this codebase (e.g. roic_pct's long_term_debt
                # fallback), not an unbounded historical search.
                if ttm_revenue is None and len(income_rows) > 1 and income_rows[1][1] is not None:
                    ttm_revenue = income_rows[1][1]

                # FIXED 2026-08-18: earnings_per_share suffers the identical "premature fiscal
                # year stub" gap as revenue just above - same anchor row, same root cause (a
                # filer whose latest fiscal year has real net_income but EPS not yet tagged).
                # Live-confirmed HG (Hamilton Insurance Group): FY2026 row has real
                # net_income=$217.032M but earnings_per_share=NULL, while FY2025 one row back
                # has a real earnings_per_share=$5.75 - pe_ratio/peg_ratio came back "SEC data
                # not available" even though growth_metrics elsewhere in the pipeline computes
                # EPS growth fine from the same underlying annual_income_statement data.
                # Track which fiscal year actually supplied ttm_eps_basic - prior_year_eps below
                # must come from a year OLDER than that one, never the same year twice (see the
                # PEG double-counting bug this exact shape caused once already, warned about in
                # the comment right below).
                ttm_eps_fiscal_year = ttm_fiscal_year
                eps_substituted_from_row1 = False
                if ttm_eps_basic is None and len(income_rows) > 1 and income_rows[1][3] is not None:
                    ttm_eps_basic = income_rows[1][3]
                    ttm_eps_fiscal_year = income_rows[1][0]
                    eps_substituted_from_row1 = True

                # FIXED 2026-08-18: operating_income/pretax_income suffer the identical anchor-row
                # stub gap as revenue and earnings_per_share above. Live-confirmed HG (Hamilton
                # Insurance Group): FY2026 (anchor) has BOTH operating_income=NULL and
                # pretax_income=NULL (neither tagged yet in the premature filing), while FY2025
                # one row back has a real pretax_income=$824.905M. Neither of the two existing
                # operating_income fallbacks just below can help here - both depend on THIS row's
                # own pretax_income/income_tax_expense, which are equally missing. This was
                # previously mis-diagnosed (see missing_factor_inputs_audit_20260818 memory) as
                # "not an independent bug, a downstream cascade of genuine per-fiscal-year gaps" -
                # it's actually the same anchor-row-timing bug already fixed for revenue/EPS above,
                # just not yet recognized as such. Substitute the WHOLE income_rows[1] set together
                # (operating_income, pretax_income, D&A) rather than mixing fields from two
                # different fiscal years, which would produce an internally inconsistent EBITDA.
                # Only fires when BOTH anchor-row income-statement figures are missing - a filer
                # with a real anchor-row pretax_income but genuinely no operating_income tag (the
                # normal financial-services case the fallback below already handles) is untouched.
                if operating_income is None and pretax_income is None and len(income_rows) > 1:
                    operating_income = income_rows[1][4]
                    pretax_income = income_rows[1][5]
                    depreciation_expense = income_rows[1][6]
                    amortization_expense = income_rows[1][7]

                # FIXED 2026-08-06: Financial services companies (banks, insurance, investment firms)
                # don't report operating_income - they report pretax_income instead. Use pretax_income
                # as fallback for EBITDA calculation in these cases. This recovers ~22% of missing
                # operating_income in the universe (e.g. JPM, BAC, PNC all have pretax_income but no
                # operating_income). Live-confirmed: JPMorgan FY2024 pretax_income=75.08B, uses this
                # fallback to compute EBITDA for EV/EBITDA ratio.
                if operating_income is None and pretax_income is not None:
                    operating_income = pretax_income
                    logger.debug(
                        f"[{symbol}] Using pretax_income as operating_income fallback (financial services company)"
                    )
                elif operating_income is None and income_tax_expense is not None and _ttm_net_income is not None:
                    # Fallback #2: Compute operating_income from net_income + taxes if available
                    # Some insurance/financial companies report net_income and taxes but not pretax_income
                    try:
                        computed_oi = _ttm_net_income + income_tax_expense
                        if computed_oi > 0:
                            operating_income = computed_oi
                            logger.debug(
                                f"[{symbol}] Computed operating_income from net_income + taxes (insurance company fallback)"
                            )
                    except (TypeError, ValueError):
                        pass  # If computation fails, leave operating_income=None
                # PEG's growth-rate leg needs a genuinely prior-year EPS, not the same TTM
                # value used twice - GOVERNANCE: this used to set `latest_eps = ttm_eps_basic`
                # (comment literally said "Use same EPS for both TTM and latest"), which made
                # _compute_valuations()'s growth_rate = (ttm_eps - latest_eps)/abs(latest_eps)
                # always exactly 0 for every symbol, so peg_ratio silently never populated
                # anywhere in the system with no marker flagging PEG specifically as broken.
                # A missing second fiscal year (new filer, gap) leaves it None, which
                # _compute_valuations already handles by leaving peg_ratio NULL.
                if len(income_rows) > 1 and not eps_substituted_from_row1:
                    prior_year_eps = income_rows[1][3]  # Index 3 = earnings_per_share
                elif eps_substituted_from_row1:
                    # income_rows[1] was itself consumed above as the ttm_eps substitute (the
                    # premature-stub case) - re-fetch a genuinely older year rather than reuse it.
                    cur.execute(
                        """
                        SELECT earnings_per_share FROM annual_income_statement
                        WHERE symbol = %s AND fiscal_year < %s AND earnings_per_share IS NOT NULL
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol, ttm_eps_fiscal_year),
                    )
                    older_eps_row = cur.fetchone()
                    prior_year_eps = older_eps_row[0] if older_eps_row else None
                else:
                    prior_year_eps = None

                # Validate critical fields are not NULL (fail-fast if SEC data incomplete)
                # Allow revenue-only companies: can compute PS ratio even without EPS. Also
                # allow net_income-only companies (live-confirmed: PFLT/PennantPark - a BDC
                # reporting NetInvestmentIncome instead of Revenue/EPS under an entirely
                # separate XBRL taxonomy; TRAX/FRNM - pre-revenue biotechs with real
                # net_income but no EPS tagged) to proceed: _compute_valuations already
                # handles ttm_revenue=None (skips PS) and ttm_eps=None (skips PE)
                # gracefully per-field, and PB/EV/FCF-yield don't depend on either at all -
                # the only real requirement is SOME income-statement signal to work with.
                if ttm_revenue is None and ttm_eps_basic is None and _ttm_net_income is None:
                    return [self._unavailable_marker(symbol, "income_statement_revenue_and_eps_null")]

                # Prefer the real, officially-reported weighted-average basic share count
                # (SEC XBRL WeightedAverageNumberOfSharesOutstandingBasic, migration 1171)
                # over the derived net_income/eps proxy below - EPS is reported rounded to
                # 2 decimals, so back-computing shares from it loses real precision (material
                # for large-caps with billions of shares). FIXED 2026-07-28: this concept was
                # fetched from SEC every run but silently discarded (see sec_statements.py),
                # so the derived proxy ran unconditionally despite this docstring's own claim
                # (line 11 above) that the real concept was already the source.
                # Apply the same plausibility floor as the fallback tiers below (see
                # MIN_PLAUSIBLE_SHARES_OUTSTANDING) - live-confirmed AIAI reports a real,
                # non-NULL shares_outstanding_basic of 1000 for its latest fiscal year (a
                # pre-float/shell-stage founder-share figure, not a data-fetch bug), which
                # produced a nonsensical ~$4,900 market cap when trusted directly. The
                # fallback tiers already guard against this class of bad data; the primary
                # reported value needs the same guard.
                shares_out = None
                if (
                    reported_shares_outstanding
                    and self.MIN_PLAUSIBLE_SHARES_OUTSTANDING
                    < reported_shares_outstanding
                    < self.MAX_PLAUSIBLE_SHARES_OUTSTANDING
                ):
                    shares_out = float(reported_shares_outstanding)
                    logger.debug(f"[{symbol}] Using reported shares_outstanding_basic: {shares_out:,.0f}")

                # Fallback: compute shares outstanding from SEC financial data: shares = net_income / eps.
                # If both net_income and eps are available, we can compute shares directly from SEC audited data.
                # This mathematically reconstructs whatever share count the filer itself used
                # to compute EPS - if that was the same implausible pre-float figure rejected
                # above (live-confirmed: AIAI's derived value is ~1000, matching its rejected
                # reported shares_outstanding_basic exactly), the same floor must apply here too.
                if not shares_out and ttm_eps_basic and ttm_eps_basic != 0 and _ttm_net_income and _ttm_net_income != 0:
                    try:
                        # Shares = Net Income / EPS (mathematical identity from SEC financial statements)
                        derived_shares_out = abs(float(_ttm_net_income) / float(ttm_eps_basic))
                        if (
                            self.MIN_PLAUSIBLE_SHARES_OUTSTANDING
                            < derived_shares_out
                            < self.MAX_PLAUSIBLE_SHARES_OUTSTANDING
                        ):
                            shares_out = derived_shares_out
                            logger.debug(
                                f"[{symbol}] Computed shares_outstanding from income_statement: {shares_out:,.0f}"
                            )
                    except (ValueError, ZeroDivisionError):
                        pass  # If computation fails, shares_out stays None and we fail below

                # Fallback: the LIMIT 2 rows above are the two most recent fiscal years, but
                # the most recent one is often a partial/estimate-stage filing with NULL
                # shares_outstanding_basic even though an older year has the real reported
                # value (same "latest year is empty" issue fixed for free_cash_flow in
                # load_value_quality_growth_metrics.py - live-confirmed for GPRO/JOUT/CWH/etc,
                # where FY2026 is NULL but FY2025 has a real share count). Search all fiscal
                # years, not just the two most recent, before falling back to company_info_sec.
                if not shares_out:
                    cur.execute(
                        """
                        SELECT shares_outstanding_basic FROM annual_income_statement
                        WHERE symbol = %s AND shares_outstanding_basic > %s AND shares_outstanding_basic < %s
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol, self.MIN_PLAUSIBLE_SHARES_OUTSTANDING, self.MAX_PLAUSIBLE_SHARES_OUTSTANDING),
                    )
                    prior_shares_row = cur.fetchone()
                    if prior_shares_row and prior_shares_row[0]:
                        shares_out = float(prior_shares_row[0])
                        logger.debug(
                            f"[{symbol}] Using shares_outstanding_basic from an older fiscal year: {shares_out:,.0f}"
                        )

                # If computation didn't work, try fetching from company_info_sec as fallback
                if not shares_out:
                    cur.execute(
                        """
                        SELECT shares_outstanding FROM company_info_sec
                        WHERE symbol = %s AND shares_outstanding > %s AND shares_outstanding < %s
                        ORDER BY filing_date DESC LIMIT 1
                        """,
                        (symbol, self.MIN_PLAUSIBLE_SHARES_OUTSTANDING, self.MAX_PLAUSIBLE_SHARES_OUTSTANDING),
                    )
                    shares_row = cur.fetchone()
                    if shares_row and shares_row[0]:
                        shares_out = safe_float(shares_row[0], f"{symbol}.shares_outstanding", allow_none=False)
                        logger.debug(f"[{symbol}] Fetched shares_outstanding from company_info_sec: {shares_out:,.0f}")

                # Last-resort fallback: the diluted share count (migration 1192). Some real
                # operating companies (live-confirmed: JOUT/Johnson Outdoors, 44 real 10-K
                # entries) only ever tag WeightedAverageNumberOfDilutedSharesOutstanding in
                # SEC XBRL, never the basic variant - every fallback above depends on basic
                # (directly or via the company_info_sec/net_income/eps proxies) and comes up
                # empty for these filers. Diluted is a real reported count, just not the
                # exact same measure as basic (differs by dilutive securities outstanding).
                if not shares_out:
                    cur.execute(
                        """
                        SELECT shares_outstanding_diluted FROM annual_income_statement
                        WHERE symbol = %s AND shares_outstanding_diluted > %s AND shares_outstanding_diluted < %s
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol, self.MIN_PLAUSIBLE_SHARES_OUTSTANDING, self.MAX_PLAUSIBLE_SHARES_OUTSTANDING),
                    )
                    diluted_shares_row = cur.fetchone()
                    if diluted_shares_row and diluted_shares_row[0]:
                        shares_out = float(diluted_shares_row[0])
                        logger.debug(
                            f"[{symbol}] Using shares_outstanding_diluted (no basic count reported): {shares_out:,.0f}"
                        )

                # Final fallback: the SEC cover-page share count (migration 1195). Some real
                # operating companies (live-confirmed: GEF/Greif 19yrs, DGICA/Donegal Group
                # 18yrs, MC/Moelis 15yrs of real net_income) tag NO weighted-average or
                # CommonStockShares* concept at all in their us-gaap facts - the only
                # share-count data SEC XBRL has for them is the universal
                # dei:EntityCommonStockSharesOutstanding cover-page fact. Restricted to
                # domestic filing forms only inside sec_statements.py's _aggregate_concepts
                # (foreign 20-F/40-F filers report this in local/home-market units with no
                # ADS-ratio conversion - see that file's removed-IFRS-concept comment for the
                # exact 100-1000x-wrong-market-cap trap this avoids repeating).
                if not shares_out:
                    cur.execute(
                        """
                        SELECT shares_outstanding_dei FROM annual_income_statement
                        WHERE symbol = %s AND shares_outstanding_dei > %s AND shares_outstanding_dei < %s
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol, self.MIN_PLAUSIBLE_SHARES_OUTSTANDING, self.MAX_PLAUSIBLE_SHARES_OUTSTANDING),
                    )
                    dei_shares_row = cur.fetchone()
                    if dei_shares_row and dei_shares_row[0]:
                        shares_out = float(dei_shares_row[0])
                        logger.debug(
                            f"[{symbol}] Using shares_outstanding_dei cover-page count (no us-gaap share concept reported): {shares_out:,.0f}"
                        )

                # Fail if still no shares outstanding available
                if not shares_out or shares_out <= 0:
                    return [self._unavailable_marker(symbol, "shares_outstanding_unavailable")]

                # Get current price for valuation computations
                cur.execute(
                    """
                    SELECT close FROM price_daily
                    WHERE symbol = %s AND close IS NOT NULL AND close > 0
                    ORDER BY date DESC LIMIT 1
                    """,
                    (symbol,),
                )
                price_row = cur.fetchone()
                if not price_row or not price_row[0]:
                    return [self._unavailable_marker(symbol, "no_recent_price")]

                current_price = safe_float(price_row[0], f"{symbol}.close", allow_none=False)
                if current_price <= 0:
                    return [self._unavailable_marker(symbol, "invalid_price")]

                # Get latest balance sheet (book value - optional, may not exist for all companies)
                # NOTE: Removed data_unavailable = FALSE filter to allow fallback computation
                # FIXED 2026-08-17: added "AND fiscal_year IS NOT NULL" - Postgres's DESC
                # ordering defaults to NULLS FIRST, so a stray NULL-fiscal_year row (e.g. a
                # crash-marker placeholder - see load_financial_statements.py's 2026-08-17 fix
                # comment for how one of these got written 4,948 times in a single bad run)
                # would silently outrank real, recent data here. Defensive: this loader doesn't
                # write such rows itself, but every "latest fiscal year" query reading a table
                # another loader also writes to should not trust that no NULL key ever lands
                # there.
                # FIXED 2026-08-18 (goal: "no SEC data"/loader audit): this was still a plain
                # `ORDER BY fiscal_year DESC LIMIT 1` with no regard for whether that year's
                # stockholders_equity was actually populated - the exact "latest year is empty"
                # bug class already fixed in this same file for the debt/income-statement/
                # shares_outstanding queries (see test_sec_valuations_debt_query_prefers_
                # populated_fiscal_year.py), just never applied here. Live-confirmed: AA has real
                # stockholders_equity=$5.157B for FY2024 but NULL for FY2025/FY2026 (in-progress/
                # unfiled years); ADM/AAON are NULL across every year on file for a different
                # reason (NCI-inclusive equity concept, separately fixed) but would hit this same
                # blind-latest-year trap once backfilled. pb_ratio silently went "missing_sec_data"
                # for 1,225 symbols as a result. Same CASE-based prioritization as the debt query:
                # prefer a fiscal year with a real reported value, only falling back to the bare
                # latest year (still correctly NULL) for companies with no balance sheet history.
                cur.execute(
                    """
                    SELECT stockholders_equity
                    FROM annual_balance_sheet
                    WHERE symbol = %s AND fiscal_year IS NOT NULL
                    ORDER BY (CASE WHEN stockholders_equity IS NOT NULL THEN 0 ELSE 1 END), fiscal_year DESC
                    LIMIT 1
                    """,
                    (symbol,),
                )
                balance_row = cur.fetchone()
                book_value = balance_row[0] if balance_row else None
                # Note: book_value can be None for companies without balance sheets - PB ratio will be NULL

                # Get latest cash flow (for FCF - optional, may not exist for all companies)
                # NOTE: Removed data_unavailable = FALSE filter to allow partial computation
                # See the fiscal_year IS NOT NULL comment on the balance sheet query above.
                # FIXED 2026-08-18 (goal: DCF/margin-of-safety coverage): also fetch the prior
                # 2 fiscal years' OCF/CapEx so the DCF can fall back to a 3-year average FCF
                # when the latest year alone is negative - a single capex-heavy or cash-flow-
                # lumpy year (common for cyclical/capital-intensive real businesses) was
                # unconditionally killing the DCF even when the company is normally FCF-
                # positive. Live-confirmed: of the 2,305 universe symbols with
                # margin_of_safety_unavailable_reason='negative_free_cash_flow', 443 have a
                # positive 3yr-average FCF despite a negative latest year. fcf_yield (below)
                # deliberately keeps using only the latest year - that metric is meant to
                # reflect current cash generation, not a smoothed figure; only the DCF's
                # normalization changes.
                cur.execute(
                    """
                    SELECT operating_cash_flow, capex, dividends_paid
                    FROM annual_cash_flow
                    WHERE symbol = %s AND fiscal_year IS NOT NULL
                    ORDER BY fiscal_year DESC LIMIT 3
                    """,
                    (symbol,),
                )
                cash_rows = cur.fetchall()
                ocf, capex, dividends_paid = cash_rows[0] if cash_rows else (None, None, None)
                # Note: None values here mean FCF yield/dividend yield will be NULL (not available)
                yearly_fcfs = [
                    float(row_ocf) - float(row_capex)
                    for row_ocf, row_capex, _ in cash_rows
                    if row_ocf is not None and row_capex is not None
                ]
                avg_fcf_fallback = sum(yearly_fcfs) / len(yearly_fcfs) if len(yearly_fcfs) >= 2 else None

                # Get debt and cash from balance sheet (for Enterprise Value)
                # NOTE: Removed data_unavailable = FALSE filter to allow partial computation
                #
                # FIXED 2026-08-17 (migration 1204): this query used to select total_liabilities
                # as "total_debt" - live-confirmed against real SEC data and the local DB this
                # was total_liabilities verbatim (AAPL FY2025: $285.5B "debt" vs real
                # long_term_debt $90.7B, a ~3.1x overstatement; same pattern for MSFT/GOOGL/F).
                # total_liabilities includes every non-debt liability (accounts payable,
                # deferred revenue, accrued expenses, pensions, leases) -
                # load_value_quality_growth_metrics.py's ROIC code already explicitly rejected
                # a "total_liabilities - current_liabilities" debt estimate for exactly this
                # reason, not realizing sec_valuations.total_debt (which it treats as "the real
                # number, 81% available" and prefers over this same table's own long_term_debt
                # column) was an even less accurate version of the same mistake. Now sums the
                # two real debt columns instead: long_term_debt (existing) + short_term_debt
                # (new, migration 1204 - commercial paper / short-term borrowings, not captured
                # by long_term_debt).
                #
                # FIXED 2026-08-17 (migration 1205, same session): also add post-ASC 842
                # capitalized lease liabilities - operating_lease_liability (S&P/Moody's
                # "adjusted debt" convention - both rating agencies capitalize operating
                # leases into adjusted debt for credit analysis) and finance_lease_liability
                # (unambiguously debt - financed asset ownership). Neither was captured by
                # long_term_debt/short_term_debt (live-confirmed via AAPL's real companyfacts
                # JSON - LongTermDebt does not include either lease figure). NULL only when
                # ALL FOUR components are absent (no fabricated $0 default - same fail-fast
                # convention as the rest of this file); otherwise sums whichever components
                # are present, treating a missing individual component as 0 (a filer with
                # real long_term_debt but no leases has real total_debt, not NULL).
                # See the fiscal_year IS NOT NULL comment on the book_value query above.
                #
                # FIXED 2026-08-17 (loader-review goal, continuation): plain `ORDER BY
                # fiscal_year DESC` picked the latest fiscal year even when its long_term_debt
                # is NULL because that year's filing is still in progress, while an older year
                # has the real reported value - same "latest year is empty" bug class already
                # fixed above for the income-statement/shares_outstanding queries in this file.
                # Live-confirmed: GOOGL's FY2026 row has real stockholders_equity/
                # total_liabilities/cash (a genuine, non-placeholder row) but long_term_debt is
                # NULL, while FY2025 has real long_term_debt=$49.085B - short_term_debt alone
                # being 0 (not NULL) on the FY2026 row meant the old "all four components NULL"
                # check never caught this, silently producing total_debt=None for a symbol with
                # 10 years of real debt history. Prioritizing fiscal years where long_term_debt
                # is populated (same primary-signal convention as the shares_outstanding
                # fallback chain above) before falling back to fiscal_year DESC alone. Cash is
                # queried separately (plain latest-fiscal-year, same as book_value/cash_row
                # above) so its freshness isn't coupled to debt-field completeness - GOOGL's
                # FY2026 cash figure is real and shouldn't be held back a year just because
                # that year's debt tags aren't filed yet.
                #
                # FIXED 2026-08-18 (goal: "no SEC data" audit, roic_pct/total_debt follow-up):
                # the CASE tier above only checked long_term_debt specifically - a filer that
                # NEVER tags long_term_debt in any fiscal year (real, debt-light companies that
                # only carry short-term/lease liabilities) fell through to plain `fiscal_year
                # DESC`, picking the latest year even when an older year has a real component
                # this query would otherwise use. Live-confirmed: ANET (Arista Networks) has
                # long_term_debt NULL in every fiscal year on file, but FY2024 reports a real
                # operating_lease_liability ($59.6M) - the old query picked FY2026/FY2025
                # (all four components NULL, both being more recent) over FY2024, producing
                # total_debt=None for a symbol with a real, computable debt figure. 522 of the
                # universe's 1,060 NULL total_debt symbols have this same "some year has a real
                # component, just not long_term_debt, and not the latest year" shape. Widened
                # the CASE tier to prefer any year with any of the four components present.
                # FIXED 2026-08-19 (pb_ratio/total_debt "latest year is empty" follow-up):
                # was a plain `ORDER BY fiscal_year DESC LIMIT 1` with no regard for whether
                # that year's cash_and_equivalents was actually populated - the same bug class
                # already fixed for book_value/debt/ebitda/revenue/eps in this file, just never
                # applied here. Live-confirmed: JACK (Jack in the Box) has real
                # cash_and_equivalents=$68.1M for FY2025 but NULL for FY2026 (in-progress/
                # unfiled year) - the old query picked the NULL FY2026 row and total_cash/
                # cash_per_share silently went "missing_sec_data" for 91 universe symbols as a
                # result. Same CASE-based prioritization as the sibling queries: prefer a fiscal
                # year with a real reported value, only falling back to the bare latest year
                # (still correctly NULL) for companies with no balance sheet history.
                cur.execute(
                    """
                    SELECT cash_and_equivalents
                    FROM annual_balance_sheet
                    WHERE symbol = %s AND fiscal_year IS NOT NULL
                    ORDER BY (CASE WHEN cash_and_equivalents IS NOT NULL THEN 0 ELSE 1 END), fiscal_year DESC
                    LIMIT 1
                    """,
                    (symbol,),
                )
                cash_row2 = cur.fetchone()
                total_cash = cash_row2[0] if cash_row2 else None

                # FIXED 2026-08-18 (total_debt "missing_sec_data" follow-up, AA live-confirmed):
                # the tier-0 condition above ("any component IS NOT NULL") treats a lone real
                # `0` value as evidence a fiscal year has debt data - but an in-progress fiscal
                # year can report a genuine `short_term_debt=0` (e.g. no new short-term
                # borrowings filed yet) while its real long_term_debt/lease figures simply
                # haven't been tagged yet, so it wrongly ties tier 0 with a fuller prior year
                # and wins on `fiscal_year DESC`. Live-confirmed: AA's FY2026 row is
                # (long_term_debt=NULL, short_term_debt=0, leases=NULL) - old query picked it
                # over FY2025's real (long_term_debt=$2.439B, short_term_debt=$9M,
                # operating_lease=$308M), producing a summed total_debt of exactly 0, which the
                # `if total_debt else None` truthy check below then silently collapsed to None.
                # 107 universe symbols DB-confirmed hit this same "selected year sums to exactly
                # 0 despite having a real non-NULL component" shape. Added a new top tier that
                # prefers any fiscal year whose components actually sum to something nonzero;
                # the existing "any non-NULL component" tier now only matters as a fallback for
                # genuinely zero-debt companies (real, all-zero-or-NULL years), and the fixed
                # `is not None` check below preserves that legitimate total_debt=0.0 instead of
                # coercing it to None.
                cur.execute(
                    """
                    SELECT
                        long_term_debt,
                        short_term_debt,
                        operating_lease_liability,
                        finance_lease_liability
                    FROM annual_balance_sheet
                    WHERE symbol = %s AND fiscal_year IS NOT NULL
                    ORDER BY (CASE
                                WHEN COALESCE(long_term_debt, 0) + COALESCE(short_term_debt, 0)
                                     + COALESCE(operating_lease_liability, 0)
                                     + COALESCE(finance_lease_liability, 0) != 0
                                THEN 0
                                WHEN long_term_debt IS NOT NULL OR short_term_debt IS NOT NULL
                                     OR operating_lease_liability IS NOT NULL
                                     OR finance_lease_liability IS NOT NULL
                                THEN 1
                                ELSE 2
                              END), fiscal_year DESC
                    LIMIT 1
                    """,
                    (symbol,),
                )
                debt_row = cur.fetchone()
                if debt_row:
                    debt_components = debt_row
                    if all(c is None for c in debt_components):
                        total_debt = None
                    else:
                        total_debt = sum(c or 0 for c in debt_components)
                else:
                    total_debt = None
                # Note: None values mean EV metrics won't be computed

                # Session 398: Calculate EBITDA from operating income + depreciation + amortization
                # EBITDA = Operating Income + Depreciation + Amortization
                # Use operating income as base; add D&A if available (even if just one of them)
                ebitda = None
                oi = safe_float(operating_income, f"{symbol}.operating_income", allow_none=True)
                if oi is not None:
                    dep_exp = safe_float(depreciation_expense, f"{symbol}.depreciation_expense", allow_none=True)
                    amort_exp = safe_float(amortization_expense, f"{symbol}.amortization_expense", allow_none=True)

                    # Start with operating income as EBITDA base
                    ebitda_val = oi
                    if dep_exp:
                        ebitda_val += dep_exp
                    if amort_exp:
                        ebitda_val += amort_exp

                    # Set EBITDA - always use it if operating income is available
                    ebitda = ebitda_val

            # Compute valuations (convert all values to float)
            # CRITICAL: Don't convert None to 0.0 - need to preserve None for PS ratio computation
            # If revenue is None, _compute_valuations will skip PS ratio (but that's OK)
            return [
                self._compute_valuations(
                    symbol,
                    float(current_price),
                    float(shares_out),
                    float(ttm_eps_basic) if ttm_eps_basic else None,
                    float(ttm_revenue) if ttm_revenue else None,  # Changed from 0.0 to None
                    float(book_value) if book_value else None,
                    float(ocf) if ocf else 0.0,
                    float(capex) if capex else 0.0,
                    float(prior_year_eps) if prior_year_eps else None,
                    float(dividends_paid) if dividends_paid else None,
                    # FIXED 2026-08-18 (AA live-confirmed): `if total_debt else None` treated a
                    # genuine 0.0 (a real, fully zero-debt fiscal year) as falsy, silently
                    # discarding it the same way a missing value would be - `is not None` is the
                    # correct check here, same fix class as the SQL tier change just above.
                    float(total_debt) if total_debt is not None else None,
                    float(total_cash) if total_cash else None,
                    float(ebitda) if ebitda else None,
                    avg_fcf_fallback,
                )
            ]

        except TimeoutError as e:
            marker = handle_exception(symbol, e, "querying SEC financial data")
            return [marker]
        except (KeyError, IndexError) as e:
            # Schema or data structure issue
            marker = handle_exception(symbol, e, "parsing SEC financial data")
            return [marker]
        except ValueError as e:
            # Data validation or conversion error
            marker = handle_invalid_data(symbol, e, "computing valuations")
            return [marker]
        except Exception as e:
            # Try to classify and handle, or fail-fast if truly unexpected
            marker = handle_exception(symbol, e, "computing valuations")
            return [marker]

    # DCF constants (migration 1208, Value factor goal 2026-08-17)
    DCF_DISCOUNT_RATE = 0.10
    DCF_TERMINAL_GROWTH_RATE = 0.025
    DCF_GROWTH_FLOOR = -0.10
    DCF_GROWTH_CEILING = 0.15
    DCF_FORECAST_YEARS = 5
    MAX_INTRINSIC_VALUE_PER_SHARE = 1_000_000.0  # $1M/share - no real per-share DCF exceeds this

    def _compute_dcf_intrinsic_value(
        self,
        symbol: str,
        fcf: float | None,
        eps_growth_pct: float | None,
        shares_out: float | None,
        current_price: float | None,
    ) -> tuple[float | None, float | None]:
        """Two-stage FCFE DCF: 5-year explicit forecast of `fcf` grown at `eps_growth_pct`
        (clamped to [DCF_GROWTH_FLOOR, DCF_GROWTH_CEILING]/yr), discounted at
        DCF_DISCOUNT_RATE, plus a Gordon Growth terminal value at DCF_TERMINAL_GROWTH_RATE,
        divided by shares_out.

        Returns (intrinsic_value_per_share, margin_of_safety_pct) - both None when fcf/
        shares_out/current_price aren't usable or the result is implausible. A missing/
        unusable eps_growth_pct defaults to flat 0%/yr rather than skipping the DCF entirely:
        FCF, shares, and price are the primary drivers and are independently available even
        when EPS history isn't (unlike peg_ratio, which requires a positive prior_year_eps to
        be meaningful at all).
        """
        if (
            fcf is None
            or fcf <= 0
            or shares_out is None
            or shares_out <= 0
            or current_price is None
            or current_price <= 0
        ):
            return None, None

        growth_rate = 0.0 if eps_growth_pct is None else eps_growth_pct / 100.0
        growth_rate = max(self.DCF_GROWTH_FLOOR, min(self.DCF_GROWTH_CEILING, growth_rate))

        pv_explicit = 0.0
        fcf_year = fcf
        for year in range(1, self.DCF_FORECAST_YEARS + 1):
            fcf_year = fcf_year * (1 + growth_rate)
            pv_explicit += fcf_year / ((1 + self.DCF_DISCOUNT_RATE) ** year)

        terminal_value = (fcf_year * (1 + self.DCF_TERMINAL_GROWTH_RATE)) / (
            self.DCF_DISCOUNT_RATE - self.DCF_TERMINAL_GROWTH_RATE
        )
        pv_terminal = terminal_value / ((1 + self.DCF_DISCOUNT_RATE) ** self.DCF_FORECAST_YEARS)
        intrinsic_per_share = (pv_explicit + pv_terminal) / shares_out

        if not (0 < intrinsic_per_share < self.MAX_INTRINSIC_VALUE_PER_SHARE):
            logger.debug(f"[{symbol}] DCF intrinsic value implausible ({intrinsic_per_share:.2f}), marking as NULL")
            return None, None

        margin_of_safety_pct = (intrinsic_per_share - current_price) / intrinsic_per_share * 100
        if not (-1000 <= margin_of_safety_pct <= 1000):
            logger.debug(f"[{symbol}] Margin of safety out of bounds ({margin_of_safety_pct:.0f}%), marking as NULL")
            return round(intrinsic_per_share, 2), None

        return round(intrinsic_per_share, 2), round(margin_of_safety_pct, 2)

    def _compute_valuations(  # noqa: C901
        self,
        symbol: str,
        current_price: float,
        shares_out: float,
        ttm_eps: float | None,
        ttm_revenue: float | None,
        book_value: float | None,
        ocf: float,
        capex: float,
        prior_year_eps: float | None,
        dividends_paid: float | None,
        total_debt: float | None,
        total_cash: float | None,
        ebitda: float | None,
        avg_fcf_fallback: float | None = None,
    ) -> dict[str, Any]:
        """Compute all valuation ratios from SEC data."""
        result: dict[str, Any] = {
            "symbol": symbol,
            "computed_at": date.today().isoformat(),
            "data_unavailable": False,
            "reason": None,
            "data_source": "sec_audited",
            # Price-based metrics
            "current_price": current_price,
            "shares_outstanding": shares_out,
            "market_cap": None,
            # Balance sheet metrics
            "total_debt": total_debt
            if total_debt is not None and abs(total_debt) < MAX_ABSOLUTE_DOLLAR_VALUE
            else None,
            "total_cash": total_cash
            if total_cash is not None and abs(total_cash) < MAX_ABSOLUTE_DOLLAR_VALUE
            else None,
            "enterprise_value": None,
            "ebitda": ebitda if ebitda is not None and abs(ebitda) < MAX_ABSOLUTE_DOLLAR_VALUE else None,
            # Valuation ratios
            "pe_ratio": None,
            "pb_ratio": None,
            "ps_ratio": None,
            "peg_ratio": None,
            "fcf_yield": None,
            "dividend_yield": None,
            "ev_ebitda": None,
            "ev_revenue": None,
            "forward_pe": None,
            "intrinsic_value_per_share": None,
            "margin_of_safety_pct": None,
        }

        if current_price <= 0:
            result["data_unavailable"] = True
            result["reason"] = "invalid_price"
            return result

        # Market Cap = Price x Shares Outstanding
        if shares_out and shares_out > 0:
            result["market_cap"] = current_price * shares_out
        else:
            result["data_unavailable"] = True
            result["reason"] = "invalid_shares_outstanding"
            return result

        # PE Ratio = Price ÷ TTM EPS (bound to -10k..10k to reject data errors)
        if ttm_eps and ttm_eps > 0:
            pe = current_price / ttm_eps
            if pe <= 10000:  # Reasonable PE bounds
                result["pe_ratio"] = round(pe, 2)
            else:
                logger.warning(f"[{symbol}] PE ratio out of bounds ({pe:.0f}), marking as NULL")
        elif ttm_eps == 0:
            # Company is unprofitable this TTM
            result["pe_ratio"] = None
        else:
            logger.warning(f"[{symbol}] TTM EPS missing or invalid, PE ratio unavailable")

        # PB Ratio = Price ÷ Book Value Per Share (bound to 0..1000)
        if book_value and book_value > 0:
            bvps = book_value / shares_out
            if bvps > 0:
                pb = current_price / bvps
                if pb <= 1000:  # Reasonable PB bounds
                    result["pb_ratio"] = round(pb, 2)
                else:
                    logger.warning(f"[{symbol}] PB ratio out of bounds ({pb:.0f}), marking as NULL")
        else:
            logger.warning(f"[{symbol}] Book value missing, PB ratio unavailable")

        # PS Ratio = Price ÷ Revenue Per Share (bound to 0..10000)
        if ttm_revenue and ttm_revenue > 0:
            rps = ttm_revenue / shares_out
            if rps > 0:
                ps = current_price / rps
                if ps <= 10000:  # Reasonable PS bounds
                    result["ps_ratio"] = round(ps, 2)
                else:
                    logger.warning(f"[{symbol}] PS ratio out of bounds ({ps:.0f}), marking as NULL")
        else:
            logger.warning(f"[{symbol}] TTM revenue missing, PS ratio unavailable")

        # PEG Ratio = PE ÷ Earnings Growth Rate % (bound to 0..10000)
        # Growth rate: (TTM EPS - EPS from prior fiscal year) / EPS from prior fiscal year
        # NOTE: Annual (fiscal-year over fiscal-year), not quarterly - full quarterly
        # lookback would require quarterly history this loader doesn't fetch.
        if (
            result["pe_ratio"]
            and prior_year_eps is not None
            and prior_year_eps > 0
            and ttm_eps is not None
            and ttm_eps > 0
        ):
            growth_rate = ((ttm_eps - prior_year_eps) / abs(prior_year_eps)) * 100 if prior_year_eps != 0 else None
            if growth_rate and growth_rate > 0 and result["pe_ratio"] > 0:
                peg = result["pe_ratio"] / growth_rate
                if peg <= 10000:  # Reasonable PEG bounds
                    result["peg_ratio"] = round(peg, 2)
                else:
                    logger.debug(f"[{symbol}] PEG ratio out of bounds ({peg:.0f}), marking as NULL")

        # FCF Yield = Free Cash Flow ÷ Market Cap
        # FCF = Operating Cash Flow - Capital Expenditures
        if ocf and capex is not None:
            fcf = ocf - capex
            if fcf and result["market_cap"] and result["market_cap"] > 0:
                fcf_yield_pct = (fcf / result["market_cap"]) * 100
                # Only store if within reasonable bounds (-1000% to +1000%)
                # Extreme values indicate data errors or tiny market caps
                if -1000 <= fcf_yield_pct <= 1000:
                    result["fcf_yield"] = round(fcf_yield_pct, 2)
                else:
                    logger.debug(f"[{symbol}] FCF yield out of bounds ({fcf_yield_pct:.1f}%), marking as NULL")

        # Dividend Yield = Dividends Paid ÷ Market Cap (stored as a decimal fraction, e.g.
        # 0.03 = 3% - matches load_stock_scores.py._score_value's existing "decimal ->
        # percent" conversion for this field; NOT the same convention as fcf_yield above,
        # which is stored as a percentage already).
        if dividends_paid and dividends_paid > 0 and result["market_cap"] and result["market_cap"] > 0:
            div_yield = dividends_paid / result["market_cap"]
            if 0 < div_yield <= 1.0:  # >100% yield indicates a data error
                result["dividend_yield"] = round(div_yield, 4)
            else:
                logger.debug(f"[{symbol}] Dividend yield out of bounds ({div_yield:.2%}), marking as NULL")

        # Enterprise Value = Market Cap + Total Debt - Cash & Equivalents
        if result["market_cap"] is not None:
            debt_val = total_debt if total_debt else 0
            cash_val = total_cash if total_cash else 0
            ev = result["market_cap"] + debt_val - cash_val
            if ev > 0 and abs(ev) < MAX_ABSOLUTE_DOLLAR_VALUE:
                result["enterprise_value"] = round(ev, 2)
            else:
                logger.debug(f"[{symbol}] Enterprise value non-positive or implausible ({ev:.0f}), marking as NULL")

        # EV / EBITDA Ratio
        if result["enterprise_value"] and ebitda and ebitda > 0:
            ev_ebitda = result["enterprise_value"] / ebitda
            if 0 < ev_ebitda <= 10000:  # Reasonable bounds
                result["ev_ebitda"] = round(ev_ebitda, 2)
            else:
                logger.debug(f"[{symbol}] EV/EBITDA out of bounds ({ev_ebitda:.0f}), marking as NULL")

        # EV / Revenue Ratio
        if result["enterprise_value"] and ttm_revenue and ttm_revenue > 0:
            ev_revenue = result["enterprise_value"] / ttm_revenue
            if 0 < ev_revenue <= 10000:  # Reasonable bounds
                result["ev_revenue"] = round(ev_revenue, 2)
            else:
                logger.debug(f"[{symbol}] EV/Revenue out of bounds ({ev_revenue:.0f}), marking as NULL")

        # Intrinsic Value / Margin of Safety: 2-stage FCFE DCF (migration 1208, Value factor
        # goal 2026-08-17). Reuses the same FCF base (OCF - CapEx) as FCF yield above so this
        # stays consistent with the other value metrics instead of introducing a second FCF
        # definition, and the same YoY EPS growth basis peg_ratio uses (see
        # _compute_dcf_intrinsic_value for why a missing/unusable growth rate defaults to flat
        # 0%/yr here instead of blocking the DCF the way peg_ratio is blocked).
        # FIXED 2026-08-18 (coverage): a single negative-FCF year (capex-heavy or cash-flow-
        # lumpy, common for real capital-intensive/cyclical businesses) used to zero out the
        # DCF outright even when the company is normally FCF-positive. Standard DCF practice
        # normalizes FCF over multiple years for exactly this reason - fall back to the
        # 3-year average FCF (fetch_incremental's avg_fcf_fallback) only when the latest
        # year alone is unusable and the multi-year average is positive; fcf_yield above is
        # deliberately left on the latest year only (it's meant to reflect current cash
        # generation, not a smoothed figure).
        fcf_base = ocf - capex if ocf and capex is not None else None
        if (fcf_base is None or fcf_base <= 0) and avg_fcf_fallback is not None and avg_fcf_fallback > 0:
            fcf_base = avg_fcf_fallback
        eps_growth_pct = None
        if prior_year_eps is not None and prior_year_eps != 0 and ttm_eps is not None:
            eps_growth_pct = ((ttm_eps - prior_year_eps) / abs(prior_year_eps)) * 100
        result["intrinsic_value_per_share"], result["margin_of_safety_pct"] = self._compute_dcf_intrinsic_value(
            symbol, fcf_base, eps_growth_pct, shares_out, current_price
        )

        # Forward PE Ratio removed: Requires external analyst data.
        # Removed per GOVERNANCE.md: no external fallbacks for financial metrics.
        # All metrics computed from SEC audited data only.

        # CRITICAL FIX: Validate that at least ONE key valuation metric was computed
        # Prevent marking data as "available" when all key metrics are NULL
        # This was causing value_metrics to have 50%+ NULL pe_ratio even with data_unavailable=FALSE
        key_metrics = [result.get("pe_ratio"), result.get("pb_ratio"), result.get("ps_ratio"), result.get("fcf_yield")]
        if all(m is None for m in key_metrics):
            logger.warning(
                f"[{symbol}] All key valuation metrics (PE, PB, PS, FCF yield) are NULL. "
                f"Mark data as unavailable instead of incomplete."
            )
            result["data_unavailable"] = True
            result["reason"] = "all_valuation_metrics_null"

        return result

    def _unavailable_marker(self, symbol: str, reason: str) -> dict[str, Any]:
        """Return data_unavailable marker for symbol."""
        return {
            "symbol": symbol,
            "computed_at": date.today().isoformat(),
            "data_unavailable": True,
            "reason": reason,
            "data_source": "none",
            # All metrics NULL
            "current_price": None,
            "shares_outstanding": None,
            "market_cap": None,
            "total_debt": None,
            "total_cash": None,
            "enterprise_value": None,
            "ebitda": None,
            "pe_ratio": None,
            "pb_ratio": None,
            "ps_ratio": None,
            "peg_ratio": None,
            "fcf_yield": None,
            "dividend_yield": None,
            "ev_ebitda": None,
            "ev_revenue": None,
            "intrinsic_value_per_share": None,
            "margin_of_safety_pct": None,
        }


if __name__ == "__main__":
    sys.exit(run_loader(SecValuationsLoader, description="Compute valuations from SEC audited data"))
