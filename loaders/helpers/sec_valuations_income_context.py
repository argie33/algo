"""Income-statement fetch/derivation context for SecValuationsLoader.fetch_incremental,
extracted from load_sec_valuations.py (2026-09-05, file-size ratchet: that file is one of the
Tier-1 bloaters flagged for decomposition, see MEMORY.md's bloater_decomposition_strategy_20260905).
Method is verbatim, no logic changed - mixed into SecValuationsLoader, which still defines every
class constant/other-mixin method (_get_total_cash_and_debt, _compute_multi_year_eps_cagr,
_unavailable_marker) this method reads/calls via `self`, so behavior is unchanged - only the
method body moved file.
"""

import logging
from typing import TYPE_CHECKING, Any

from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)


class IncomeStatementContextMixin:
    """Income-statement fetch/derivation (revenue/EPS anchor-row fallbacks, EBITDA,
    total_cash/total_debt, PEG's prior_year_eps) for SecValuationsLoader.fetch_incremental.
    Not usable standalone - relies on methods defined on SecValuationsLoader itself (via other
    mixins) and on `_split_adjusted_eps`/`_fpi_ads_adjusted_eps`/`MAX_ABSOLUTE_DOLLAR_VALUE` in
    load_sec_valuations.py (imported locally inside the method, not at module level, to avoid a
    circular import - same pattern as ValuationSanityCheckMixin._sanity_check_market_cap's
    `_lsv` import).
    """

    # Type-only declarations, TYPE_CHECKING-only so they exist for mypy but never shadow the
    # real methods at runtime (MRO would find these before the real ones if they were real
    # methods here, since SecValuationsLoader lists this mixin after ValuationSanityCheckMixin/
    # DcfValuationMixin - TYPE_CHECKING keeps that a non-issue either way) - the real
    # implementations live on ValuationSanityCheckMixin/DcfValuationMixin, which
    # SecValuationsLoader also mixes in.
    if TYPE_CHECKING:

        def _get_total_cash_and_debt(self, cur: Any, symbol: str) -> tuple[float | None, float | None]: ...

        def _unavailable_marker(
            self,
            symbol: str,
            reason: str,
            total_debt: float | None = None,
            total_cash: float | None = None,
            ebitda: float | None = None,
        ) -> dict[str, Any]: ...

        @staticmethod
        def _compute_multi_year_eps_cagr(income_rows: list[tuple[Any, ...]]) -> float | None: ...

    @staticmethod
    def _reclassify_fpi_zero_row_currency_gap(cur: Any, symbol: str, reason: str) -> str:
        """ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, sibling to
        9e26b3d02/6111c0b4f's has_unsupported_currency_only_fact fix): annual_income_statement
        having ZERO rows for a foreign private issuer (as opposed to a row existing but all-NULL,
        the case those two commits cover) means every fact _aggregate_concepts found for
        revenue/net_income was in a rejected currency, so no row was ever created at all (see
        _aggregate_concepts: a currency-skipped unit never touches `rows.setdefault`).
        Live-confirmed GGAL/BSAC/TKC/EDN/SUPV/TGS/TEO hitting this exact shape (ifrs-full
        Revenue/ProfitLoss only under unit="ARS"). This mixin has no SecEdgarClient instance to
        reuse a cache from (unlike load_financial_statements.py, mid-extraction) and there's no
        DB row to cross-reference either (that's the whole gap - zero rows exist), so this is the
        one call site that genuinely needs a fresh live check - scoped to the rare "FPI with
        literally zero income-statement rows" path only (caller only invokes this when
        reason == "no_income_statement").
        """
        cur.execute(
            "SELECT is_foreign_private_issuer FROM company_info_sec WHERE symbol = %s",
            (symbol,),
        )
        fpi_row = cur.fetchone()
        if not (fpi_row and fpi_row[0]):
            return reason

        from utils.external.sec_edgar_client import SecEdgarClient
        from utils.external.sec_statements_shared import has_unsupported_currency_only_fact

        if has_unsupported_currency_only_fact(
            SecEdgarClient(), symbol, ["Revenues", "NetIncomeLoss"], ["Revenue", "ProfitLoss"]
        ):
            return "unsupported_currency_no_fx_rate"
        return reason

    def _fetch_income_statement_context(self, cur: Any, symbol: str) -> Any:
        """Fetch the latest annual_income_statement row(s) for `symbol` and derive every
        income-statement-sourced value fetch_incremental needs before it can resolve
        shares_out: ttm_revenue/ttm_eps_basic (with same-anchor-row-timing-gap fallbacks),
        prior_year_eps (for PEG, guarded against the ttm-substitution double-counting bug),
        dcf_eps_cagr_pct, total_cash/total_debt/ebitda (with the MAX_ABSOLUTE_DOLLAR_VALUE
        overflow guard), is_foreign_private_issuer, sic_code, and reported_shares_outstanding.
        Moved verbatim out of fetch_incremental - same `cur` (still inside that method's `with
        DatabaseContext("read") as cur:` block), same queries, same order.

        Returns EITHER a single-element list containing a data_unavailable marker dict (the two
        early-return cases fetch_incremental itself used to hit directly: "no_income_statement"
        and "income_statement_revenue_and_eps_null") - the caller must `return` this immediately,
        exactly as fetch_incremental did inline before this extraction - OR, on success, the
        tuple (income_rows, is_foreign_private_issuer, sic_code, ttm_fiscal_year, ttm_revenue,
        ttm_net_income, ttm_eps_basic, prior_year_eps, eps_substituted_from_row1,
        dcf_eps_cagr_pct, total_cash, total_debt, ebitda, reported_shares_outstanding).
        """
        # Local import (not module-level): load_sec_valuations.py imports this mixin before
        # _split_adjusted_eps/_fpi_ads_adjusted_eps/MAX_ABSOLUTE_DOLLAR_VALUE are defined
        # further down in its own source, and this module is imported BY load_sec_valuations.py,
        # so a module-level import here would be a true circular import - same fix already
        # applied in SharesOutstandingResolutionMixin._resolve_shares_outstanding and
        # ValuationSanityCheckMixin._sanity_check_market_cap for the same reason.
        from loaders.load_sec_valuations import (
            MAX_ABSOLUTE_DOLLAR_VALUE,
            _fpi_ads_adjusted_eps,
            _split_adjusted_eps,
        )

        # Get income statement data from most recent annual filing
        # CRITICAL: Use NULL checks instead of COALESCE(col, 0) to detect missing financial data
        # Defaulting to 0 for revenue/EPS would cause wrong valuations (zero division, phantom metrics)
        # FIXED 2026-08-20 (goal: finance-accuracy audit): the `data_unavailable = FALSE`
        # filter removed below (see old NOTE) was dropped to stop excluding legitimate rows
        # where the flag is simply unset - but data_unavailable=TRUE with
        # reason='incomplete_sec_filing_income' means the filer's income-statement section
        # is itself incomplete/inconsistent, not merely unset, and its non-NULL
        # revenue/net_income/EPS values are known-unreliable, not just missing. Live-
        # confirmed 113 universe symbols with a valid current_price currently computing
        # pe_ratio/ps_ratio in the hundreds (e.g. ASBP pe_ratio=1649.85, AVLN=1535.70,
        # BOBS=922.50, ALMR=808.37) purely from this. `data_unavailable IS NOT TRUE` (not
        # `= FALSE`) keeps admitting NULL-flag rows exactly as before while excluding only
        # the confirmed-bad ones, falling back to the next real fiscal year within the
        # LIMIT 2 window (or the existing no_income_statement/*_null unavailable paths)
        # instead of a fabricated ratio.
        # FIXED: plain `ORDER BY fiscal_year DESC` picked the latest fiscal year even when
        # it's a partial/estimate-stage filing with NULL revenue AND NULL EPS, while an
        # older year has real data - same "latest year is empty" bug class as the FCF fix
        # in load_value_quality_growth_metrics.py. Live-confirmed: MC (Moelis), CLSK
        # (CleanSpark), FRD (Friedman Industries) all have real revenue/net_income one
        # fiscal year back but were failing "income_statement_revenue_and_eps_null" on the
        # latest year alone. Prioritizing rows with revenue or EPS present, then by
        # fiscal_year DESC, still returns two genuinely consecutive fiscal years for the
        # prior_year_eps growth-rate calc below (whichever two are most recent AND usable).
        # ADDED 2026-08-19 (migration 1211, goal: "no SEC data"/missing factor inputs
        # audit): is_foreign_private_issuer folded in via LEFT JOIN (not a separate
        # round-trip) so it's available on income_rows[0] without disturbing the call
        # sequence every other query in this method relies on. See the shares_out tier
        # gating below for the full story - foreign private issuers (20-F/40-F/6-K)
        # report revenue/net_income/EPS/share-count figures in their home-market
        # security's units, which for ADR-structured filers (e.g. TSM, 1 ADS = 5
        # ordinary shares) differ from the US-registered security current_price is
        # quoted in.
        cur.execute(
            """
            SELECT
                ais.fiscal_year,
                ais.revenue,
                ais.net_income,
                ais.earnings_per_share,
                ais.operating_income,
                ais.pretax_income,
                ais.depreciation_expense,
                ais.amortization_expense,
                ais.shares_outstanding_basic,
                ais.income_tax_expense,
                cis.is_foreign_private_issuer,
                cis.sic_code,
                ais.interest_expense
            FROM annual_income_statement ais
            LEFT JOIN company_info_sec cis ON cis.symbol = ais.symbol
            WHERE ais.symbol = %s AND ais.data_unavailable IS NOT TRUE
            ORDER BY (CASE WHEN ais.revenue IS NOT NULL OR ais.earnings_per_share IS NOT NULL OR ais.net_income IS NOT NULL THEN 0 ELSE 1 END), ais.fiscal_year DESC
            LIMIT 6
            """,
            (symbol,),
        )
        # LIMIT raised from 2 to 6 on 2026-08-25 (goal: "finance best practices"
        # methodology audit, deferred item - multi-year EPS CAGR for the DCF): purely
        # additive - every fallback below still only ever reads income_rows[0]/[1],
        # exactly as before. Rows 2-5 exist solely to give
        # _compute_multi_year_eps_cagr below a few more fiscal years of EPS history
        # without a second query - same tier/fiscal_year-DESC ordering as before, so
        # income_rows[0]/[1]'s selection is unchanged.
        income_rows = cur.fetchall()
        if not income_rows:
            # FIXED 2026-09-02 (goal: "get all the data we need" full-coverage audit):
            # total_cash/total_debt are pure balance-sheet facts with no income-
            # statement dependency - see _get_total_cash_and_debt's own docstring for
            # the live-confirmed AADX evidence this was silently losing both to this
            # exact early return.
            total_cash, total_debt = self._get_total_cash_and_debt(cur, symbol)
            # FIXED 2026-09-05 (goal session: "implausible values" sweep follow-up): an ETF
            # (stock_symbols.etf = 'true') genuinely has zero annual_income_statement rows -
            # it files N-1A/N-CSR under the Investment Company Act, not a 10-K, so there is no
            # SEC "income statement" concept to extract at all. Same "Legitimate / not
            # applicable" business-model fact as reit_special_entity/etf_trust_no_gaap_
            # financials elsewhere in this codebase, not a missing-SEC-data gap. Live-confirmed
            # SPY (SPDR S&P 500 ETF Trust): zero rows in both annual_income_statement and
            # sec_valuations itself.
            cur.execute("SELECT etf FROM stock_symbols WHERE symbol = %s", (symbol,))
            etf_row = cur.fetchone()
            reason = "etf_no_sec_filings" if etf_row and etf_row[0] == "true" else "no_income_statement"
            if reason == "no_income_statement":
                reason = self._reclassify_fpi_zero_row_currency_gap(cur, symbol, reason)
            return [self._unavailable_marker(symbol, reason, total_cash=total_cash, total_debt=total_debt)]

        # len() guard: pre-existing tests mock income_rows as plain 10-element
        # tuples (this method's own pre-2026-08-19 shape) - default to False
        # (unchanged prior behavior) rather than requiring every one of those
        # fixtures to be updated for a column real production queries always return.
        is_foreign_private_issuer = bool(income_rows[0][10]) if len(income_rows[0]) > 10 else False
        # FIXED 2026-08-22 (goal session: "Missing SEC/XBRL data" coverage audit):
        # depository institutions (banks) never tag a "CapitalExpenditures" XBRL
        # concept, ever, in any fiscal year - live-confirmed via JPM, BAC, MS, WFC,
        # PNC's real companyfacts JSON (capex NULL across every year 2007-2026, not
        # just the current interim year). See the capex-fallback comment below and
        # in sec_base.py's free_cash_flow computation for the full rationale.
        sic_code = income_rows[0][11] if len(income_rows[0]) > 11 else None
        # FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" follow-up, "implausible
        # values" sweep): the pretax_income-as-operating_income fallback just below was
        # applying unconditionally to ANY symbol lacking a tagged operating_income, not just
        # the financial-services companies (banks/insurers) its own comment describes -
        # pretax_income is AFTER interest expense, so using it bare as a proxy for
        # operating_income (which is BEFORE interest) silently and massively understated
        # EBITDA for any real industrial/leveraged filer with material interest_expense.
        # Live-confirmed HRI (Herc Holdings, equipment rental, NOT a financial company):
        # FY2025 pretax_income=$1M, interest_expense=$416M - the bare fallback produced
        # ebitda=$1M (matching sec_valuations' stored value exactly) for a company with
        # $4.4B market cap, a wrong-by-2-orders-of-magnitude EV/EBITDA input. Adding back
        # interest_expense when available is the mathematically correct general fix (works
        # for any company type) and is a no-op for genuine financial companies, which
        # typically don't tag a separate interest_expense concept at all (interest is netted
        # into revenue, not reported as a standalone expense line) - so this fix doesn't
        # change the JPM/BAC/PNC-class behavior the fallback was originally built for.
        interest_expense_val = income_rows[0][12] if len(income_rows[0]) > 12 else None

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
        ) = income_rows[0][:10]

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
        # FIXED 2026-09-05 (goal session: "implausible values" sweep): the check above
        # only handled ttm_revenue being NULL, not a real but NEGATIVE anchor-year value
        # - live-confirmed BWMX (Betterware de Mexico, IFRS filer): FY2022 anchor row has
        # revenue=-$543.3M (likely a restatement/writeback artifact), while FY2025/FY2024
        # both have real positive revenue ($7.2B/$10.1B) one-two rows back. A negative
        # revenue is exactly as unusable for ps_ratio/ev_revenue as a NULL one (the
        # downstream `if ttm_revenue and ttm_revenue > 0` gates already refuse to compute
        # from it either way) but, unlike NULL, never triggered this same-window fallback
        # - silently leaving ps_ratio/ev_revenue None with no reason recorded instead of
        # recovering the real, usable figure one row back. Same small-window fallback,
        # just widened to treat "real but non-positive" the same as "missing", consistent
        # with every other revenue-anchor gate in this codebase treating a non-positive
        # value as equivalent to absent for ratio-denominator purposes.
        if (
            (ttm_revenue is None or ttm_revenue <= 0)
            and len(income_rows) > 1
            and income_rows[1][1] is not None
            and income_rows[1][1] > 0
        ):
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

        # See RECENT_STOCK_SPLITS' own module-level comment (BKNG 25-for-1, 2026-04-02).
        ttm_eps_basic = _split_adjusted_eps(symbol, ttm_eps_basic, ttm_eps_fiscal_year)
        # See FPI_EPS_ADS_RATIO_OVERRIDES' own module-level comment (DDI, 20 ADS = 1 share).
        ttm_eps_basic = _fpi_ads_adjusted_eps(symbol, ttm_eps_basic, ttm_eps_fiscal_year)

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
            operating_income = pretax_income + (interest_expense_val or 0)
            logger.debug(
                f"[{symbol}] Using pretax_income + interest_expense as operating_income fallback"
                " (financial services company, or a leveraged filer needing the interest addback)"
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
            prior_year_eps = _split_adjusted_eps(symbol, prior_year_eps, income_rows[1][0])
            prior_year_eps = _fpi_ads_adjusted_eps(symbol, prior_year_eps, income_rows[1][0])
        elif eps_substituted_from_row1:
            # income_rows[1] was itself consumed above as the ttm_eps substitute (the
            # premature-stub case) - re-fetch a genuinely older year rather than reuse it.
            cur.execute(
                """
                SELECT fiscal_year, earnings_per_share FROM annual_income_statement
                WHERE symbol = %s AND fiscal_year < %s AND earnings_per_share IS NOT NULL
                AND data_unavailable IS NOT TRUE
                ORDER BY fiscal_year DESC LIMIT 1
                """,
                (symbol, ttm_eps_fiscal_year),
            )
            older_eps_row = cur.fetchone()
            prior_year_eps = _split_adjusted_eps(symbol, older_eps_row[1], older_eps_row[0]) if older_eps_row else None
            prior_year_eps = _fpi_ads_adjusted_eps(symbol, prior_year_eps, older_eps_row[0] if older_eps_row else None)
        else:
            prior_year_eps = None

        # ADDED 2026-08-25 (goal: "finance best practices" methodology audit,
        # deferred item - "multi-year EPS CAGR instead of single-year growth"): the
        # DCF's growth driver (eps_growth_pct in _compute_valuations below) was a bare
        # TTM-vs-prior-year EPS delta - noisy for any symbol whose single prior year had
        # a one-off blip (impairment, tax item, etc), the same "one bad year distorts
        # the whole figure" problem already solved for FCF via the 3-year
        # avg_fcf_fallback. Uses the same income_rows list (now fetched with LIMIT 6, see
        # above) rather than PEG's prior_year_eps/ttm_eps - PEG deliberately stays
        # single-year (see peg_ratio's own comment; it's a conventionally
        # single-year-forward metric, changing it would be a different, unrequested
        # methodology change).
        dcf_eps_cagr_pct = self._compute_multi_year_eps_cagr(income_rows)

        # MOVED 2026-08-19 (goal session continuation - "which factor inputs are
        # missing the most" audit): total_debt/total_cash/ebitda used to live after the
        # shares_outstanding and current_price gates below, even though none of the
        # three actually depend on shares outstanding or price - they're pure balance-
        # sheet/income-statement dollar figures. That put them behind an early `return`
        # they had no real dependency on: any symbol failing the shares_outstanding gate
        # (771 active symbols, overwhelmingly foreign private issuers - see
        # load_company_info_sec.py's domestic-forms-only guard) or the price gate lost
        # total_debt/total_cash/ebitda too, purely as a control-flow accident, not a real
        # data gap. Computed here, before every gate below, so
        # load_value_quality_growth_metrics.py's `SELECT total_debt, total_cash, ebitda
        # FROM sec_valuations` (which reads these three columns directly, with no
        # data_unavailable=FALSE filter) gets real values via the unavailable-marker path
        # too, not just the full-success path. cash_per_share is unaffected - it still
        # needs shares_outstanding and correctly stays gated.
        # FIXED 2026-08-20 (goal: finance-accuracy audit): added data_unavailable IS NOT
        # TRUE - same bug class as the income-statement query above. reason=
        # 'incomplete_sec_filing_balance' rows can carry a non-NULL but unreliable
        # cash_and_equivalents; live-confirmed 253 universe symbols with a valid
        # current_price were picking one up as "the" cash figure.
        # Debt = long_term_debt + short_term_debt + operating/finance lease liabilities
        # (S&P/Moody's "adjusted debt" convention; NOT total_liabilities, which
        # overstates debt ~3x by including accounts payable/deferred revenue/pensions -
        # see git history for the AAPL/MSFT/GOOGL/F live-confirmed fix). NULL only when
        # ALL FOUR components are absent across every fiscal year on file; a fiscal year
        # whose components sum to a real nonzero value is preferred over one that's
        # merely non-NULL (a lone real `short_term_debt=0` on an in-progress year must
        # not outrank a fuller prior year), which in turn is preferred over a bare
        # `ORDER BY fiscal_year DESC` for genuinely zero-debt companies.
        #
        # TIER 0 ADDED 2026-09-01 (goal-mode factor-usage review, category-leaders spot
        # check): the "any nonzero sum" tier above couldn't distinguish a COMPLETE year
        # from a PARTIAL one - a stray small short_term_debt/lease-liability figure on an
        # in-progress fiscal year (real, but missing the dominant long_term_debt line
        # because a mid-year 10-Q simply doesn't re-disclose the full debt schedule the
        # way an annual 10-K's footnotes do) counted as "nonzero" exactly like a genuinely
        # complete prior year - and being MORE RECENT, won the tiebreak outright. Live-
        # confirmed via COF (Capital One): FY2026 has short_term_debt=$1.626B alone
        # (long_term_debt NULL) while FY2025 has the real, complete long_term_debt=
        # $49.913B - old logic picked FY2026's $1.626B "total debt" for one of the
        # largest, most leveraged banks in the market. Same root cause as JCAP's
        # near-zero debt_to_equity found the same session (a $3.891M operating-lease-only
        # FY2026 figure beating FY2025's real $1.754B long_term_debt). Universe-wide sweep:
        # 477 symbols (incl. GE, GS, TD, COF, TMUS, DUK, SO, PCG) had their most recent
        # nonzero year measure under 5% of their own historical max debt-sum - not a
        # financials-only issue, a general "incomplete current year" issue. Fix: a year
        # where long_term_debt ITSELF is present (the single most information-dense,
        # hardest-to-accidentally-populate component - no filing accidentally reports a
        # multi-billion-dollar long-term debt figure) now wins over any year that only has
        # the smaller components, tiebroken by fiscal_year DESC among long_term_debt-real
        # years so the freshest COMPLETE year still wins. Falls through unchanged to the
        # existing tiers for companies that never report long_term_debt at all (genuinely
        # short-term-debt-only or lease-only capital structures aren't penalized - they
        # simply never populate tier 0, same as before this fix).
        total_cash, total_debt = self._get_total_cash_and_debt(cur, symbol)

        # EBITDA = Operating Income + Depreciation + Amortization (Session 398)
        ebitda = None
        oi = safe_float(operating_income, f"{symbol}.operating_income", allow_none=True)
        if oi is not None:
            dep_exp = safe_float(depreciation_expense, f"{symbol}.depreciation_expense", allow_none=True)
            amort_exp = safe_float(amortization_expense, f"{symbol}.amortization_expense", allow_none=True)
            ebitda_val = oi
            if dep_exp:
                ebitda_val += dep_exp
            if amort_exp:
                ebitda_val += amort_exp
            ebitda = ebitda_val

        # Same overflow guard _compute_valuations applies to these three below (see
        # MAX_ABSOLUTE_DOLLAR_VALUE's module docstring - foreign ADR filers reporting
        # balance-sheet figures in local currency without USD conversion, live-crashed
        # NumericValueOutOfRange on BBAR/BCH/BMA/BSAC/HDB/HMC) - applied here too since
        # the unavailable-marker return paths below use these values directly, bypassing
        # _compute_valuations' own guard entirely.
        if total_debt is not None and abs(total_debt) >= MAX_ABSOLUTE_DOLLAR_VALUE:
            total_debt = None
        if total_cash is not None and abs(total_cash) >= MAX_ABSOLUTE_DOLLAR_VALUE:
            total_cash = None
        if ebitda is not None and abs(ebitda) >= MAX_ABSOLUTE_DOLLAR_VALUE:
            ebitda = None

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
            # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, sibling of the
            # `not income_rows` branch's own 2026-09-05 ETF fix above): live-confirmed IWM
            # (iShares Russell 2000 ETF, stock_symbols.etf='true') has a stray
            # annual_income_statement row that survives the `data_unavailable IS NOT TRUE`
            # filter above but carries no real revenue/EPS/net_income - same underlying "this
            # is a fund, not an operating company with a 10-K income statement" fact as the
            # zero-rows case, just reached via a row that technically exists but is empty
            # rather than truly absent. Same reason label, same category
            # ("Legitimate / not applicable").
            cur.execute("SELECT etf FROM stock_symbols WHERE symbol = %s", (symbol,))
            etf_row = cur.fetchone()
            reason = (
                "etf_no_sec_filings" if etf_row and etf_row[0] == "true" else "income_statement_revenue_and_eps_null"
            )
            return [
                self._unavailable_marker(
                    symbol,
                    reason,
                    total_debt=total_debt,
                    total_cash=total_cash,
                    ebitda=ebitda,
                )
            ]

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
        # FIXED 2026-08-19 (migration 1211, goal: "no SEC data"/missing factor inputs
        # audit): live-confirmed TSM (Taiwan Semiconductor, 1 ADS = 5 ordinary
        # shares) showed market_cap=$10.7 TRILLION and pe_ratio=304 (both ~5x too
        # high, independently cross-checked against yfinance's live sharesOutstanding/
        # marketCap/trailingPE) because tiers 1-3/5 below all read
        # shares_outstanding_basic/diluted or derive a share count from net_income/EPS
        # - for a foreign private issuer these are real, correctly-filed figures, just
        # on the filer's home-market ordinary-share basis, not the ADS-equivalent basis
        # current_price is quoted in. Only tiers 4 (company_info_sec) and 6
        # (shares_outstanding_dei) are independently guarded to domestic forms only
        # (see load_company_info_sec.py and utils/external/sec_statements.py
        # respectively) - skip straight to those for a foreign private issuer rather
        # than risk the same unit mismatch in a tier nobody had separately audited.

        return (
            income_rows,
            is_foreign_private_issuer,
            sic_code,
            ttm_fiscal_year,
            ttm_revenue,
            _ttm_net_income,
            ttm_eps_basic,
            prior_year_eps,
            eps_substituted_from_row1,
            dcf_eps_cagr_pct,
            total_cash,
            total_debt,
            ebitda,
            reported_shares_outstanding,
        )
