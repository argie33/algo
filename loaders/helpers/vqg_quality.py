"""QualityMetricsMixin._compute_quality_metrics, extracted from
load_value_quality_growth_metrics.py (2026-09-05, file-size-ratchet compliance split): this
single method was ~2,600 of the file's ~6,070 lines - by far the largest single
concentration. Moved verbatim - no behavior change - except `DatabaseContext(...)` call
sites now go through `_owner()` (see that helper's own docstring for why).

Mixed into ValueQualityGrowthMetricsLoader via multiple inheritance alongside
ValueMetricsMixin/GrowthMetricsMixin - every `self.` call here (the 39 SymbolGateMixin
gates, _fetch_annual_fallback_row, _fetch_balance_sheet_anchor_fallback,
_ratio_with_implausible_fallback, _find_plausible_cross_year_ratio, etc.) resolves normally
through the instance regardless of which mixin file defines it.
"""

import logging
from typing import TYPE_CHECKING, Any

from loaders.helpers.vqg_quality_inputs import QualityInputsMixin
from loaders.helpers.vqg_quality_reasons_profitability import QualityReasonsProfitabilityMixin
from loaders.helpers.vqg_quality_reasons_valuation import QualityReasonsValuationMixin
from loaders.helpers.vqg_quality_recategorize import QualityRecategorizeMixin
from loaders.helpers.vqg_quality_score import QualityScoreMixin
from loaders.helpers.vqg_shared import (
    _QUARTERLY_DERIVED_TREND_FIELDS,
    MAX_ABSOLUTE_DOLLAR_VALUE,
    MAX_PLAUSIBLE_GROWTH_PCT,
    MAX_TREND_PERCENTAGE_POINTS,
    compute_quality_row_level_reason,
    get_loader_timestamp,
)
from loaders.helpers.vqg_symbol_gates import SymbolGateMixin
from utils.external.sec_ticker_cache import is_known_non_sec_filer_bank
from utils.type_conversion import safe_float


def _owner() -> Any:
    """Lazy reference to the owner module, resolved at call time (not import time).

    Two reasons this indirection exists, both load-bearing:
    (1) DatabaseContext: dozens of existing unit tests monkeypatch
    ``loaders.load_value_quality_growth_metrics.DatabaseContext`` directly. A module-level
    ``from utils.db.context import DatabaseContext`` here would bind this module's own
    separate copy of the name, which those patches can never reach - going through
    ``_owner().DatabaseContext`` always reads whatever the owner module's current attribute
    is, mocked or real.
    (2) Avoids importing anything from the owner module at THIS module's top level, which
    is what caused a real circular-import crash on 2026-09-05 (see
    vqg_and_stock_scores_dead_split_files_deleted_20260905 in memory): when the owner is run
    as a script (``python loaders/load_value_quality_growth_metrics.py``) rather than
    imported as a package, it registers under ``sys.modules["__main__"]``, not its dotted
    path - a top-level `from loaders.load_value_quality_growth_metrics import X` here then
    re-imports the owner from scratch while it's still mid-import, before this class exists
    yet, raising ImportError. Importing lazily inside a function body sidesteps this
    entirely since it only runs after both modules have finished importing.
    """
    from loaders import load_value_quality_growth_metrics as _owner_mod

    return _owner_mod


logger = logging.getLogger("loaders.load_value_quality_growth_metrics")


