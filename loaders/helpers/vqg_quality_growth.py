"""Cash-flow-ratio and YoY-growth/trend computation helpers for `_compute_quality_metrics`.

Split out of vqg_quality_metrics.py (2026-09-04, same pass as vqg_quality_ratios.py - see that
module's docstring). Pure extract-method refactor: no computation, fallback order, tolerance,
threshold, or return value was changed from the original inline code. Every fix-history
comment/live-verified sample count/bound below is preserved byte-for-byte.

`QualityGrowthMixin` provides:
- `_compute_cash_flow_ratios`: fcf_to_net_income, ocf_to_net_income, payout_ratio, the absolute
  free_cash_flow/operating_cash_flow/total_debt/total_cash/ebitda values, cash_per_share.
- `_compute_yoy_growth_metrics`: earnings/revenue growth YoY, net_income/operating_income
  growth YoY, and the three margin trends (gross/operating/net).
- `_compute_sgr_and_remaining_trends`: sustainable_growth_rate, ROE trend, FCF/OCF/asset growth
  YoY, and the shared trend-field unavailable-reason loop.

All three mutate the caller's `metrics`/`failed_metrics`/`implausible_ratio_metrics` (plus, for
the two growth methods, the caller's `sign_change_yoy_metrics`/`immaterial_base_yoy_metrics`,
which are local-only to these two methods in the original code and are threaded through as
shared lists so both can append to them before the trend-reason loop reads them).

Mixed into QualityMetricsMixin via multiple inheritance, same pattern as vqg_symbol_gates.py's
SymbolGateMixin - every `self.` call here resolves normally through the final composed instance.
"""

import logging
from typing import TYPE_CHECKING, Any

from loaders.helpers.vqg_symbol_gates import SymbolGateMixin

logger = logging.getLogger("loaders.load_value_quality_growth_metrics")


class QualityGrowthMixin(SymbolGateMixin):
    """See module docstring. TYPE_CHECKING stubs mirror vqg_quality_metrics.py's - only the
    cross-mixin members (defined directly on ValueQualityGrowthMetricsLoader) this file's
    methods actually call via `self.` are declared.
    """

    if TYPE_CHECKING:

        def _has_recent_dividend_history(self, symbol: str) -> bool: ...

    def _compute_cash_flow_ratios(
        self,
        symbol: str,
        free_cash_flow: float | None,
        net_income: float | None,
        operating_cash_flow: float | None,
        dividends_paid_with_prior_year_fallback: float | None,
        total_debt_ev: float | None,
        total_cash_ev: float | None,
        ebitda_ev: float | None,
        shares_outstanding: float | None,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        max_absolute_dollar_value: float,
    ) -> tuple[str | None, bool]:
        """FCF/OCF-to-net-income, payout ratio, absolute cash-flow values, cash per share.

        Writes metrics["fcf_to_net_income"], ["ocf_to_net_income"], ["payout_ratio"],
        ["free_cash_flow"], ["operating_cash_flow"], ["total_debt"], ["total_cash"],
        ["ebitda"], ["cash_per_share"] and appends to failed_metrics - identical to the
        original inline code. Returns (payout_ratio_reason, cash_per_share_shares_missing),
        both needed by the later unavailable-reason assignment.
        """
        # FCF to Net Income = Free Cash Flow / Net Income
        if free_cash_flow is not None and net_income is not None and net_income != 0:
            metrics["fcf_to_net_income"] = float(free_cash_flow / net_income)
        else:
            failed_metrics.append("fcf_to_net_income")

        # OCF to Net Income = Operating Cash Flow / Net Income
        if operating_cash_flow is not None and net_income is not None and net_income != 0:
            metrics["ocf_to_net_income"] = float(operating_cash_flow / net_income)
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
            else:
                # Same "ever, not recently" distinction as dividend_yield_reason above - a
                # symbol that discontinued its dividend years ago has real history on file
                # but isn't a current data gap. Same 2-year recency window used there.
                has_real_dividend_history = self._has_recent_dividend_history(symbol)
                payout_ratio_reason = "missing_sec_data" if has_real_dividend_history else "non_dividend_paying_stock"

        # Absolute cash flow values
        if free_cash_flow is not None and abs(free_cash_flow) < max_absolute_dollar_value:
            metrics["free_cash_flow"] = float(free_cash_flow)
        else:
            failed_metrics.append("free_cash_flow")

        if operating_cash_flow is not None and abs(operating_cash_flow) < max_absolute_dollar_value:
            metrics["operating_cash_flow"] = float(operating_cash_flow)
        else:
            failed_metrics.append("operating_cash_flow")

        # Absolute balance sheet values from sec_valuations
        if total_debt_ev is not None and abs(total_debt_ev) < max_absolute_dollar_value:
            metrics["total_debt"] = float(total_debt_ev)
        else:
            failed_metrics.append("total_debt")

        if total_cash_ev is not None and abs(total_cash_ev) < max_absolute_dollar_value:
            metrics["total_cash"] = float(total_cash_ev)
        else:
            failed_metrics.append("total_cash")

        if ebitda_ev is not None and abs(ebitda_ev) < max_absolute_dollar_value:
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

        return payout_ratio_reason, cash_per_share_shares_missing

    def _compute_yoy_growth_metrics(  # noqa: C901 -- inherent branching of the tiered
        # SEC/XBRL fallback pattern applied per YoY growth metric (earnings/revenue/net-income/
        # operating-income); extracted verbatim from the original monolith.
        self,
        symbol: str,
        earnings_per_share: float | None,
        prior_year_eps: float | None,
        revenue: float | None,
        prior_year_revenue: float | None,
        net_income: float | None,
        prior_year_net_income: float | None,
        operating_income_for_margin: float | None,
        prior_year_operating_income_for_trend: float | None,
        gross_profit_direct: float | None,
        cost_of_revenue: float | None,
        prior_year_gross_profit: float | None,
        prior_year_cost_of_revenue: float | None,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
        sign_change_yoy_metrics: list[str],
        immaterial_base_yoy_metrics: list[str],
        max_plausible_growth_pct: float,
        max_trend_percentage_points: float,
    ) -> None:
        """Earnings/revenue growth YoY, net_income/operating_income growth YoY, margin trends.

        Writes metrics["earnings_growth_yoy"], ["revenue_growth_yoy"],
        ["net_income_growth_yoy"], ["operating_income_growth_yoy"], ["gross_margin_trend"],
        ["operating_margin_trend"], ["net_margin_trend"] and appends to
        failed_metrics/implausible_ratio_metrics/sign_change_yoy_metrics/
        immaterial_base_yoy_metrics - identical to the original inline code.
        """
        # Earnings Growth YoY = (Current EPS - Prior Year EPS) / Prior Year EPS * 100.
        # Bounded like the sibling *_growth_yoy fields below: a near-zero prior-year base
        # can overflow NUMERIC(10,2) and crash the whole row's INSERT. Appends to
        # implausible_ratio_metrics (in addition to failed_metrics) so a real-but-rejected
        # ratio is distinguished from a genuinely absent prior-year base.
        if earnings_per_share is not None and prior_year_eps is not None and prior_year_eps != 0:
            try:
                yoy_growth = ((earnings_per_share - prior_year_eps) / abs(prior_year_eps)) * 100
                if abs(yoy_growth) < max_trend_percentage_points:
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
                if abs(yoy_growth) < max_trend_percentage_points:
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
                    if abs(ni_growth) < max_plausible_growth_pct:
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
                    if abs(oi_growth) < max_trend_percentage_points:
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
                    prior_year_revenue - prior_year_cost_of_revenue if prior_year_cost_of_revenue is not None else None
                )
            )
            if curr_gross_profit is not None and prior_gross_profit is not None:
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
                        if abs(gm_trend) < max_trend_percentage_points:
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
                curr_om = (operating_income_for_margin / revenue) * 100
                prior_om = (prior_year_operating_income_for_trend / prior_year_revenue) * 100
                if abs(curr_om) <= MAX_MARGIN_ABS_PCT and abs(prior_om) <= MAX_MARGIN_ABS_PCT:
                    try:
                        om_trend = round(curr_om - prior_om, 2)
                        if abs(om_trend) < max_trend_percentage_points:
                            metrics["operating_margin_trend"] = float(om_trend)
                        else:
                            implausible_ratio_metrics.append("operating_margin_trend")
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass
                else:
                    implausible_ratio_metrics.append("operating_margin_trend")

            # Net Margin Trend - only if actual prior net income available
            if net_income is not None and prior_year_net_income is not None and prior_year_revenue > 0:
                curr_nm = (net_income / revenue) * 100
                prior_nm = (prior_year_net_income / prior_year_revenue) * 100
                if abs(curr_nm) <= MAX_MARGIN_ABS_PCT and abs(prior_nm) <= MAX_MARGIN_ABS_PCT:
                    try:
                        nm_trend = round(curr_nm - prior_nm, 2)
                        if abs(nm_trend) < max_trend_percentage_points:
                            metrics["net_margin_trend"] = float(nm_trend)
                        else:
                            implausible_ratio_metrics.append("net_margin_trend")
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass
                else:
                    implausible_ratio_metrics.append("net_margin_trend")

    def _compute_sgr_and_remaining_trends(  # noqa: C901 -- inherent branching of the tiered
        # SEC/XBRL fallback pattern applied per trend metric (SGR, ROE trend, FCF/OCF/asset
        # growth YoY); extracted verbatim from the original monolith.
        self,
        symbol: str,
        stockholders_equity: float | None,
        net_income: float | None,
        dividends_paid_with_prior_year_fallback: float | None,
        prior_year_stockholders_equity: float | None,
        prior_year_net_income: float | None,
        free_cash_flow: float | None,
        prior_year_free_cash_flow: float | None,
        operating_cash_flow: float | None,
        prior_year_operating_cash_flow: float | None,
        total_assets: float | None,
        prior_year_total_assets: float | None,
        prior_year_revenue: float | None,
        no_gross_profit_concept: bool,
        metrics: dict[str, Any],
        implausible_ratio_metrics: list[str],
        sign_change_yoy_metrics: list[str],
        immaterial_base_yoy_metrics: list[str],
        max_plausible_growth_pct: float,
        max_trend_percentage_points: float,
    ) -> None:
        """Sustainable growth rate, ROE trend, FCF/OCF/asset growth YoY, trend-reason loop.

        Writes metrics["sustainable_growth_rate"] (+ its own reason), ["roe_trend"],
        ["fcf_growth_yoy"], ["ocf_growth_yoy"], ["asset_growth_yoy"], and the 9
        `*_unavailable_reason` trend fields (mirrored into growth_metrics via the
        _SHARED_TREND_FIELDS copy in the owner module) - identical to the original inline
        code. Appends to implausible_ratio_metrics/sign_change_yoy_metrics/
        immaterial_base_yoy_metrics.
        """
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
            has_real_dividend_history = self._has_recent_dividend_history(symbol)
            if has_real_dividend_history:
                sgr_reason = "missing_sec_data"
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
                    if abs(sgr) < max_plausible_growth_pct:
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
        MAX_MARGIN_ABS_PCT = 1000.0  # noqa: N806
        if (
            stockholders_equity is not None
            and net_income is not None
            and stockholders_equity != 0
            and prior_year_stockholders_equity is not None
            and prior_year_net_income is not None
            and prior_year_stockholders_equity != 0
        ):
            curr_roe = (net_income / stockholders_equity) * 100
            prior_roe = (prior_year_net_income / prior_year_stockholders_equity) * 100
            if abs(curr_roe) <= MAX_MARGIN_ABS_PCT and abs(prior_roe) <= MAX_MARGIN_ABS_PCT:
                try:
                    roe_trend = round(curr_roe - prior_roe, 2)
                    if abs(roe_trend) < max_trend_percentage_points:
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
                    fcf_growth = ((free_cash_flow - prior_year_free_cash_flow) / abs(prior_year_free_cash_flow)) * 100
                    if abs(fcf_growth) < max_plausible_growth_pct:
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
                    if abs(ocf_growth) < max_trend_percentage_points:
                        metrics["ocf_growth_yoy"] = float(round(ocf_growth, 2))
                    else:
                        implausible_ratio_metrics.append("ocf_growth_yoy")
                except (ValueError, TypeError, ZeroDivisionError):
                    pass

        # Asset Growth YoY - now can compute with prior-year total assets
        if total_assets is not None and prior_year_total_assets is not None and prior_year_total_assets != 0:
            try:
                asset_growth = ((total_assets - prior_year_total_assets) / abs(prior_year_total_assets)) * 100
                if abs(asset_growth) < max_trend_percentage_points:
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

        # sustainable_growth_rate uses NO prior-year data (see its own computation above),
        # so it gets its own explicit sgr_reason rather than the blanket trend-field loop.
        if metrics.get("sustainable_growth_rate") is None:
            metrics["sustainable_growth_rate_unavailable_reason"] = sgr_reason or "missing_sec_data"