class QualityMetricsMixin(
    SymbolGateMixin,
    QualityInputsMixin,
    QualityRecategorizeMixin,
    QualityScoreMixin,
    QualityReasonsProfitabilityMixin,
    QualityReasonsValuationMixin,
):
    """See module docstring.

    Inherits SymbolGateMixin (also a base of ValueQualityGrowthMetricsLoader itself - a
    diamond, harmless since it's the same class both times) purely so mypy can see the 39
    `_get_*_symbols` gate methods called via `self.` below, and QualityInputsMixin/
    QualityRecategorizeMixin (2026-09-09 file-size-ratchet split of this file's own former
    body - see those modules' docstrings) for real so `_derive_quality_row_inputs`/
    `_apply_quality_recategorize_reasons_pre`/`_apply_quality_recategorize_reasons_post`
    resolve without a TYPE_CHECKING-only stub. The handful of other cross-mixin members
    (defined on ValueQualityGrowthMetricsLoader or a sibling mixin, which don't exist as
    types this file can import without a real circular import) are declared type-checking-
    only below.
    """

    if TYPE_CHECKING:
        _ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS: frozenset[str]

        def _nan_to_none(self, value: float | None) -> float | None: ...

        def _unavailable_marker(self, table: str, symbol: str, reason: str | None = None) -> dict[str, Any]: ...

        def _fetch_annual_fallback_row(
            self, table: str, columns: str, extra_where: str, symbol: str
        ) -> tuple[Any, ...] | None: ...

        def _fetch_balance_sheet_anchor_fallback(self, symbol: str, column: str) -> float | None: ...

        def _fetch_total_debt_components_fallback(self, symbol: str) -> float | None: ...

        def _fetch_ttm_net_income_from_quarterly(self, symbol: str) -> float | None: ...

        def _ratio_with_implausible_fallback(
            self,
            symbol: str,
            numerator: float | None,
            denominator: float | None,
            numerator_field: str,
            denominator_field: str,
            *,
            denominator_must_be_positive: bool = False,
        ) -> tuple[float | None, bool]: ...

        def _get_symbol_sector(self, symbol: str) -> str | None: ...

        def _get_symbol_industry(self, symbol: str) -> str | None: ...

        def _compute_quarterly_metrics(self, symbol: str) -> dict[str, Any]: ...

        def _margin_curve(self, value: float, breakpoints: list[tuple[float, float]]) -> float: ...

        def _weighted_avg(
            self, components: list[tuple[float | None, float]], min_weight_pct: float = 0.0
        ) -> float | None: ...

        def _find_plausible_cross_year_ratio(
            self, symbol: str, numerator_field: str, denominator_field: str, *, as_percentage: bool = True
        ) -> float | None: ...

        def _find_plausible_cross_year_roic_ratio(self, symbol: str, metric: str) -> float | None: ...

        def _find_plausible_cross_year_ebitda_margin_ratio(self, symbol: str) -> float | None: ...

    def _compute_quality_metrics(  # noqa: C901
        self,
        symbol: str,
        quality_row: Any,
        ev_metrics: Any = None,
        margin_volatility: float | None = None,
    ) -> dict[str, Any]:
        """Compute quality_metrics from SEC financials (balance sheet + income statement + cash flow + EV data).

        ev_metrics: tuple of (total_debt, total_cash, ebitda[, reason]) from sec_valuations -
        the 4th element (sec_valuations.reason) is optional for backward compatibility with
        callers/tests still passing a 3-tuple.
        margin_volatility: trailing-3yr net_margin stdev, precomputed by the caller (see
        _compute_margin_volatility) from multi-year income_rows this function doesn't have.
        """
        if not quality_row:
            # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): this early
            # return fires whenever the symbol has ZERO annual_balance_sheet rows at all
            # (the query feeding `quality_row` is a LEFT JOIN off that table) - live-
            # confirmed SPY (listed 1993, 8,458 real trading days, ZERO annual_balance_sheet
            # rows ever, since ETFs file N-1A/N-CSR under the Investment Company Act, never a
            # 10-K) was falling through to the generic "missing_sec_data" default for its
            # ENTIRE quality_metrics row (every one of its ~45 *_unavailable_reason columns),
            # mislabeling a real, permanent business-model fact as an actionable SEC/XBRL
            # data gap. `_get_etf_symbols()` was added 2026-09-05 for exactly this SPY/IGV/
            # BKDV shape, but only wired into the per-field total_debt/total_cash reason
            # chains further down this function - unreachable from this earlier return, so it
            # never actually fixed SPY. Reuses "etf_no_sec_filings" (already correctly mapped
            # to "Legitimate / not applicable") - the identical underlying fact
            # sec_valuations_income_context.py's own ETF carve-out already uses for the same
            # "no 10-K" case. FIXED 2026-09-07: also covers RIC/CEF - see _no_balance_sheet_row_reason().
            reason = self._no_balance_sheet_row_reason(symbol)
            return self._unavailable_marker("quality_metrics", symbol, reason=reason)

        if not isinstance(quality_row, (tuple, list)):
            logger.error(
                f"[VALUE_QUALITY_GROWTH] {symbol}: quality_row is {type(quality_row)}, not tuple/list. This is a CRITICAL BUG. "
                f"Upstream transformation (cur.fetchone() from annual_balance_sheet JOIN) failed to return tuple. "
                f"Data structure: {repr(quality_row)[:200]}. "
                f"Check: (1) DatabaseContext cursor type, (2) Connection pool configuration, (3) Database driver version. "
                f"Recovery: Mark symbol unavailable and skip quality metrics for this run."
            )
            return self._unavailable_marker("quality_metrics", symbol)

        if len(quality_row) < 28:
            logger.error(f"[VALUE_QUALITY_GROWTH] {symbol}: quality_row has {len(quality_row)} columns, expected 28")
            return self._unavailable_marker("quality_metrics", symbol)

        try:
            _qi = self._derive_quality_row_inputs(symbol, quality_row)
            stockholders_equity = _qi["stockholders_equity"]
            total_liabilities = _qi["total_liabilities"]
            total_assets = _qi["total_assets"]
            net_income = _qi["net_income"]
            net_income_from_ttm_quarterly = _qi["net_income_from_ttm_quarterly"]
            net_income_from_annual_fallback = _qi["net_income_from_annual_fallback"]
            revenue = _qi["revenue"]
            operating_income = _qi["operating_income"]
            current_assets = _qi["current_assets"]
            current_liabilities = _qi["current_liabilities"]
            inventory = _qi["inventory"]
            interest_expense = _qi["interest_expense"]
            pretax_income = _qi["pretax_income"]
            interest_coverage_operating_income = _qi["interest_coverage_operating_income"]
            shares_outstanding = _qi["shares_outstanding"]
            cost_of_revenue = _qi["cost_of_revenue"]
            operating_cash_flow = _qi["operating_cash_flow"]
            free_cash_flow = _qi["free_cash_flow"]
            earnings_per_share = _qi["earnings_per_share"]
            prior_year_eps = _qi["prior_year_eps"]
            prior_year_revenue = _qi["prior_year_revenue"]
            gross_profit_direct = _qi["gross_profit_direct"]
            long_term_debt_bs = _qi["long_term_debt_bs"]
            cash_and_equivalents_bs = _qi["cash_and_equivalents_bs"]
            income_tax_expense = _qi["income_tax_expense"]
            prior_year_net_income = _qi["prior_year_net_income"]
            prior_year_operating_cash_flow = _qi["prior_year_operating_cash_flow"]
            prior_year_free_cash_flow = _qi["prior_year_free_cash_flow"]
            prior_year_cost_of_revenue = _qi["prior_year_cost_of_revenue"]
            prior_year_total_assets = _qi["prior_year_total_assets"]
            prior_year_stockholders_equity = _qi["prior_year_stockholders_equity"]
            prior_year_gross_profit = _qi["prior_year_gross_profit"]
            dividends_paid_with_prior_year_fallback = _qi["dividends_paid_with_prior_year_fallback"]
            prior_year_operating_income_for_trend = _qi["prior_year_operating_income_for_trend"]

            metrics: dict[str, Any] = {
                "symbol": symbol,
                "roe": None,
                "roa": None,
                "operating_margin": None,
                "net_margin": None,
                "debt_to_equity": None,
                "debt_to_assets": None,
                "current_ratio": None,
                "quick_ratio": None,
                "interest_coverage": None,
                # New fields - Phase 3 expansion
                "gross_margin": None,
                "ebitda_margin": None,
                "roic_pct": None,
                "roce_pct": None,
                "fcf_to_net_income": None,
                "ocf_to_net_income": None,
                "payout_ratio": None,
                "free_cash_flow": None,
                "operating_cash_flow": None,
                "total_debt": None,
                "total_cash": None,
                "cash_per_share": None,
                "ebitda": None,
                "earnings_growth_yoy": None,
                "revenue_growth_yoy": None,
                "quality_score": None,
                "data_unavailable": False,
                "data_source": "sec_audited",
                "updated_at": get_loader_timestamp(),
            }

            failed_metrics: list[str] = []
            # Metrics whose value came from _find_plausible_cross_year_ratio /
            # _find_plausible_cross_year_roic_ratio (up to 6 fiscal years back, tightened
            # 2026-09-05 real-money audit from an original 30-year lookback that let this
            # rescue reach implausibly far into the past) rather than the current anchor
            # year. That value is written into the SAME row as this symbol's current-period
            # metrics with no other provenance marker, so without this tracking a multi-year-
            # old ratio is indistinguishable from fresh data to any downstream scoring/
            # backtest consumer. See data_source override near this function's return.
            stale_fallback_metrics: list[str] = []
            # Metrics suppressed by the |ratio| > 1000 garbage-value bound below - tracked
            # separately from failed_metrics because "we computed a real ratio and threw it
            # away as implausible" (near-zero-denominator extraction artifact, or a
            # legitimately near-zero-revenue filer like a pre-revenue biotech/SPAC) is a
            # materially different situation from "SEC never reported the inputs at all", and
            # both were previously labeled with the same generic "missing_sec_data" reason.
            implausible_ratio_metrics: list[str] = []
            # Tracks the reason for the sign-change guards below (a YoY comparison that flips
            # sign, e.g. -$15M to +$2M, produces a meaningless growth percentage).
            sign_change_yoy_metrics: list[str] = []
            # A prior-year base under 1% of that year's revenue is too small to produce a
            # meaningful growth percentage even without a sign flip - mark unavailable rather
            # than compute a technically-real but misleading number.
            immaterial_base_yoy_metrics: list[str] = []

            # ROE = Net Income / Shareholders' Equity. Same near-zero-denominator garbage-value
            # bound as the other ratios in this function; falls back to the most recent OTHER
            # fiscal year with a plausible pair before giving up as implausible_ratio.
            metrics["roe"], _roe_implausible = self._ratio_with_implausible_fallback(
                symbol, net_income, stockholders_equity, "net_income", "stockholders_equity"
            )
            if metrics["roe"] is None:
                failed_metrics.append("roe")
                if _roe_implausible:
                    implausible_ratio_metrics.append("roe")

            # ROA = Net Income / Total Assets. Same bound and cross-year fallback as roe above.
            metrics["roa"], _roa_implausible = self._ratio_with_implausible_fallback(
                symbol, net_income, total_assets, "net_income", "total_assets"
            )
            if metrics["roa"] is None:
                failed_metrics.append("roa")
                if _roa_implausible:
                    implausible_ratio_metrics.append("roa")

            # Operating Margin = Operating Income / Revenue
            # Fallback for banks (NULL revenue): use Operating Income / Total Assets instead
            # EBIT-approximation fallback (pretax_income + interest_expense), same as
            # interest_coverage_operating_income/roic_operating_income above - uses the anchor
            # row's own pretax_income/interest_expense (not the cross-year-searched value) so
            # numerator and denominator (revenue) stay from the same fiscal year.
            operating_income_for_margin = operating_income
            if operating_income_for_margin is None and pretax_income is not None:
                operating_income_for_margin = pretax_income + (interest_expense or 0)
            # Some REIT/tonnage-tax filers (AGNC/ARE/AMH-class) never tag OperatingIncomeLoss OR
            # pretax_income/income_tax_expense at all - a permanent different-accounting-model
            # gap, not an XBRL extraction failure, so recategorize as "reit_special_entity"
            # rather than "missing_sec_data" once confirmed unrecoverable (reuses the same
            # _get_no_tax_concept_symbols() 3-consecutive-year check as roic_pct's
            # effective_tax_rate=0.0 branch). Deliberately does not attempt a numeric
            # reconstruction here (net_income-based reconstruction was tried and rejected
            # elsewhere in this file - too much deviation). sustainable_growth_rate is
            # unaffected since its ROE input only needs net_income+equity.
            no_operating_income_concept = (
                operating_income_for_margin is None and symbol in self._get_no_tax_concept_symbols()
            )
            if operating_income_for_margin is not None:
                operating_margin_denominator_field = None
                if revenue is not None and revenue > 0:
                    computed_operating_margin = (operating_income_for_margin / revenue) * 100
                    operating_margin_denominator_field = "revenue"
                elif total_assets is not None and total_assets != 0:
                    # Fallback: ROA of operating income (useful for banks with NULL revenue)
                    computed_operating_margin = (operating_income_for_margin / total_assets) * 100
                    operating_margin_denominator_field = "total_assets"
                else:
                    computed_operating_margin = None
                if computed_operating_margin is None:
                    failed_metrics.append("operating_margin")
                else:
                    # Same near-zero-denominator garbage-value bound as gross_margin/
                    # ebitda_margin/roic_pct above.
                    if abs(computed_operating_margin) > 1000:
                        # Same cross-year fallback as ROE/ROA/roic_pct - search for an older
                        # fiscal year with a plausible same-year (operating_income, denominator)
                        # pair, using the SAME denominator field the anchor year used (revenue
                        # vs total_assets), before giving up as implausible.
                        operating_margin_fallback = (
                            self._find_plausible_cross_year_ratio(
                                symbol, "operating_income", operating_margin_denominator_field
                            )
                            if operating_margin_denominator_field is not None
                            else None
                        )
                        if operating_margin_fallback is not None:
                            metrics["operating_margin"] = operating_margin_fallback
                            stale_fallback_metrics.append("operating_margin")
                        else:
                            failed_metrics.append("operating_margin")
                            implausible_ratio_metrics.append("operating_margin")
                    else:
                        metrics["operating_margin"] = float(computed_operating_margin)
            else:
                failed_metrics.append("operating_margin")

            # Net Margin = Net Income / Revenue
            # Fallback for banks (NULL revenue): use Net Income / Total Assets instead
            if net_income is not None:
                net_margin_denominator_field = None
                if revenue is not None and revenue > 0:
                    computed_net_margin = (net_income / revenue) * 100
                    net_margin_denominator_field = "revenue"
                elif total_assets is not None and total_assets != 0:
                    # Fallback: ROA of net income (useful for banks with NULL revenue)
                    computed_net_margin = (net_income / total_assets) * 100
                    net_margin_denominator_field = "total_assets"
                else:
                    computed_net_margin = None
                if computed_net_margin is None:
                    failed_metrics.append("net_margin")
                else:
                    # Same near-zero-denominator garbage-value bound as the margins above.
                    if abs(computed_net_margin) > 1000:
                        # Same cross-year fallback as operating_margin above.
                        net_margin_fallback = (
                            self._find_plausible_cross_year_ratio(symbol, "net_income", net_margin_denominator_field)
                            if net_margin_denominator_field is not None
                            else None
                        )
                        if net_margin_fallback is not None:
                            metrics["net_margin"] = net_margin_fallback
                            stale_fallback_metrics.append("net_margin")
                        else:
                            failed_metrics.append("net_margin")
                            implausible_ratio_metrics.append("net_margin")
                    else:
                        metrics["net_margin"] = float(computed_net_margin)
            else:
                failed_metrics.append("net_margin")

            # Debt to Equity is computed after roic_pct below, alongside ROCE, from
            # debt_for_roic (interest-bearing debt) / equity - NOT Total Liabilities / Equity,
            # which is a different, broader ratio (includes AP/deferred revenue/accrued
            # expenses) than what "Debt-to-Equity" means in standard finance usage or what was
            # Fama-MacBeth validated for this factor.

            # Debt to Assets = Total Liabilities / Total Assets
            # Same >1000 near-zero-denominator bound as the other ratios in this function.
            if total_liabilities is not None and total_assets is not None and total_assets != 0:
                computed_debt_to_assets = total_liabilities / total_assets
                if abs(computed_debt_to_assets) > 1000:
                    failed_metrics.append("debt_to_assets")
                    implausible_ratio_metrics.append("debt_to_assets")
                else:
                    metrics["debt_to_assets"] = float(computed_debt_to_assets)
            else:
                failed_metrics.append("debt_to_assets")

            # Current Ratio = Current Assets / Current Liabilities
            # Same >1000 bound as the other ratios above.
            if current_assets is not None and current_liabilities is not None and current_liabilities != 0:
                computed_current_ratio = current_assets / current_liabilities
                if abs(computed_current_ratio) > 1000:
                    failed_metrics.append("current_ratio")
                    implausible_ratio_metrics.append("current_ratio")
                else:
                    metrics["current_ratio"] = float(computed_current_ratio)
            else:
                failed_metrics.append("current_ratio")

            # Quick Ratio = (Current Assets - Inventory) / Current Liabilities
            # `inventory` NULL means genuinely none carried (service/software) or simply not
            # broken out - treat as 0 rather than failing the metric, same as IBD/most screeners.
            # Same >1000 bound as current_ratio above (shares the same denominator).
            if current_assets is not None and current_liabilities is not None and current_liabilities != 0:
                computed_quick_ratio = (current_assets - (inventory or 0)) / current_liabilities
                if abs(computed_quick_ratio) > 1000:
                    failed_metrics.append("quick_ratio")
                    implausible_ratio_metrics.append("quick_ratio")
                else:
                    metrics["quick_ratio"] = float(computed_quick_ratio)
            else:
                failed_metrics.append("quick_ratio")

            # REITs/banks file unclassified balance sheets and never report
            # AssetsCurrent/LiabilitiesCurrent - a permanent structural gap, distinct from an
            # ordinary filer's one-year extraction/timing gap, so check full symbol history.
            unclassified_balance_sheet = (
                current_assets is None
                and current_liabilities is None
                and symbol in self._get_unclassified_balance_sheet_symbols()
            )

            # Companies that stop itemizing interest_expense (debt-free, or netted into other
            # income/expense) never report it again - full-history check, not just this row.
            no_recent_interest_expense = interest_expense is None and (
                symbol in self._get_no_recent_interest_expense_symbols()
                or symbol in self._get_never_tagged_interest_expense_symbols()
            )
            # REITs with real interest_expense (mortgage debt) but no operating_income/
            # pretax_income concept ever tagged fail interest_coverage on the operating-income
            # side, not interest_expense - distinct from no_recent_interest_expense above.
            no_operating_income_concept_ic = (
                interest_coverage_operating_income is None and symbol in self._get_no_tax_concept_symbols()
            )

            # Interest Coverage = Operating Income / Interest Expense. Higher is better
            # (ability to service debt from operating earnings). Column existed on
            # quality_metrics (migration predates this loader) and is already displayed by
            # the frontend/API, but no loader ever computed it - annual_income_statement had
            # no interest_expense column until migration 1145. Only computed when
            # interest_expense > 0 (zero debt service is a real "not applicable" case, not
            # an infinite/undefined ratio to fake a max score for).
            if interest_expense is not None and interest_expense > 0 and interest_coverage_operating_income is not None:
                computed_interest_coverage = interest_coverage_operating_income / interest_expense
                # Negligibly small denominator = noise; also floor interest_expense < 1% of
                # |op_income| (RESTORED 2026-09-08, dropped by c9b0e2088; `70e20b7b8`).
                _ic_immaterial = interest_expense < abs(interest_coverage_operating_income) * 0.01
                if abs(computed_interest_coverage) > 1000 or _ic_immaterial:
                    # Same cross-year fallback as operating_margin/net_margin/roic_pct above.
                    interest_coverage_fallback = self._find_plausible_cross_year_ratio(
                        symbol, "operating_income", "interest_expense", as_percentage=False
                    )
                    if interest_coverage_fallback is not None:
                        metrics["interest_coverage"] = interest_coverage_fallback
                        stale_fallback_metrics.append("interest_coverage")
                    else:
                        failed_metrics.append("interest_coverage")
                        implausible_ratio_metrics.append("interest_coverage")
                else:
                    metrics["interest_coverage"] = float(computed_interest_coverage)
            else:
                failed_metrics.append("interest_coverage")

            # Extract EV metrics from sec_valuations if available
            total_debt_ev = None
            total_cash_ev = None
            ebitda_ev = None
            # sec_valuations' own `reason` column carries a specific cause (e.g.
            # "income_statement_revenue_and_eps_null") - prefer it over a generic bucket.
            # `len(ev_metrics) > 3` guards callers/tests still passing the older 3-tuple shape.
            sec_valuations_reason = ev_metrics[3] if ev_metrics and len(ev_metrics) > 3 else None
            if ev_metrics:
                total_debt_ev = self._nan_to_none(safe_float(ev_metrics[0], f"{symbol}.total_debt", allow_none=True))
                total_cash_ev = self._nan_to_none(safe_float(ev_metrics[1], f"{symbol}.total_cash", allow_none=True))
                ebitda_ev = self._nan_to_none(safe_float(ev_metrics[2], f"{symbol}.ebitda", allow_none=True))

            # Gross Margin = Gross Profit / Revenue. Prefers gross_profit directly from SEC
            # data over computing it from cost_of_revenue, with a prior-year fallback (like
            # ROIC/interest_coverage) when the anchor year has neither. Fetched as a triple
            # (gross_profit, cost_of_revenue, revenue) to avoid year mismatches.
            gross_profit_used = None
            gross_profit_revenue = revenue  # Track which revenue used (for margin calc)

            if gross_profit_direct is not None:
                gross_profit_used = gross_profit_direct
            elif cost_of_revenue is not None and revenue is not None:
                gross_profit_used = revenue - cost_of_revenue

            # Fallback to prior year if current year lacks both sources
            if gross_profit_used is None and (gross_profit_direct is None and cost_of_revenue is None):
                # `data_unavailable IS NOT TRUE` (applied inside the helper) excludes
                # incomplete/unfiled stub rows, which under-report vs the real complete fiscal
                # year.
                fallback_gm_row = self._fetch_annual_fallback_row(
                    "annual_income_statement",
                    "gross_profit, cost_of_revenue, revenue",
                    "AND (gross_profit IS NOT NULL OR cost_of_revenue IS NOT NULL) AND revenue IS NOT NULL",
                    symbol,
                )
                if fallback_gm_row:
                    fallback_gross_profit = self._nan_to_none(
                        safe_float(fallback_gm_row[0], f"{symbol}.gross_profit_fallback_year", allow_none=True)
                    )
                    fallback_cost_of_revenue = self._nan_to_none(
                        safe_float(fallback_gm_row[1], f"{symbol}.cost_of_revenue_fallback_year", allow_none=True)
                    )
                    fallback_revenue = self._nan_to_none(
                        safe_float(fallback_gm_row[2], f"{symbol}.revenue_fallback_year", allow_none=True)
                    )
                    if fallback_gross_profit is not None:
                        gross_profit_used = fallback_gross_profit
                        gross_profit_revenue = fallback_revenue
                    elif fallback_cost_of_revenue is not None and fallback_revenue is not None:
                        gross_profit_used = fallback_revenue - fallback_cost_of_revenue
                        gross_profit_revenue = fallback_revenue

            # Still None here means this symbol has never once reported gross_profit or
            # cost_of_revenue - banks, insurers, and service/REIT filers legitimately don't
            # break out a COGS line at all (structural gap, not a data gap).
            no_gross_profit_concept = gross_profit_used is None

            if gross_profit_used is not None and gross_profit_revenue is not None and gross_profit_revenue != 0:
                # Bound the ratio - a real but implausibly tiny revenue relative to gross_profit
                # (e.g. a mis-scaled/mis-tagged SEC fact) explodes this into nonsense.
                #
                # FIXED 2026-09-06 (goal session: "SEC/XBRL missing data to zero" / implausible-
                # values audit): unlike EBITDA margin or ROE/ROA (which can legitimately exceed
                # 100% - the shared |ratio|>1000 bound below is correct for those), gross margin
                # is capped at 100% by definition (gross_profit = revenue - cost_of_revenue, and
                # cost_of_revenue is never negative for a real filer) - the old 1000% bound let
                # values like 138.5% straight through unflagged. Live-confirmed via SAN/BBVA/GFR
                # (foreign banks): quality_metrics.gross_margin stored 138.54/140.53/107.29 with
                # gross_margin_unavailable_reason=NULL, feeding directly into Quality scoring.
                # Root cause there is a real, current concept mismatch (GrossProfit is a broad
                # IFRS bank "total operating income" concept, but the interest_revenue_expense
                # fallback-only concept mapped to our "revenue" column is a much narrower net-
                # interest-income figure for these filers - see _REVENUE_FALLBACK_ONLY_FIELDS'
                # comment on interest_revenue_expense) rather than a stale/mis-tagged value, so
                # there's no better concept to substitute - flagging it as implausible (same
                # governance as every other implausible-ratio rejection in this file) is the
                # correct outcome, not a false positive: 105% buffer allows for the rare
                # legitimate edge case (a vendor-rebate credit or other negative-COGS item
                # pushing slightly over 100%) without accepting a genuinely impossible value.
                computed_gross_margin = (gross_profit_used / gross_profit_revenue) * 100
                if computed_gross_margin > 105 or computed_gross_margin < -1000:
                    # Same cross-year fallback as operating_margin/net_margin/interest_coverage
                    # above - search for an older fiscal year with a plausible same-year
                    # (gross_profit, revenue) pair. The shared helper's own |ratio|<=1000 bound
                    # is too loose for gross_margin specifically (see above) - re-validate its
                    # candidate against the same >105% ceiling before accepting it.
                    gross_margin_fallback = self._find_plausible_cross_year_ratio(symbol, "gross_profit", "revenue")
                    if gross_margin_fallback is not None and gross_margin_fallback <= 105:
                        metrics["gross_margin"] = gross_margin_fallback
                        stale_fallback_metrics.append("gross_margin")
                    else:
                        failed_metrics.append("gross_margin")
                        implausible_ratio_metrics.append("gross_margin")
                else:
                    metrics["gross_margin"] = float(computed_gross_margin)
            else:
                failed_metrics.append("gross_margin")

            # EBITDA Margin = EBITDA / Revenue
            if ebitda_ev is not None and revenue is not None and revenue != 0:
                # Same near-zero-denominator bound as gross_margin above.
                computed_ebitda_margin = (ebitda_ev / revenue) * 100
                if abs(computed_ebitda_margin) > 1000:
                    ebitda_margin_fallback = self._find_plausible_cross_year_ebitda_margin_ratio(symbol)
                    if ebitda_margin_fallback is not None:
                        metrics["ebitda_margin"] = ebitda_margin_fallback
                        stale_fallback_metrics.append("ebitda_margin")
                    else:
                        failed_metrics.append("ebitda_margin")
                        implausible_ratio_metrics.append("ebitda_margin")
                else:
                    metrics["ebitda_margin"] = float(computed_ebitda_margin)
            else:
                failed_metrics.append("ebitda_margin")

            # ROIC = NOPAT / Invested Capital, NOPAT = EBIT * (1 - effective_tax_rate). No
            # hardcoded tax-rate assumption - only real SEC-reported tax/pretax concepts are
            # used (a fabricated 0.21/0.25 fallback was rejected/reverted). Pulled as one row
            # (not independent lookups) so NOPAT never mixes mismatched fiscal years.
            anchor_interest_expense_for_roic = self._nan_to_none(
                safe_float(quality_row[10], f"{symbol}.interest_expense_roic_anchor", allow_none=True)
            )
            roic_tax_expense, roic_pretax_income, roic_operating_income, roic_interest_expense, roic_net_income = (
                income_tax_expense,
                pretax_income,
                operating_income,
                anchor_interest_expense_for_roic,
                net_income,
            )
            # Banks especially often have tax+pretax in the anchor year but neither
            # operating_income nor interest_expense that same year (both untagged) - trigger
            # the rescue search below even when tax/pretax themselves are present.
            if (
                income_tax_expense is None
                or pretax_income is None
                or (operating_income is None and anchor_interest_expense_for_roic is None)
            ):
                with _owner().DatabaseContext("read") as cur:
                    # First try: tax+pretax together in recent history (3 years). Prefer a
                    # row that also has operating_income or interest_expense (either lets
                    # NOPAT compute - operating_income directly, interest_expense via EBIT
                    # approximation), but don't require it - a tax/pretax-only row still
                    # unblocks effective_tax_rate even if NOPAT itself later fails.
                    # `data_unavailable IS NOT TRUE` excludes incomplete/unfiled stub rows.
                    cur.execute(
                        """
                        SELECT income_tax_expense, pretax_income, operating_income, interest_expense, net_income
                        FROM annual_income_statement
                        WHERE symbol = %s AND income_tax_expense IS NOT NULL
                          AND pretax_income IS NOT NULL AND data_unavailable IS NOT TRUE
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                        ORDER BY (CASE WHEN operating_income IS NOT NULL OR interest_expense IS NOT NULL
                                       THEN 0 ELSE 1 END), fiscal_year DESC
                        LIMIT 1
                        """,
                        (symbol,),
                    )
                    fallback_tax_row = cur.fetchone()

                    # Widen to full history if the 3-year window found nothing, OR found a
                    # tax/pretax row that still can't recover operating_income/interest_expense
                    # (both None) - a 3-year match on tax/pretax alone must not short-circuit
                    # the widen, since it recovers nothing this fallback needs. Keep the 3-year
                    # row (still unblocks effective_tax_rate) if the wider search also empties.
                    if not fallback_tax_row or (fallback_tax_row[2] is None and fallback_tax_row[3] is None):
                        cur.execute(
                            """
                            SELECT income_tax_expense, pretax_income, operating_income, interest_expense, net_income
                            FROM annual_income_statement
                            WHERE symbol = %s AND income_tax_expense IS NOT NULL
                              AND pretax_income IS NOT NULL AND data_unavailable IS NOT TRUE
                            ORDER BY (CASE WHEN operating_income IS NOT NULL OR interest_expense IS NOT NULL
                                           THEN 0 ELSE 1 END), fiscal_year DESC
                            LIMIT 1
                            """,
                            (symbol,),
                        )
                        wider_fallback_tax_row = cur.fetchone()
                        if wider_fallback_tax_row:
                            fallback_tax_row = wider_fallback_tax_row

                if fallback_tax_row:
                    # The search above ranks candidate years by "has operating_income or
                    # interest_expense" ABOVE recency, so it can pick an older, worse year's
                    # tax/pretax over the anchor's own good ones (e.g. a stale loss year beating
                    # a current profitable one for insurers, who often lack both concepts even
                    # when otherwise current). Only take the fallback row's tax/pretax when the
                    # anchor didn't already have real values - this fallback exists solely to
                    # recover operating_income/interest_expense for NOPAT, never to override an
                    # anchor year's own good profitability figures.
                    if roic_tax_expense is None:
                        roic_tax_expense = self._nan_to_none(
                            safe_float(
                                fallback_tax_row[0], f"{symbol}.income_tax_expense_fallback_year", allow_none=True
                            )
                        )
                    if roic_pretax_income is None:
                        roic_pretax_income = self._nan_to_none(
                            safe_float(fallback_tax_row[1], f"{symbol}.pretax_income_fallback_year", allow_none=True)
                        )
                    # Same "don't clobber a real anchor-year value" guard for
                    # operating_income/interest_expense - otherwise the anchor year's real
                    # operating_income could get mixed with a different fallback year's
                    # interest_expense (or vice versa).
                    if roic_operating_income is None:
                        roic_operating_income = self._nan_to_none(
                            safe_float(fallback_tax_row[2], f"{symbol}.operating_income_fallback_year", allow_none=True)
                        )
                    if roic_interest_expense is None:
                        roic_interest_expense = self._nan_to_none(
                            safe_float(fallback_tax_row[3], f"{symbol}.interest_expense_fallback_year", allow_none=True)
                        )
                    if roic_net_income is None:
                        roic_net_income = self._nan_to_none(
                            safe_float(fallback_tax_row[4], f"{symbol}.net_income_fallback_year", allow_none=True)
                        )

            # FIXED 2026-09-10 (goal: "SEC/XBRL missing data under 500" sweep,
            # operating_income_not_itemized investigation): a symbol that is already
            # double-confirmed structurally debt-free (never tagged ANY debt component AND
            # never tagged interest_expense - same gate debt_for_roic/total_debt above already
            # trust for a real $0) still fell through this EBIT-approximation fallback because
            # roic_interest_expense stayed None instead of the real $0 it corroborates, so a
            # symbol with a perfectly real, current roic_pretax_income (e.g. EDHL, NEWP) got no
            # roic_operating_income at all - falling to the generic "operating_income_not_itemized"
            # catch-all instead of the correct EBIT = pretax_income + $0 interest. Mirrors the
            # debt_for_roic coercion above exactly, just applied to the other addend of this
            # same formula.
            if (
                roic_interest_expense is None
                and symbol in self._get_never_tagged_debt_components_symbols()
                and symbol in self._get_never_tagged_interest_expense_symbols()
            ):
                roic_interest_expense = 0.0

            if roic_operating_income is None and roic_pretax_income is not None and roic_interest_expense is not None:
                # EBIT approximation fallback - see comment above. roic_interest_expense is
                # always from the same row as roic_pretax_income (anchor or fallback_tax_row),
                # so this never mixes fiscal years.
                roic_operating_income = roic_pretax_income + roic_interest_expense

            # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): the never-tagged-
            # pretax-income derivation just below (in the effective_tax_rate branches) used to
            # only handle the case where the derived base (net_income + tax_expense) came out
            # POSITIVE - a loss-making filer with this exact profile (REITs aside, live-confirmed
            # CVNA/TRDA/FATE and 16 more of 19 universe rows) got NEITHER a computed roic_pct NOR
            # the correct "unprofitable_stock" reason, silently falling to the generic
            # "missing_sec_data" catch-all instead, since roic_pretax_income stayed None and the
            # roic_pct_unprofitable check just below never saw it. Deriving roic_pretax_income
            # itself here - unconditional of sign - lets that check correctly classify a
            # negative/zero derived base, and the existing effective_tax_rate branch below
            # handles the positive case with the identical formula a since-removed dedicated
            # branch used to compute separately.
            if (
                roic_pretax_income is None
                and roic_tax_expense is not None
                and roic_tax_expense != 0
                and roic_net_income is not None
                and symbol in self._get_never_tagged_pretax_income_symbols()
            ):
                roic_pretax_income = roic_net_income + roic_tax_expense

            # No hardcoded tax-rate assumption - only real SEC-reported IncomeTaxExpenseBenefit/
            # pretax_income concepts are used (a fabricated 0.21/0.25 fallback was rejected).
            # Bounded to [-60%, 60%]: an implausible rate (near-zero pretax income swamped by an
            # unrelated tax swing) would distort NOPAT worse than marking unavailable, but a
            # real net tax benefit in a profitable year (R&D credits, valuation-allowance
            # releases) is normal and should compute, hence the symmetric range rather than
            # [0, 60%] alone.
            roic_pct_unprofitable = roic_pretax_income is not None and roic_pretax_income <= 0
            effective_tax_rate = None
            if roic_tax_expense is not None and roic_pretax_income is not None and roic_pretax_income > 0:
                candidate_rate = roic_tax_expense / roic_pretax_income
                if -0.60 <= candidate_rate <= 0.60:
                    effective_tax_rate = candidate_rate
                else:
                    implausible_ratio_metrics.append("roic_pct")
            elif (
                roic_tax_expense is None and roic_pretax_income is None and symbol in self._get_no_tax_concept_symbols()
            ):
                # See _get_no_tax_concept_symbols - a filer that has never once tagged a tax
                # concept is structurally tax-exempt (Marine Shipping tonnage-tax filers,
                # REITs), not missing data. NOPAT = operating_income * (1 - 0%).
                effective_tax_rate = 0.0
            elif roic_tax_expense == 0 and roic_pretax_income is None:
                # Some filers (simple loss-making biotechs/small-caps) tag
                # IncomeTaxExpenseBenefit=$0 every year but never tag any pretax_income concept
                # (nothing to reconcile with $0 tax). This needs no net_income+tax_expense
                # approximation (rejected elsewhere as too imprecise, ~25% deviation from
                # NCI/discontinued-ops noise) - effective_tax_rate = tax/pretax is exact algebra
                # when tax is EXACTLY 0: 0/x = 0 for any nonzero x.
                effective_tax_rate = 0.0
            # The never-tagged-pretax-income REIT/mortgage-trust case (net_income+tax_expense
            # approximation) is now handled uniformly above by deriving roic_pretax_income
            # itself before this if/elif chain runs - a positive derived value reaches the
            # first branch above with the identical candidate_rate formula this elif used to
            # compute separately; a non-positive one is correctly caught by
            # roic_pct_unprofitable instead. See this function's own comment just above the
            # roic_pretax_income derivation for the fix history.

            # Invested Capital = Stockholders' Equity + Total Debt - Cash & Equivalents
            # Use total_debt_ev (from sec_valuations, 81% available) as primary source
            # Fall back to long_term_debt_bs (from balance_sheet, only 22% available) if needed
            # ROIC requires complete balance sheet data, not partial guesses. A prior session
            # added a (total_liabilities - current_liabilities) debt estimate - reverted: that
            # includes non-debt liabilities (AP, accrued expenses, deferred revenue, pensions),
            # so it is not a real "total debt" figure.
            #
            # stockholders_equity/cash_and_equivalents get the same same-year-substitute
            # treatment as the tax triple above, for the same reason (76% cash coverage in the
            # FCF-prioritized row vs a different year that has it).
            roic_stockholders_equity, roic_cash_and_equivalents = stockholders_equity, cash_and_equivalents_bs
            if stockholders_equity is None or cash_and_equivalents_bs is None:
                # `data_unavailable IS NOT TRUE` (applied inside the helper) excludes an
                # incomplete/unfiled or stale-orphan (see sec_base.py's
                # stale_fiscal_year_not_confirmed_by_full_sec_refetch) fiscal year's stub.
                fallback_bs_row = self._fetch_annual_fallback_row(
                    "annual_balance_sheet",
                    "stockholders_equity, cash_and_equivalents",
                    "AND stockholders_equity IS NOT NULL AND cash_and_equivalents IS NOT NULL",
                    symbol,
                )

                if fallback_bs_row:
                    roic_stockholders_equity = self._nan_to_none(
                        safe_float(fallback_bs_row[0], f"{symbol}.stockholders_equity_fallback_year", allow_none=True)
                    )
                    roic_cash_and_equivalents = self._nan_to_none(
                        safe_float(fallback_bs_row[1], f"{symbol}.cash_and_equivalents_fallback_year", allow_none=True)
                    )

            # Banks often tag deposits/FHLB advances/subordinated debentures under concepts
            # this pipeline doesn't map to "long_term_debt" for the current fiscal year, even
            # though an older 10-K (within the 3-year lookback) has a real figure.
            # total_debt_ev has no fiscal-year dimension (sec_valuations is a single
            # latest-snapshot row), so only long_term_debt_bs can be rescued this way - only
            # search when total_debt_ev is also absent (it remains the primary source below).
            #
            # `0 < x < 1000` treated the same as missing for BOTH total_debt_ev and
            # long_term_debt_bs - ADDED 2026-09-07 (goal: "digging into scores" audit,
            # anchor-fiscal-year-mismatch follow-up). Live-confirmed FLZH: both
            # sec_valuations.total_debt (total_debt_ev, a separate loader/table) AND this
            # anchor row's own long_term_debt were the identical real-but-immaterial $0.01
            # stub - an as-yet-unfiled current fiscal year's rounding/placeholder artifact
            # (same class this file already treats interest_expense<=0 as invalid for just
            # above, not merely None). Since $0.01 is non-NULL in both places, neither the
            # "is None" check here nor total_debt_ev's own unconditional priority below ever
            # caught it, so debt_for_roic paired FY2026's real $191.9M stockholders_equity
            # with essentially zero debt (debt_to_equity≈0.00) while total_liabilities/
            # total_assets (which DO have their own None-triggered fallback above) correctly
            # fell back to FY2025's real $45.5M liabilities/$332K assets - two supposedly-
            # paired leverage ratios for the same company computed from two different,
            # inconsistent fiscal years. $1000 is far below any economically meaningful
            # long-term-debt figure for a real filer (SEC XBRL reports whole dollars, not
            # thousands) while comfortably above a genuine $0 "no debt" tag, which stays
            # untouched (only a non-zero, sub-floor value is treated as a stub).
            _total_debt_ev_is_stub = total_debt_ev is not None and 0 < total_debt_ev < 1000
            _long_term_debt_bs_is_stub = long_term_debt_bs is not None and 0 < long_term_debt_bs < 1000
            roic_long_term_debt = None if _long_term_debt_bs_is_stub else long_term_debt_bs
            if (total_debt_ev is None or _total_debt_ev_is_stub) and (
                long_term_debt_bs is None or _long_term_debt_bs_is_stub
            ):
                # `data_unavailable IS NOT TRUE` (applied inside the helper) excludes an
                # incomplete/stale-orphan stub.
                fallback_debt = self._fetch_balance_sheet_anchor_fallback(symbol, "long_term_debt")
                if fallback_debt is not None:
                    roic_long_term_debt = fallback_debt
                else:
                    # A filer with real short_term_debt/lease liabilities but no long_term_debt
                    # tag (ATHR/BRNS) reaches this - see the fallback's own docstring.
                    fallback_all_debt = self._fetch_total_debt_components_fallback(symbol)
                    if fallback_all_debt is not None:
                        roic_long_term_debt = fallback_all_debt

            invested_capital = None
            debt_for_roic = (
                total_debt_ev if total_debt_ev is not None and not _total_debt_ev_is_stub else roic_long_term_debt
            )

            # Depository institutions AND risk-bearing insurance underwriters: override with
            # total_liabilities when available. A bank's core liability (customer deposits) and
            # an underwriter's (policy/loss reserves) are both functionally interest-bearing
            # debt but aren't tagged under long_term_debt/total_debt_ev (see
            # DEPOSITORY_BANK_INDUSTRIES/INSURANCE_UNDERWRITER_INDUSTRIES's docstrings in
            # load_value_quality_growth_metrics.py for the live-verified impact on each - e.g.
            # deposit-funded small banks like TCBX/PEBK showing debt_to_equity ~0.11, and
            # underwriters like RGA/ACGL/HIG showing ~0.01-0.42 vs a real ~2.5-11.5x). Narrowly
            # scoped to these two SIC industry lists, not the broader Financial Services sector
            # (payment networks/asset managers/insurance brokers keep the universal
            # interest-bearing-debt figure, where total_liabilities' AP/accrued/deferred-revenue
            # contamination would be a real, not negligible, distortion).
            if total_liabilities is not None and self._get_symbol_industry(symbol) in (
                _owner().DEPOSITORY_BANK_INDUSTRIES | _owner().INSURANCE_UNDERWRITER_INDUSTRIES
            ):
                debt_for_roic = total_liabilities

            # A symbol that has never tagged ANY debt component across its full balance-sheet
            # history AND never reports nonzero interest_expense is double-confirmed
            # structurally debt-free (SPACs, pre-revenue biotech, small tech/services - see
            # _get_never_tagged_debt_components_symbols()'s docstring), not an extraction gap.
            # Mirrors load_sec_valuations.py's own EV treatment of missing total_debt as 0, but
            # requires the interest_expense corroboration since debt_to_equity/roce_pct/
            # roic_pct feed real trading scores and a false "0 debt" would overstate safety.
            if (
                debt_for_roic is None
                and symbol in self._get_never_tagged_debt_components_symbols()
                and symbol in self._get_never_tagged_interest_expense_symbols()
            ):
                debt_for_roic = 0.0

            if (
                roic_stockholders_equity is not None
                and debt_for_roic is not None
                and roic_cash_and_equivalents is not None
            ):
                invested_capital = roic_stockholders_equity + debt_for_roic - roic_cash_and_equivalents
            # A large cash pile (common for well-capitalized biotechs, e.g. equity-raise-funded)
            # can push equity + debt - cash negative even with real, complete SEC data - a real
            # business-state fact, not an absent concept (same distinction as
            # roic_pct_unprofitable below for pretax losses).
            roic_pct_negative_invested_capital = invested_capital is not None and invested_capital <= 0
            # roic_operating_income (NOPAT's other input) can independently be None for
            # no-tax-concept REITs even when effective_tax_rate's own branch already handles
            # them - same structural-not-missing gate.
            no_operating_income_concept_roic = (
                roic_operating_income is None and symbol in self._get_no_tax_concept_symbols()
            )

            if (
                effective_tax_rate is not None
                and roic_operating_income is not None
                and invested_capital is not None
                and invested_capital > 0
            ):
                nopat = roic_operating_income * (1 - effective_tax_rate)
                # Same near-zero-denominator bound as gross_margin/ebitda_margin/
                # interest_coverage above - invested_capital > 0 only rules out literal zero,
                # not an implausibly tiny-but-positive value that explodes the ratio.
                computed_roic_pct = (nopat / invested_capital) * 100
                # ADDED 2026-09-08 (goal: score/tie-out sanity sweep - live-caught via
                # ScoreRatioOutlierChecker's roce_pct batch, see roce_pct's own materiality-floor
                # fix immediately below for the INR evidence this shares a root cause with):
                # invested_capital > 0 only rules out literal zero, exactly the gap this
                # block's own comment above already flagged without closing it - a real-but-
                # immaterial invested_capital (e.g. a company funded almost entirely by current
                # liabilities, with only a token sliver of equity+debt-minus-cash) can still
                # produce a computed_roic_pct UNDER the |ratio|>1000 bound while still being a
                # near-zero-denominator artifact, same bug class as interest_coverage's
                # interest_expense floor. Folded into the existing >1000 branch (rather than a
                # separate gate) so it gets the identical treatment: try the cross-year
                # fallback first, only fail as implausible_ratio if that also comes up empty.
                if abs(computed_roic_pct) > 1000 or invested_capital < 0.01 * abs(nopat):
                    roic_fallback = self._find_plausible_cross_year_roic_ratio(symbol, "roic_pct")
                    if roic_fallback is not None:
                        metrics["roic_pct"] = roic_fallback
                        stale_fallback_metrics.append("roic_pct")
                    else:
                        failed_metrics.append("roic_pct")
                        implausible_ratio_metrics.append("roic_pct")
                else:
                    metrics["roic_pct"] = float(computed_roic_pct)
            else:
                failed_metrics.append("roic_pct")

            # ROCE = EBIT / (Equity + Debt), deliberately NO cash subtraction - unlike roic_pct
            # above, whose cash-netted invested_capital goes negative for well-capitalized,
            # profitable companies. roic_operating_income is used as the EBIT proxy (pretax,
            # classic ROCE convention - not NOPAT). Replaces roic_score in the composite (see
            # weighted_score) - more stable and higher coverage per FM validation.
            capital_employed = (
                roic_stockholders_equity + debt_for_roic
                if roic_stockholders_equity is not None and debt_for_roic is not None
                else None
            )
            roce_pct_negative_capital_employed = capital_employed is not None and capital_employed <= 0
            if roic_operating_income is not None and capital_employed is not None and capital_employed > 0:
                computed_roce_pct = (roic_operating_income / capital_employed) * 100
                # ADDED 2026-09-08 (goal: score/tie-out sanity sweep, live-caught via
                # ScoreRatioOutlierChecker's newly-added roce_pct outlier batch): INR live-
                # confirmed the exact same immaterial-denominator bug class as interest_coverage/
                # forward_pe this session - stockholders_equity=$0.00 (exactly) and
                # debt_for_roic~$1.2M against $1.24B total_assets, so capital_employed > 0 was
                # real but economically negligible, producing roce_pct=989.60 (just under the
                # >1000 ceiling, so never excluded) off a capital base worth ~0.1% of the
                # balance sheet. Folded into the existing >1000 branch (same treatment as
                # roic_pct's own fix above) so it tries the cross-year fallback first.
                if abs(computed_roce_pct) > 1000 or capital_employed < 0.01 * abs(roic_operating_income):
                    roce_fallback = self._find_plausible_cross_year_roic_ratio(symbol, "roce_pct")
                    if roce_fallback is not None:
                        metrics["roce_pct"] = roce_fallback
                        stale_fallback_metrics.append("roce_pct")
                    else:
                        failed_metrics.append("roce_pct")
                        implausible_ratio_metrics.append("roce_pct")
                else:
                    metrics["roce_pct"] = float(computed_roce_pct)
            else:
                failed_metrics.append("roce_pct")

            # Debt to Equity: interest-bearing Debt / Equity (replaced the old Total
            # Liabilities / Equity formula). Reuses debt_for_roic/roic_stockholders_equity, same
            # inputs as ROIC/ROCE above. Correlates strongly with debt_to_assets (corr=0.67), so
            # replaces it in the composite rather than being scored alongside it.
            if roic_stockholders_equity is not None and debt_for_roic is not None and roic_stockholders_equity != 0:
                computed_debt_to_equity = debt_for_roic / roic_stockholders_equity
                if abs(computed_debt_to_equity) > 1000:
                    failed_metrics.append("debt_to_equity")
                    implausible_ratio_metrics.append("debt_to_equity")
                else:
                    metrics["debt_to_equity"] = float(computed_debt_to_equity)
            elif roic_stockholders_equity == 0:
                # A real, literal $0.00 equity (FLOC/INR/WBI) is a division-by-zero case, not
                # missing data - same near-zero-denominator treatment as roic_pct/roce_pct above.
                failed_metrics.append("debt_to_equity")
                implausible_ratio_metrics.append("debt_to_equity")
            else:
                failed_metrics.append("debt_to_equity")

            # FCF to Net Income = Free Cash Flow / Net Income
            # Same >1000 near-zero-denominator bound as debt_to_assets/current_ratio/quick_ratio/
            # debt_to_equity above - a near-zero net_income explodes this ratio the same way a
            # near-zero equity/assets base explodes theirs, and this field was missing the guard
            # every sibling ratio in this function already has.
            if free_cash_flow is not None and net_income is not None and net_income != 0:
                computed_fcf_to_net_income = free_cash_flow / net_income
                if abs(computed_fcf_to_net_income) > 1000:
                    failed_metrics.append("fcf_to_net_income")
                    implausible_ratio_metrics.append("fcf_to_net_income")
                else:
                    metrics["fcf_to_net_income"] = float(computed_fcf_to_net_income)
            else:
                failed_metrics.append("fcf_to_net_income")

            # OCF to Net Income = Operating Cash Flow / Net Income
            # Same >1000 near-zero-denominator bound as fcf_to_net_income above.
            if operating_cash_flow is not None and net_income is not None and net_income != 0:
                computed_ocf_to_net_income = operating_cash_flow / net_income
                if abs(computed_ocf_to_net_income) > 1000:
                    failed_metrics.append("ocf_to_net_income")
                    implausible_ratio_metrics.append("ocf_to_net_income")
                else:
                    metrics["ocf_to_net_income"] = float(computed_ocf_to_net_income)
            else:
                failed_metrics.append("ocf_to_net_income")

            # Payout Ratio = Dividends / Net Income (% of earnings paid out). A loss year
            # (net_income <= 0) makes the ratio not meaningful - "not applicable", not a data
            # gap; distinguish from genuine non-payers (no dividend history at all) and true
            # extraction gaps (dividend history exists elsewhere, concept missing this year).
            # Magnitude-guarded like the other ratio fields: quality_metrics.payout_ratio is
            # NUMERIC(10,2) (max ~1e8) and a near-zero net_income denominator can otherwise
            # explode the ratio and crash the INSERT with NumericValueOutOfRange.
            MAX_PAYOUT_RATIO_ABS_PCT = 1000.0  # noqa: N806
            payout_ratio_reason = None
            if dividends_paid_with_prior_year_fallback is not None and net_income is not None and net_income > 0:
                payout_ratio_pct = (dividends_paid_with_prior_year_fallback / net_income) * 100
                if abs(payout_ratio_pct) <= MAX_PAYOUT_RATIO_ABS_PCT:
                    metrics["payout_ratio"] = float(payout_ratio_pct)
                else:
                    failed_metrics.append("payout_ratio")
                    payout_ratio_reason = "implausible_ratio"
            else:
                failed_metrics.append("payout_ratio")
                if dividends_paid_with_prior_year_fallback is not None and net_income is not None and net_income <= 0:
                    payout_ratio_reason = "unprofitable_stock"
                # Same net_income_not_reported gate net_margin/roa/roe already use - genuinely
                # never-tagged net_income, not just <=0.
                elif net_income is None and (
                    symbol in self._get_no_recent_net_income_symbols()
                    or symbol in self._get_never_tagged_net_income_symbols()
                ):
                    payout_ratio_reason = "net_income_not_reported"
                # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day
                # follow-up to total_debt_unavailable_reason's own etf_symbols check above): an
                # ETF/UIT (SPY/IGV/BKDV live-confirmed) has no "net_income" concept at all - it
                # distributes fund income, it doesn't report corporate earnings - so its real
                # dividend payments (has_real_dividend_history below would otherwise be True)
                # were mislabeled "missing_sec_data" instead of the already-correct
                # etf_trust_no_gaap_financials. Same "etf_symbols membership alone is
                # sufficient" rationale as that total_debt fix - an ETF's absence of a
                # net_income concept doesn't depend on listing age.
                elif symbol in self._get_etf_symbols():
                    payout_ratio_reason = "etf_trust_no_gaap_financials"
                # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): sibling gate
                # to the sustainable_growth_rate/net_margin/roa/roe/ebitda_margin reason chains
                # elsewhere in this file (see _get_net_income_available_elsewhere_symbols()'s
                # docstring) - net_income is None here because the anchor fiscal year's own
                # income-statement row is unavailable, not because the symbol lacks real
                # net_income data. This chain fell straight through to the generic
                # has_real_dividend_history check below instead, mislabeling every affected
                # dividend payer "missing_sec_data" (Missing SEC/XBRL data) instead of the more
                # precise, already-established "net_income_absent_from_anchor_year" label.
                elif net_income is None and symbol in self._get_net_income_available_elsewhere_symbols():
                    payout_ratio_reason = "net_income_absent_from_anchor_year"
                else:
                    # Same "ever, not recently" distinction as dividend_yield_reason above - a
                    # symbol that discontinued its dividend years ago has real history on file
                    # but isn't a current data gap. Same 2-year recency window used there.
                    with _owner().DatabaseContext("read") as cur:
                        cur.execute(
                            """
                            SELECT 1 FROM dividend_data
                            WHERE symbol = %s AND data_unavailable = FALSE
                              AND ex_dividend_date > CURRENT_DATE - INTERVAL '2 years'
                            LIMIT 1
                            """,
                            (symbol,),
                        )
                        has_real_dividend_history = cur.fetchone() is not None
                    payout_ratio_reason = (
                        "missing_sec_data" if has_real_dividend_history else "non_dividend_paying_stock"
                    )

            # Absolute cash flow values
            #
            # FIXED 2026-09-05 (goal session: "implausible values"/missing-XBRL sweep):
            # unlike fcf_margin/fcf_to_net_income, this field isn't a ratio requiring same-year
            # pairing with anything else - it's a standalone dollar figure, so an older real
            # value is a straightforward, safe substitution (same reasoning as the roic_pct/
            # roce_pct cross-year fallback) rather than the local-variable-only, label-only
            # treatment fcf_margin/fcf_to_net_income need to preserve their anchor-year
            # alignment (see the fcf_margin fallback's own comment above for why those stay
            # separate). Deliberately a fresh query, not a reuse of
            # `_get_free_cash_flow_available_elsewhere_symbols()` (that gate only proves
            # membership for labeling, not the actual value).
            standalone_free_cash_flow = free_cash_flow
            if standalone_free_cash_flow is None:
                # Same two-tier recency window as the fcf_margin fallback above (recent 3 fiscal
                # years preferred, only reaching further back if nothing qualifies there) - keeps
                # this from resurrecting a decade-stale figure for a symbol that's simply been
                # `_get_no_recent_free_cash_flow_symbols()`-flagged for years.
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT free_cash_flow FROM annual_cash_flow
                        WHERE symbol = %s AND free_cash_flow IS NOT NULL AND data_unavailable = FALSE
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol,),
                    )
                    fallback_row = cur.fetchone()
                    if not fallback_row:
                        cur.execute(
                            """
                            SELECT free_cash_flow FROM annual_cash_flow
                            WHERE symbol = %s AND free_cash_flow IS NOT NULL AND data_unavailable = FALSE
                            ORDER BY fiscal_year DESC LIMIT 1
                            """,
                            (symbol,),
                        )
                        fallback_row = cur.fetchone()
                if fallback_row:
                    standalone_free_cash_flow = self._nan_to_none(
                        safe_float(fallback_row[0], f"{symbol}.free_cash_flow_fallback_year", allow_none=True)
                    )
            if standalone_free_cash_flow is not None and abs(standalone_free_cash_flow) < MAX_ABSOLUTE_DOLLAR_VALUE:
                metrics["free_cash_flow"] = float(standalone_free_cash_flow)
            else:
                failed_metrics.append("free_cash_flow")

            # FIXED 2026-09-05 (same fix as standalone_free_cash_flow above): operating_cash_flow
            # is also a standalone dollar figure with no same-year pairing requirement of its
            # own - ocf_to_net_income/accruals_ratio/the YoY growth check above DO need the
            # anchor-year-aligned global `operating_cash_flow`, so this fallback is scoped to a
            # separate local variable exactly like standalone_free_cash_flow.
            standalone_operating_cash_flow = operating_cash_flow
            if standalone_operating_cash_flow is None:
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT operating_cash_flow FROM annual_cash_flow
                        WHERE symbol = %s AND operating_cash_flow IS NOT NULL AND data_unavailable = FALSE
                          AND fiscal_year >= EXTRACT(YEAR FROM CURRENT_DATE)::int - 3
                        ORDER BY fiscal_year DESC LIMIT 1
                        """,
                        (symbol,),
                    )
                    fallback_row = cur.fetchone()
                    if not fallback_row:
                        cur.execute(
                            """
                            SELECT operating_cash_flow FROM annual_cash_flow
                            WHERE symbol = %s AND operating_cash_flow IS NOT NULL AND data_unavailable = FALSE
                            ORDER BY fiscal_year DESC LIMIT 1
                            """,
                            (symbol,),
                        )
                        fallback_row = cur.fetchone()
                if fallback_row:
                    standalone_operating_cash_flow = self._nan_to_none(
                        safe_float(fallback_row[0], f"{symbol}.operating_cash_flow_fallback_year", allow_none=True)
                    )
            if (
                standalone_operating_cash_flow is not None
                and abs(standalone_operating_cash_flow) < MAX_ABSOLUTE_DOLLAR_VALUE
            ):
                metrics["operating_cash_flow"] = float(standalone_operating_cash_flow)
            else:
                failed_metrics.append("operating_cash_flow")

            # Absolute balance sheet values from sec_valuations
            if total_debt_ev is not None and abs(total_debt_ev) < MAX_ABSOLUTE_DOLLAR_VALUE:
                metrics["total_debt"] = float(total_debt_ev)
            elif (
                symbol in self._get_never_tagged_debt_components_symbols()
                and symbol in self._get_never_tagged_interest_expense_symbols()
            ):
                # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): debt_for_roic
                # just below already coerces to 0.0 for this exact double-confirmed-debt-free
                # population (see its own comment) so debt_to_equity/roic_pct/roce_pct compute
                # real values - but the raw total_debt metric itself was never given the same
                # treatment, so it stayed "total_debt_not_itemized" (Missing SEC/XBRL data) even
                # for a symbol whose absence of debt is confirmed, not unknown. A confirmed zero
                # is a real value, not missing data - same "genuinely absent, not missing"
                # philosophy already applied to capex for this population's siblings.
                metrics["total_debt"] = 0.0
            else:
                failed_metrics.append("total_debt")

            if total_cash_ev is not None and abs(total_cash_ev) < MAX_ABSOLUTE_DOLLAR_VALUE:
                metrics["total_cash"] = float(total_cash_ev)
            else:
                failed_metrics.append("total_cash")

            if ebitda_ev is not None and abs(ebitda_ev) < MAX_ABSOLUTE_DOLLAR_VALUE:
                metrics["ebitda"] = float(ebitda_ev)
            else:
                failed_metrics.append("ebitda")

            # Cash per Share = Total Cash / Shares Outstanding
            cash_per_share_shares_missing = False
            if total_cash_ev is not None and shares_outstanding is not None and shares_outstanding > 0:
                metrics["cash_per_share"] = float(total_cash_ev / shares_outstanding)
            else:
                failed_metrics.append("cash_per_share")
                # shares_outstanding here is sv.shares_outstanding (quality_row[11]) - same
                # column that already gets its own "shares_outstanding_unavailable" reason
                # elsewhere in this codebase, not a generic SEC extraction gap.
                cash_per_share_shares_missing = shares_outstanding is None or shares_outstanding <= 0

            # Earnings Growth YoY = (Current EPS - Prior Year EPS) / Prior Year EPS * 100.
            # Bounded like the sibling *_growth_yoy fields below: a near-zero prior-year base
            # can overflow NUMERIC(10,2) and crash the whole row's INSERT. Appends to
            # implausible_ratio_metrics (in addition to failed_metrics) so a real-but-rejected
            # ratio is distinguished from a genuinely absent prior-year base.
            if earnings_per_share is not None and prior_year_eps is not None and prior_year_eps != 0:
                try:
                    yoy_growth = ((earnings_per_share - prior_year_eps) / abs(prior_year_eps)) * 100
                    if abs(yoy_growth) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["earnings_growth_yoy"] = float(round(yoy_growth, 2))
                    else:
                        failed_metrics.append("earnings_growth_yoy")
                        implausible_ratio_metrics.append("earnings_growth_yoy")
                except (ValueError, TypeError):
                    failed_metrics.append("earnings_growth_yoy")
            else:
                failed_metrics.append("earnings_growth_yoy")

            # Revenue Growth YoY = (Current Revenue - Prior Year Revenue) / Prior Year Revenue * 100
            if revenue is not None and prior_year_revenue is not None and prior_year_revenue != 0:
                try:
                    yoy_growth = ((revenue - prior_year_revenue) / abs(prior_year_revenue)) * 100
                    if abs(yoy_growth) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["revenue_growth_yoy"] = float(round(yoy_growth, 2))
                    else:
                        failed_metrics.append("revenue_growth_yoy")
                        implausible_ratio_metrics.append("revenue_growth_yoy")
                except (ValueError, TypeError):
                    failed_metrics.append("revenue_growth_yoy")
            else:
                failed_metrics.append("revenue_growth_yoy")

            # TREND FIELDS (new fields for enhanced scoring)
            # Net Income Growth YoY - only if actual prior net income available.
            # Bounded by MAX_TREND_PERCENTAGE_POINTS (same guard as roe_trend below): a real but
            # near-zero prior-year base can overflow this column's NUMERIC(10,4) and crash the
            # whole row's INSERT.
            if net_income is not None and prior_year_net_income is not None and prior_year_net_income != 0:
                if (net_income > 0 and prior_year_net_income < 0) or (net_income < 0 and prior_year_net_income > 0):
                    # Profit<->loss sign flip - growth % is mathematically undefined here,
                    # same treatment _cagr()/_compute_period_growth already give this exact
                    # condition (root cause of CRWD's -966% net_income_growth_yoy despite
                    # genuinely strong ~22% revenue growth).
                    sign_change_yoy_metrics.append("net_income_growth_yoy")
                elif (
                    prior_year_revenue is not None
                    and prior_year_revenue > 0
                    and abs(prior_year_net_income) < 0.01 * prior_year_revenue
                ):
                    immaterial_base_yoy_metrics.append("net_income_growth_yoy")
                else:
                    try:
                        ni_growth = ((net_income - prior_year_net_income) / abs(prior_year_net_income)) * 100
                        if abs(ni_growth) < MAX_PLAUSIBLE_GROWTH_PCT:
                            metrics["net_income_growth_yoy"] = float(round(ni_growth, 2))
                        else:
                            implausible_ratio_metrics.append("net_income_growth_yoy")
                    except (ValueError, TypeError, ZeroDivisionError) as e:
                        logger.warning(
                            f"[{symbol}] Failed to calculate net_income_growth_yoy: {type(e).__name__}. "
                            f"Metric marked data_unavailable."
                        )

            # Operating Income Growth YoY - uses the same EBIT-approximation fallback as
            # operating_income_for_margin (current year) and prior_year_operating_income_for_trend
            # (prior year) so filers that never tag OperatingIncomeLoss aren't blocked here too.
            if (
                operating_income_for_margin is not None
                and prior_year_operating_income_for_trend is not None
                and prior_year_operating_income_for_trend != 0
            ):
                if (operating_income_for_margin > 0 and prior_year_operating_income_for_trend < 0) or (
                    operating_income_for_margin < 0 and prior_year_operating_income_for_trend > 0
                ):
                    sign_change_yoy_metrics.append("operating_income_growth_yoy")
                elif (
                    prior_year_revenue is not None
                    and prior_year_revenue > 0
                    and abs(prior_year_operating_income_for_trend) < 0.01 * prior_year_revenue
                ):
                    immaterial_base_yoy_metrics.append("operating_income_growth_yoy")
                else:
                    try:
                        oi_growth = (
                            (operating_income_for_margin - prior_year_operating_income_for_trend)
                            / abs(prior_year_operating_income_for_trend)
                        ) * 100
                        if abs(oi_growth) < MAX_TREND_PERCENTAGE_POINTS:
                            metrics["operating_income_growth_yoy"] = float(round(oi_growth, 2))
                        else:
                            implausible_ratio_metrics.append("operating_income_growth_yoy")
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

            # Margin Trends (current - prior year) - only compute when actual prior data available.
            # The trend-level MAX_TREND_PERCENTAGE_POINTS check only bounds the DELTA, not the
            # two margins that produce it - a near-zero-revenue year can put curr/prior
            # individually in the tens of thousands of percent while their difference still
            # lands under threshold. Bound each side of the subtraction first (same |ratio| <=
            # 1000 bound as the base margin fields) - a trend from two implausible margins is
            # itself meaningless.
            MAX_MARGIN_ABS_PCT = 1000.0  # noqa: N806
            if revenue is not None and prior_year_revenue is not None and revenue > 0 and prior_year_revenue > 0:
                # Gross Margin Trend - prefers each year's directly-reported gross_profit (same
                # source the base gross_margin metric above falls back to), only deriving from
                # revenue - cost_of_revenue when a filer doesn't tag GrossProfit at all (some
                # filers report GrossProfit but never a separate CostOfRevenue concept).
                curr_gross_profit = (
                    gross_profit_direct
                    if gross_profit_direct is not None
                    else (revenue - cost_of_revenue if cost_of_revenue is not None else None)
                )
                prior_gross_profit = (
                    prior_year_gross_profit
                    if prior_year_gross_profit is not None
                    else (
                        prior_year_revenue - prior_year_cost_of_revenue
                        if prior_year_cost_of_revenue is not None
                        else None
                    )
                )
                if curr_gross_profit is not None and prior_gross_profit is not None:
                    # Prefer the base gross_margin metric's own value when already computed
                    # above - it may already reflect that field's cross-year implausible-ratio
                    # fallback (a genuine extraction artifact this fiscal year, e.g. near-zero
                    # revenue, rescued from a different coherent year), so reusing it here
                    # avoids re-deriving the SAME raw (and possibly implausible) ratio inline.
                    curr_gm = metrics.get("gross_margin")
                    if curr_gm is None:
                        curr_gm = (curr_gross_profit / revenue) * 100 if revenue > 0 else None
                    prior_gm = (prior_gross_profit / prior_year_revenue) * 100 if prior_year_revenue > 0 else None
                    if (
                        curr_gm is not None
                        and prior_gm is not None
                        and abs(curr_gm) <= MAX_MARGIN_ABS_PCT
                        and abs(prior_gm) <= MAX_MARGIN_ABS_PCT
                    ):
                        try:
                            gm_trend = round(curr_gm - prior_gm, 2)
                            if abs(gm_trend) < MAX_TREND_PERCENTAGE_POINTS:
                                metrics["gross_margin_trend"] = float(gm_trend)
                            else:
                                implausible_ratio_metrics.append("gross_margin_trend")
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass
                    elif curr_gm is not None and prior_gm is not None:
                        # Inputs existed but one/both margins blew past MAX_MARGIN_ABS_PCT
                        # (e.g. cost_of_revenue exceeding revenue) - a real, if garbage,
                        # ratio that was deliberately excluded, not a missing-data gap.
                        implausible_ratio_metrics.append("gross_margin_trend")

                # Operating Margin Trend - uses the same EBIT-approximation fallback as
                # operating_income_growth_yoy above (see prior_year_operating_income_for_trend).
                if (
                    operating_income_for_margin is not None
                    and prior_year_operating_income_for_trend is not None
                    and prior_year_revenue > 0
                ):
                    # Prefer the base operating_margin metric's own value when already
                    # computed above - see gross_margin_trend's comment on why.
                    curr_om = metrics.get("operating_margin")
                    if curr_om is None:
                        curr_om = (operating_income_for_margin / revenue) * 100
                    prior_om = (prior_year_operating_income_for_trend / prior_year_revenue) * 100
                    if abs(curr_om) <= MAX_MARGIN_ABS_PCT and abs(prior_om) <= MAX_MARGIN_ABS_PCT:
                        try:
                            om_trend = round(curr_om - prior_om, 2)
                            if abs(om_trend) < MAX_TREND_PERCENTAGE_POINTS:
                                metrics["operating_margin_trend"] = float(om_trend)
                            else:
                                implausible_ratio_metrics.append("operating_margin_trend")
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass
                    else:
                        implausible_ratio_metrics.append("operating_margin_trend")

                # Net Margin Trend - only if actual prior net income available
                if net_income is not None and prior_year_net_income is not None and prior_year_revenue > 0:
                    # Prefer the base net_margin metric's own value when already computed
                    # above - see gross_margin_trend's comment on why.
                    curr_nm = metrics.get("net_margin")
                    if curr_nm is None:
                        curr_nm = (net_income / revenue) * 100
                    prior_nm = (prior_year_net_income / prior_year_revenue) * 100
                    if abs(curr_nm) <= MAX_MARGIN_ABS_PCT and abs(prior_nm) <= MAX_MARGIN_ABS_PCT:
                        try:
                            nm_trend = round(curr_nm - prior_nm, 2)
                            if abs(nm_trend) < MAX_TREND_PERCENTAGE_POINTS:
                                metrics["net_margin_trend"] = float(nm_trend)
                            else:
                                implausible_ratio_metrics.append("net_margin_trend")
                        except (ValueError, TypeError, ZeroDivisionError):
                            pass
                    else:
                        implausible_ratio_metrics.append("net_margin_trend")

            # Sustainable Growth Rate = ROE * Retention Ratio - only with real data
            # dividends_paid is None (not 0) for genuine non-dividend-payers, since SEC XBRL
            # simply omits the PaymentsOfDividends concept when nothing was paid - same
            # "confirmed non-payer vs missing data" ambiguity as dividend_yield/payout_ratio
            # above. Confirmed non-payers still compute (retention_ratio = 1.0).
            sgr_reason = None
            # Same prior-year fallback as payout_ratio above, so a confirmed-recent payer's
            # current-year extraction gap doesn't get stuck on "missing_sec_data".
            sgr_dividends_paid = dividends_paid_with_prior_year_fallback
            if (
                sgr_dividends_paid is None
                and stockholders_equity is not None
                and net_income is not None
                and stockholders_equity > 0
            ):
                # Same "ever, not recently" distinction as dividend_yield_reason/
                # payout_ratio_reason above; same 2-year recency window.
                with _owner().DatabaseContext("read") as cur:
                    cur.execute(
                        """
                        SELECT 1 FROM dividend_data
                        WHERE symbol = %s AND data_unavailable = FALSE
                          AND ex_dividend_date > CURRENT_DATE - INTERVAL '2 years'
                        LIMIT 1
                        """,
                        (symbol,),
                    )
                    has_real_dividend_history = cur.fetchone() is not None
                if has_real_dividend_history:
                    # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" audit):
                    # annual_cash_flow.dividends_paid is unpopulated for many real payers
                    # (live-confirmed SPG/RS/CNK - see value_metrics.dividend_yield's own TIER 4
                    # fallback docstring, same root cause) - this used to give up entirely and
                    # blame "missing_sec_data" the instant has_real_dividend_history confirmed a
                    # real payer, never trying the same dividend_data.dividend_per_share TTM
                    # recovery TIER 4 already uses. Mirrors that fallback exactly: trailing
                    # ~370-day per-share sum x shares_outstanding = a real, if approximate,
                    # dollar dividends_paid figure - same recency window, same "a confirmed real
                    # payer deserves a real attempt before falling back to the generic label"
                    # reasoning.
                    _sgr_ttm_attempted = False
                    if shares_outstanding is not None and shares_outstanding > 0:
                        _sgr_ttm_attempted = True
                        with _owner().DatabaseContext("read") as cur:
                            cur.execute(
                                """
                                SELECT SUM(dividend_per_share) FROM dividend_data
                                WHERE symbol = %s AND data_unavailable = FALSE
                                  AND dividend_per_share IS NOT NULL
                                  AND ex_dividend_date > CURRENT_DATE - INTERVAL '370 days'
                                """,
                                (symbol,),
                            )
                            ttm_row = cur.fetchone()
                            ttm_dividend_per_share = ttm_row[0] if ttm_row else None
                        if ttm_dividend_per_share is not None and ttm_dividend_per_share > 0:
                            sgr_dividends_paid = float(ttm_dividend_per_share) * shares_outstanding
                    if sgr_dividends_paid is None and _sgr_ttm_attempted:
                        # FIXED 2026-09-05 (goal session: "SEC/XBRL missing data to zero"
                        # follow-up, same fix as value_metrics.dividend_yield's identical gap):
                        # a real payment inside the 2-year has_real_dividend_history window but
                        # outside the 370-day TTM window just used is genuine recent data, too
                        # stale to compute a confident current dividends_paid figure from - a
                        # real fact, not a missing SEC concept, same "Legitimate / not
                        # applicable" class as a confirmed non-payer.
                        sgr_reason = "dividend_lapsed_beyond_ttm_window"
                    elif sgr_dividends_paid is None:
                        # FIXED 2026-09-09 (goal session: "missing SEC/XBRL data under 500"
                        # sweep): the TTM attempt above never even ran when shares_outstanding
                        # is None, and this used to blame the generic "missing_sec_data" for
                        # that case unconditionally - live-confirmed TX (Ternium S.A.)/CYD
                        # (China Yuchai)/AUXX/FGL/GAUZ/GIXI/INCR: all confirmed real, current
                        # dividend payers (has_real_dividend_history True) with real, positive
                        # net_income and stockholders_equity, whose shares_outstanding is None
                        # not because SEC/XBRL data is missing but because
                        # company_info_sec.shares_outstanding_unavailable_reason is
                        # "fpi_shares_excluded_domestic_only" - a DELIBERATE exclusion (see
                        # sec_statements_entry_resolution.py's dei-facts-domestic-only guard)
                        # to avoid a foreign filer's local-share/ADS-ratio unit mismatch, not a
                        # genuine extraction gap. Reuse the real, already-correctly-categorized
                        # ("Legitimate / not applicable") reason recorded on company_info_sec
                        # for this exact fact when that's the actual cause, instead of
                        # mislabeling a known, deliberate design constraint as a missing-data
                        # bug. Falls back to the pre-existing "missing_sec_data" label for every
                        # other real "shares_outstanding is genuinely unknown" case (e.g.
                        # cik_not_found), which this was never meant to touch.
                        #
                        # EXTENDED 2026-09-11 (goal: "under 300" push): live-confirmed CVKD
                        # (Cadrenal Therapeutics)/HCWB (HCW Biologics) reach this exact branch -
                        # real dividend history, real net_income/stockholders_equity - but
                        # shares_outstanding is None here NOT because it was never tagged, but
                        # because load_value_quality_growth_metrics.py's own query already
                        # excludes it (`WHERE reason IS NULL OR reason !=
                        # 'shares_outstanding_scale_mismatch'`, added for the PMI/SELX/AGH/AKTX/
                        # UHAL sustainable_growth_rate corruption bug) whenever sec_valuations
                        # has flagged this exact symbol's shares_outstanding as scale-mismatched
                        # (CVKD: company_info_sec says 3,567,592 vs sec_valuations says
                        # 1,993,757). That upstream exclusion is correct and load-bearing - don't
                        # touch it - but it left this function unable to tell "shares_outstanding
                        # was never tagged" apart from "shares_outstanding exists but is
                        # untrustworthy", so both fell through to the same generic
                        # "missing_sec_data" label. Check sec_valuations directly (not just
                        # company_info_sec) so a known-inconsistent share count gets the correct,
                        # already-established "shares_outstanding_scale_mismatch" reason instead.
                        _sgr_shares_reason: str | None = None
                        with _owner().DatabaseContext("read") as cur:
                            cur.execute(
                                "SELECT shares_outstanding_unavailable_reason FROM company_info_sec WHERE symbol = %s",
                                (symbol,),
                            )
                            _sgr_shares_row = cur.fetchone()
                            _sgr_shares_reason = _sgr_shares_row[0] if _sgr_shares_row else None
                        if _sgr_shares_reason == "fpi_shares_excluded_domestic_only":
                            sgr_reason = _sgr_shares_reason
                        else:
                            with _owner().DatabaseContext("read") as cur:
                                cur.execute(
                                    "SELECT reason FROM sec_valuations WHERE symbol = %s",
                                    (symbol,),
                                )
                                _sgr_sv_row = cur.fetchone()
                            sgr_reason = (
                                "shares_outstanding_scale_mismatch"
                                if _sgr_sv_row is not None and _sgr_sv_row[0] == "shares_outstanding_scale_mismatch"
                                else "missing_sec_data"
                            )
                else:
                    sgr_dividends_paid = 0.0

            if stockholders_equity is not None and net_income is not None and stockholders_equity > 0:
                if sgr_dividends_paid is not None and net_income != 0:
                    # Actual retention ratio = (earnings - dividends) / earnings
                    roe_pct = net_income / stockholders_equity
                    retention_ratio = 1.0 - (sgr_dividends_paid / abs(net_income)) if net_income != 0 else 0.0
                    try:
                        sgr = round(roe_pct * retention_ratio * 100, 2)
                        # Bounded by MAX_PLAUSIBLE_GROWTH_PCT - a near-zero stockholders_equity
                        # base blows up roe_pct the same way a near-zero prior-year base blows
                        # up other ratios.
                        if abs(sgr) < MAX_PLAUSIBLE_GROWTH_PCT:
                            metrics["sustainable_growth_rate"] = float(sgr)
                        elif sgr_reason is None:
                            # Real value, deliberately rejected as implausible - not a missing
                            # SEC concept.
                            sgr_reason = "implausible_ratio"
                            implausible_ratio_metrics.append("sustainable_growth_rate")
                    except (ValueError, TypeError, ZeroDivisionError):
                        if sgr_reason is None:
                            sgr_reason = "missing_sec_data"
                elif sgr_reason is None:
                    sgr_reason = "missing_sec_data"
            elif sgr_reason is None:
                # stockholders_equity <= 0 (debt-funded buybacks/distributions, e.g.
                # YUM/IRM/COKE) is real data, not missing - SGR's "growth financeable from
                # retained earnings relative to the equity base" doesn't translate to a negative
                # base, so this deliberately still doesn't compute a value, but the label must
                # say why. Reuses "negative_book_value" (same as pb_ratio above) rather than
                # inventing a new string.
                if stockholders_equity is not None and stockholders_equity <= 0:
                    sgr_reason = "negative_book_value"
                # Remaining case: stockholders_equity is None, or (rarely) present but
                # net_income is None - reuse the same gates roe/roa/debt_to_equity use above.
                elif stockholders_equity is None and (
                    symbol in self._get_no_recent_stockholders_equity_symbols()
                    or symbol in self._get_never_tagged_stockholders_equity_symbols()
                ):
                    sgr_reason = "stockholders_equity_not_reported"
                elif net_income is None and (
                    symbol in self._get_no_recent_net_income_symbols()
                    or symbol in self._get_never_tagged_net_income_symbols()
                ):
                    sgr_reason = "net_income_not_reported"
                # quality_row_db's current-year income-statement columns require an EXACT
                # fiscal_year match to the balance-sheet anchor row (~line 716) - a
                # still-in-progress income statement for that year can leave net_income None
                # here even when real data exists 1-2 years back. Deliberately does NOT
                # recompute from the mismatched-year net_income (same discipline as
                # revenue_absent_from_anchor_year/implausible_dcf_result elsewhere) - label-only,
                # to distinguish "SEC data isn't there" from "SEC data is there, wrong year".
                elif net_income is None and symbol in self._get_net_income_available_elsewhere_symbols():
                    sgr_reason = "net_income_absent_from_anchor_year"
                else:
                    sgr_reason = "missing_sec_data"

            # ROE Trend = Current ROE - Prior ROE. Same per-side MAX_MARGIN_ABS_PCT bound as
            # the margin trends above - a near-zero prior-year equity base must be caught before
            # the subtraction, not just via the looser trend-level check on the delta. Uses
            # `!= 0` (not `> 0`) to match the base roe field - negative equity (debt-funded
            # buybacks/distributions, e.g. YUM/IRM/COKE) is real data, and MAX_MARGIN_ABS_PCT
            # already rejects genuine near-zero-equity garbage.
            if (
                stockholders_equity is not None
                and net_income is not None
                and stockholders_equity != 0
                and prior_year_stockholders_equity is not None
                and prior_year_net_income is not None
                and prior_year_stockholders_equity != 0
            ):
                # Prefer the base roe metric's own value when already computed above - it may
                # already reflect roe's own cross-year implausible-ratio fallback (see
                # gross_margin_trend's comment on why reusing it here is safe).
                curr_roe = metrics.get("roe")
                if curr_roe is None:
                    curr_roe = (net_income / stockholders_equity) * 100
                prior_roe = (prior_year_net_income / prior_year_stockholders_equity) * 100
                if abs(curr_roe) <= MAX_MARGIN_ABS_PCT and abs(prior_roe) <= MAX_MARGIN_ABS_PCT:
                    try:
                        roe_trend = round(curr_roe - prior_roe, 2)
                        if abs(roe_trend) < MAX_TREND_PERCENTAGE_POINTS:
                            metrics["roe_trend"] = float(roe_trend)
                        else:
                            implausible_ratio_metrics.append("roe_trend")
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass
                else:
                    implausible_ratio_metrics.append("roe_trend")

            # FCF Growth YoY - only if actual prior FCF available
            # Same MAX_TREND_PERCENTAGE_POINTS overflow guard as net_income_growth_yoy above -
            # these three share the identical NUMERIC(10,4) column and tiny-prior-year-base risk.
            if free_cash_flow is not None and prior_year_free_cash_flow is not None and prior_year_free_cash_flow != 0:
                if (free_cash_flow > 0 and prior_year_free_cash_flow < 0) or (
                    free_cash_flow < 0 and prior_year_free_cash_flow > 0
                ):
                    sign_change_yoy_metrics.append("fcf_growth_yoy")
                elif (
                    prior_year_revenue is not None
                    and prior_year_revenue > 0
                    and abs(prior_year_free_cash_flow) < 0.01 * prior_year_revenue
                ):
                    immaterial_base_yoy_metrics.append("fcf_growth_yoy")
                else:
                    try:
                        fcf_growth = (
                            (free_cash_flow - prior_year_free_cash_flow) / abs(prior_year_free_cash_flow)
                        ) * 100
                        if abs(fcf_growth) < MAX_PLAUSIBLE_GROWTH_PCT:
                            metrics["fcf_growth_yoy"] = float(round(fcf_growth, 2))
                        else:
                            implausible_ratio_metrics.append("fcf_growth_yoy")
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

            # OCF Growth YoY - only if actual prior OCF available
            if (
                operating_cash_flow is not None
                and prior_year_operating_cash_flow is not None
                and prior_year_operating_cash_flow != 0
            ):
                if (operating_cash_flow > 0 and prior_year_operating_cash_flow < 0) or (
                    operating_cash_flow < 0 and prior_year_operating_cash_flow > 0
                ):
                    sign_change_yoy_metrics.append("ocf_growth_yoy")
                elif (
                    prior_year_revenue is not None
                    and prior_year_revenue > 0
                    and abs(prior_year_operating_cash_flow) < 0.01 * prior_year_revenue
                ):
                    immaterial_base_yoy_metrics.append("ocf_growth_yoy")
                else:
                    try:
                        ocf_growth = (
                            (operating_cash_flow - prior_year_operating_cash_flow) / abs(prior_year_operating_cash_flow)
                        ) * 100
                        if abs(ocf_growth) < MAX_TREND_PERCENTAGE_POINTS:
                            metrics["ocf_growth_yoy"] = float(round(ocf_growth, 2))
                        else:
                            implausible_ratio_metrics.append("ocf_growth_yoy")
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

            # Asset Growth YoY - now can compute with prior-year total assets
            if total_assets is not None and prior_year_total_assets is not None and prior_year_total_assets != 0:
                try:
                    asset_growth = ((total_assets - prior_year_total_assets) / abs(prior_year_total_assets)) * 100
                    if abs(asset_growth) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["asset_growth_yoy"] = float(round(asset_growth, 2))
                    else:
                        implausible_ratio_metrics.append("asset_growth_yoy")
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

            # Record WHY each of these 9 trend/growth fields stayed None (mirrored into
            # growth_metrics via the _SHARED_TREND_FIELDS copy below). Order matters: check the
            # structural gross_profit gap and implausible-ratio rejection before falling through
            # to the generic "insufficient_prior_year_data" - both are legitimate-gap or
            # garbage-data cases, not evidence of a loader fetch failure.
            for _trend_field in (
                "net_income_growth_yoy",
                "operating_income_growth_yoy",
                "gross_margin_trend",
                "operating_margin_trend",
                "net_margin_trend",
                "roe_trend",
                "fcf_growth_yoy",
                "ocf_growth_yoy",
                "asset_growth_yoy",
            ):
                if metrics.get(_trend_field) is None:
                    if _trend_field == "gross_margin_trend" and no_gross_profit_concept:
                        metrics[f"{_trend_field}_unavailable_reason"] = "reit_special_entity"
                    elif _trend_field in sign_change_yoy_metrics:
                        metrics[f"{_trend_field}_unavailable_reason"] = "growth_undefined_sign_change"
                    elif _trend_field in immaterial_base_yoy_metrics:
                        metrics[f"{_trend_field}_unavailable_reason"] = "immaterial_prior_year_base"
                    elif _trend_field in implausible_ratio_metrics:
                        metrics[f"{_trend_field}_unavailable_reason"] = "implausible_ratio"
                    else:
                        metrics[f"{_trend_field}_unavailable_reason"] = "insufficient_prior_year_data"

            # Quarterly Metrics (Session 74+)
            quarterly_metrics = self._compute_quarterly_metrics(symbol)
            metrics.update(quarterly_metrics)

            # Initialize missing trend fields as None
            for field in [
                "net_income_growth_yoy",
                "operating_income_growth_yoy",
                "gross_margin_trend",
                "operating_margin_trend",
                "net_margin_trend",
                "roe_trend",
                "sustainable_growth_rate",
                "quarterly_growth_momentum",
                "fcf_growth_yoy",
                "ocf_growth_yoy",
                "asset_growth_yoy",
                "earnings_surprise_avg",
                "eps_growth_stability",
                "earnings_beat_rate",
                "consecutive_positive_quarters",
                "estimate_revision_direction",
                "revision_activity_30d",
                "estimate_momentum_60d",
                "estimate_momentum_90d",
                "revision_trend_score",
                "earnings_growth_4q_avg",
            ]:
                if field not in metrics:
                    metrics[field] = None

            # sustainable_growth_rate uses NO prior-year data (see its own computation above),
            # so it gets its own explicit sgr_reason rather than the blanket trend-field loop.
            if metrics.get("sustainable_growth_rate") is None:
                metrics["sustainable_growth_rate_unavailable_reason"] = sgr_reason or "missing_sec_data"

            # Quarterly-derived fields (consecutive_positive_quarters, quarterly_growth_momentum,
            # earnings_growth_4q_avg, eps_growth_stability, earnings_surprise_avg,
            # earnings_beat_rate) are merged in from _compute_quarterly_metrics() above, which
            # sets its own specific reason when the value is None. The generic
            # "insufficient_quarterly_data"/"no_analyst_estimates" fallback for these fields
            # lives further below and only fires if that specific reason wasn't already set.

            # Mark unavailable if all metrics are None
            if (
                all(
                    metrics[k] is None
                    for k in [
                        "roe",
                        "roa",
                        "operating_margin",
                        "net_margin",
                        "debt_to_equity",
                        "debt_to_assets",
                        "current_ratio",
                    ]
                )
                and metrics.get("consecutive_positive_quarters") is None
            ):
                # consecutive_positive_quarters is always a real int (never None) whenever >=4
                # real quarters exist, so checking it here is a direct signal that real
                # quarterly data exists - guards against this early return's blanket
                # None+"missing_sec_data" stamp wiping already-computed quarterly-derived
                # fields. row_level_reason logic extracted to vqg_shared.py's
                # compute_quality_row_level_reason() 2026-09-09 (file-size ratchet).
                row_level_reason = compute_quality_row_level_reason(
                    symbol,
                    stockholders_equity,
                    total_assets,
                    self._get_etf_trust_no_stockholders_equity_symbols(),
                    self._get_unsupported_currency_balance_sheet_symbols(),
                    self._get_no_recent_stockholders_equity_symbols(),
                    self._get_never_tagged_stockholders_equity_symbols(),
                    self._get_no_recent_total_assets_symbols(),
                    self._get_never_tagged_total_assets_symbols(),
                    self._get_reit_or_special_entity_no_balance_data_symbols(),
                )
                marker = self._unavailable_marker("quality_metrics", symbol, reason=row_level_reason)
                # FIXED 2026-09-09: preserve _QUARTERLY_DERIVED_TREND_FIELDS' own reason
                # (e.g. "foreign_private_issuer_no_quarterly_filings") instead of letting
                # _unavailable_marker overwrite it with the unrelated row_level_reason above -
                # see compute_quality_row_level_reason()'s docstring.
                for _qfield in _QUARTERLY_DERIVED_TREND_FIELDS:
                    _qreason_field = f"{_qfield}_unavailable_reason"
                    if metrics.get(_qreason_field):
                        marker[_qreason_field] = metrics[_qreason_field]
                return marker

            _qs = self._compute_quality_composite_score(
                symbol,
                metrics,
                stockholders_equity,
                total_assets,
                operating_income_for_margin,
                interest_expense,
                gross_profit_used,
                net_income,
                operating_cash_flow,
                revenue,
                free_cash_flow,
                margin_volatility,
                failed_metrics,
                implausible_ratio_metrics,
            )
            gross_profitability = _qs["gross_profitability"]
            operating_profitability = _qs["operating_profitability"]
            operating_profitability_negative_equity = _qs["operating_profitability_negative_equity"]
            accruals_ratio = _qs["accruals_ratio"]
            fcf_margin = _qs["fcf_margin"]
            asset_turnover = _qs["asset_turnover"]
            weighted_score = _qs["weighted_score"]
            available_quality_weight = _qs["available_quality_weight"]
            min_quality_weight_pct = _qs["min_quality_weight_pct"]

            self._apply_quality_profitability_reasons(
                metrics=metrics,
                symbol=symbol,
                failed_metrics=failed_metrics,
                implausible_ratio_metrics=implausible_ratio_metrics,
                gross_profitability=gross_profitability,
                operating_profitability=operating_profitability,
                accruals_ratio=accruals_ratio,
                margin_volatility=margin_volatility,
                fcf_margin=fcf_margin,
                asset_turnover=asset_turnover,
                no_gross_profit_concept=no_gross_profit_concept,
                no_operating_income_concept=no_operating_income_concept,
                operating_profitability_negative_equity=operating_profitability_negative_equity,
                operating_income_for_margin=operating_income_for_margin,
                stockholders_equity=stockholders_equity,
                total_assets=total_assets,
                unclassified_balance_sheet=unclassified_balance_sheet,
                current_assets=current_assets,
                current_liabilities=current_liabilities,
                no_recent_interest_expense=no_recent_interest_expense,
                no_operating_income_concept_ic=no_operating_income_concept_ic,
                interest_coverage_operating_income=interest_coverage_operating_income,
                debt_for_roic=debt_for_roic,
                net_income=net_income,
                revenue=revenue,
                operating_cash_flow=operating_cash_flow,
                weighted_score=weighted_score,
            )
            self._apply_quality_valuation_reasons(
                metrics=metrics,
                symbol=symbol,
                ev_metrics=ev_metrics,
                sec_valuations_reason=sec_valuations_reason,
                failed_metrics=failed_metrics,
                implausible_ratio_metrics=implausible_ratio_metrics,
                payout_ratio_reason=payout_ratio_reason,
                no_gross_profit_concept=no_gross_profit_concept,
                no_operating_income_concept=no_operating_income_concept,
                operating_income_for_margin=operating_income_for_margin,
                stockholders_equity=stockholders_equity,
                total_assets=total_assets,
                total_liabilities=total_liabilities,
                cash_per_share_shares_missing=cash_per_share_shares_missing,
                roic_pct_unprofitable=roic_pct_unprofitable,
                roic_pct_negative_invested_capital=roic_pct_negative_invested_capital,
                no_operating_income_concept_roic=no_operating_income_concept_roic,
                debt_for_roic=debt_for_roic,
                roce_pct_negative_capital_employed=roce_pct_negative_capital_employed,
                net_income=net_income,
                revenue=revenue,
                free_cash_flow=free_cash_flow,
                operating_cash_flow=operating_cash_flow,
                weighted_score=weighted_score,
                available_quality_weight=available_quality_weight,
                min_quality_weight_pct=min_quality_weight_pct,
            )

            self._apply_quality_recategorize_reasons_pre(metrics, symbol)
            # FIXED 2026-09-11 (goal: "under 300" push, total_debt_not_itemized re-investigation):
            # a confirmed FDIC-designee bank (RCBC et al. - see is_known_non_sec_filer_bank's
            # module comment) has no SEC CIK at all, so its upstream annual/quarterly_balance_sheet
            # row is already correctly marked data_unavailable_reason='fdic_designee_no_sec_cik'
            # (load_financial_statements.py) - but that specific, already-correct reason never
            # reached quality_metrics: _apply_structural_entity_type_exemption_reasons below only
            # recognizes the ETF/CEF/BDC entity_type/sic_code shape, not this bank population (real
            # operating banks, not sic_code=0), so total_debt/roce_pct/debt_to_equity/etc for RCBC
            # fell through to the generic "total_debt_not_itemized" ("Missing SEC/XBRL data")
            # instead of the same "Legitimate / not applicable" bucket company_info_sec/
            # dividend_data/current_reports_8k already use for this exact population. Applied
            # BEFORE the entity-type gate below (same "narrower reason wins" ordering as that
            # method's own docstring) since a confirmed no-SEC-CIK bank is a more specific fact
            # than the generic entity-type exemption.
            if is_known_non_sec_filer_bank(symbol):
                for field in self._STRUCTURAL_ENTITY_EXEMPT_FIELDS:
                    reason_key = f"{field}_unavailable_reason"
                    if (
                        metrics.get(field) is None
                        and metrics.get(reason_key) in self._STRUCTURAL_ENTITY_EXEMPT_SOURCE_REASONS
                    ):
                        metrics[reason_key] = "fdic_designee_no_sec_cik"
            self._apply_structural_entity_type_exemption_reasons(symbol, metrics)
            self._apply_quality_recategorize_reasons_post(metrics, symbol)

            if stale_fallback_metrics:
                # One or more fields above came from a prior fiscal year (up to 6 years
                # back) via the cross-year "implausible anchor" rescue, not this symbol's
                # current reporting period. Flag it on data_source (VARCHAR(50) - keep this
                # short) so a downstream scoring/backtest consumer can at least tell this row
                # isn't purely fresh current-period data, since there's no per-field
                # provenance column to name which ones.
                metrics["data_source"] = "sec_audited_stale_fallback"
                logger.info(
                    f"[VALUE_QUALITY_GROWTH] {symbol}: data_source marked stale_fallback - "
                    f"fields from a prior fiscal year: {stale_fallback_metrics}"
                )
            elif net_income_from_ttm_quarterly:
                # net_income (and every ratio derived from it - roe/roa/net_margin/
                # sustainable_growth_rate/payout_ratio) came from a TTM sum of 4 real quarters,
                # not the annual anchor row - distinct from stale_fallback_metrics above (this
                # is current-period data, just not yet filed as a 10-K), but still worth a
                # provenance marker since it's not the usual annual_income_statement source.
                metrics["data_source"] = "sec_audited_ttm_quarterly"
                logger.info(f"[VALUE_QUALITY_GROWTH] {symbol}: net_income recovered from TTM quarterly sum")
            elif net_income_from_annual_fallback:
                # net_income (and every ratio derived from it) came from a prior real fiscal
                # year's annual_income_statement row, not the current anchor row or a TTM
                # quarterly sum - same "prior fiscal year" provenance semantics as
                # stale_fallback_metrics above, reusing its tag.
                metrics["data_source"] = "sec_audited_stale_fallback"
                logger.info(f"[VALUE_QUALITY_GROWTH] {symbol}: net_income recovered from prior annual fiscal year")

            return metrics

        except Exception as e:
            logger.warning(f"[VALUE_QUALITY_GROWTH] {symbol}: Quality metrics compute failed: {e}")
            # Propagate the real exception (not the generic "missing_sec_data" default) so a
            # genuine loader bug lands in scores.py's _categorize_reason() "Other (errors /
            # excluded)" bucket instead of silently inflating "Missing SEC/XBRL data" - same
            # fix already applied to this file's outer fetch_incremental() except block.
            exc_reason = f"fetch_exception: {type(e).__name__}: {str(e)[:150]}"
            return self._unavailable_marker("quality_metrics", symbol, reason=exc_reason)
