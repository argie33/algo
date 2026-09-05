"""Core financial-ratio computation helpers for `_compute_quality_metrics`.

Split out of vqg_quality_metrics.py (2026-09-04, "one 2,500-line function is still too bloated
even after being moved to its own file" pass): this is a pure extract-method refactor of two
tightly-related blocks from that single function - no computation, fallback order, tolerance,
threshold, or return value was changed. Every fix-history comment/live-verified sample
count/bound below is preserved byte-for-byte from its original location.

2026-09-05 second pass: `_compute_core_financial_ratios` and `_compute_roic_roce_and_leverage`
were themselves still too large (295/316 lines) relative to the repo's own gold-standard example
(`algo/risk/circuit_breaker.py`'s ~150-200-line `_check_*` methods). Both are now thin
orchestrators over private per-sub-metric helpers, one level deeper than the original monolith
split, same extract-method technique - no computation, fallback order, tolerance, threshold, or
return value changed here either. Every sub-helper takes exactly the inputs its slice of the
original code used and returns exactly what downstream code in the same original function needed;
`metrics`/`failed_metrics`/`implausible_ratio_metrics` are still mutated in place, matching the
original inline code's side effects.

`QualityRatiosMixin` provides:
- `_compute_core_financial_ratios`: ROE/ROA (via the shared cross-year-fallback ratio helper),
  operating/net margin, debt-to-assets, current/quick ratio, interest coverage, EV-metrics
  extraction, gross margin, EBITDA margin.
- `_compute_roic_roce_and_leverage`: ROIC/ROCE/debt-to-equity, which share the same
  NOPAT/invested-capital/capital-employed inputs and cross-year fallback searches.

Both mutate the caller's `metrics`/`failed_metrics`/`implausible_ratio_metrics` in place (same
objects the caller continues to use afterward) and return a small dataclass of the extra flags
downstream blocks (composite scoring, unavailable-reason assignment) need - everything else
computed here (e.g. `roic_stockholders_equity`, `invested_capital`, `effective_tax_rate`) is
purely local to these two methods in the original code and stays local here too.

Mixed into QualityMetricsMixin via multiple inheritance, same pattern as vqg_symbol_gates.py's
SymbolGateMixin - every `self.` call here resolves normally through the final composed instance.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loaders.helpers.vqg_symbol_gates import SymbolGateMixin
from utils.type_conversion import safe_float


def _owner() -> Any:
    from loaders import load_value_quality_growth_metrics as _owner_mod

    return _owner_mod


@dataclass
class CoreRatiosResult:
    """Flags/values from `_compute_core_financial_ratios` needed by later blocks."""

    operating_income_for_margin: float | None
    no_operating_income_concept: bool
    unclassified_balance_sheet: bool
    no_recent_interest_expense: bool
    no_operating_income_concept_ic: bool
    total_debt_ev: float | None
    total_cash_ev: float | None
    ebitda_ev: float | None
    sec_valuations_reason: str | None
    gross_profit_used: float | None
    no_gross_profit_concept: bool


@dataclass
class RoicRoceResult:
    """Flags/values from `_compute_roic_roce_and_leverage` needed by later blocks."""

    debt_for_roic: float | None
    roic_pct_unprofitable: bool
    roic_pct_negative_invested_capital: bool
    roce_pct_negative_capital_employed: bool
    no_operating_income_concept_roic: bool


@dataclass
class _NopatInputs:
    """Same-fiscal-year tax/pretax/operating-income/interest-expense/net-income quintuple used
    to derive NOPAT - internal to `_compute_roic_roce_and_leverage`'s helpers only."""

    tax_expense: float | None
    pretax_income: float | None
    operating_income: float | None
    interest_expense: float | None
    net_income: float | None


class QualityRatiosMixin(SymbolGateMixin):
    """See module docstring. TYPE_CHECKING stubs mirror vqg_quality_metrics.py's - only the
    cross-mixin members (defined directly on ValueQualityGrowthMetricsLoader) this file's
    methods actually call via `self.` are declared.
    """

    if TYPE_CHECKING:

        def _nan_to_none(self, value: float | None) -> float | None: ...

        def _fetch_annual_fallback_row(
            self, table: str, columns: str, extra_where: str, symbol: str
        ) -> tuple[Any, ...] | None: ...

        def _fetch_balance_sheet_anchor_fallback(self, symbol: str, column: str) -> float | None: ...

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

    # ------------------------------------------------------------------
    # _compute_core_financial_ratios and its per-sub-metric helpers
    # ------------------------------------------------------------------

    def _compute_roe_roa(
        self,
        symbol: str,
        net_income: float | None,
        stockholders_equity: float | None,
        total_assets: float | None,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
    ) -> None:
        """ROE/ROA - each via the shared cross-year-fallback ratio helper."""
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

    def _compute_operating_and_net_margins(
        self,
        symbol: str,
        operating_income: float | None,
        revenue: float | None,
        total_assets: float | None,
        pretax_income: float | None,
        interest_expense: float | None,
        net_income: float | None,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
    ) -> tuple[float | None, bool]:
        """Operating Margin and Net Margin, each with the bank (NULL-revenue) ROA-style fallback.

        Returns (operating_income_for_margin, no_operating_income_concept) - both needed by
        later blocks in the caller (interest-coverage flag reuses the no_tax_concept gate, EV
        block reads none of these, but the original inline code computed
        operating_income_for_margin here and it stays computed here).
        """
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
        if operating_income_for_margin is not None and operating_income_for_margin != 0:
            if revenue is not None and revenue != 0:
                computed_operating_margin = (operating_income_for_margin / revenue) * 100
            elif total_assets is not None and total_assets != 0:
                # Fallback: ROA of operating income (useful for banks with NULL revenue)
                computed_operating_margin = (operating_income_for_margin / total_assets) * 100
            else:
                computed_operating_margin = None
            if computed_operating_margin is None:
                failed_metrics.append("operating_margin")
            else:
                # Same near-zero-denominator garbage-value bound as gross_margin/
                # ebitda_margin/roic_pct above.
                if abs(computed_operating_margin) > 1000:
                    failed_metrics.append("operating_margin")
                    implausible_ratio_metrics.append("operating_margin")
                else:
                    metrics["operating_margin"] = float(computed_operating_margin)
        else:
            failed_metrics.append("operating_margin")

        # Net Margin = Net Income / Revenue
        # Fallback for banks (NULL revenue): use Net Income / Total Assets instead
        if net_income is not None and net_income != 0:
            if revenue is not None and revenue != 0:
                computed_net_margin = (net_income / revenue) * 100
            elif total_assets is not None and total_assets != 0:
                # Fallback: ROA of net income (useful for banks with NULL revenue)
                computed_net_margin = (net_income / total_assets) * 100
            else:
                computed_net_margin = None
            if computed_net_margin is None:
                failed_metrics.append("net_margin")
            else:
                # Same near-zero-denominator garbage-value bound as the margins above.
                if abs(computed_net_margin) > 1000:
                    failed_metrics.append("net_margin")
                    implausible_ratio_metrics.append("net_margin")
                else:
                    metrics["net_margin"] = float(computed_net_margin)
        else:
            failed_metrics.append("net_margin")

        return operating_income_for_margin, no_operating_income_concept

    def _compute_leverage_and_liquidity_ratios(
        self,
        symbol: str,
        current_assets: float | None,
        current_liabilities: float | None,
        inventory: float | None,
        total_liabilities: float | None,
        total_assets: float | None,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
    ) -> bool:
        """Debt-to-Assets, Current Ratio, Quick Ratio. Returns unclassified_balance_sheet."""
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
        return (
            current_assets is None
            and current_liabilities is None
            and symbol in self._get_unclassified_balance_sheet_symbols()
        )

    def _compute_interest_coverage_metric(
        self,
        symbol: str,
        interest_expense: float | None,
        interest_coverage_operating_income: float | None,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
    ) -> tuple[bool, bool]:
        """Interest Coverage. Returns (no_recent_interest_expense, no_operating_income_concept_ic)."""
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
            # A negligibly small interest_expense denominator blows this ratio up into
            # noise (real but meaningless), not a real coverage signal.
            if abs(computed_interest_coverage) > 1000:
                failed_metrics.append("interest_coverage")
                implausible_ratio_metrics.append("interest_coverage")
            else:
                metrics["interest_coverage"] = float(computed_interest_coverage)
        else:
            failed_metrics.append("interest_coverage")

        return no_recent_interest_expense, no_operating_income_concept_ic

    def _extract_ev_metrics(
        self, symbol: str, ev_metrics: Any
    ) -> tuple[float | None, float | None, float | None, str | None]:
        """Extract EV metrics from sec_valuations, if available.

        Returns (total_debt_ev, total_cash_ev, ebitda_ev, sec_valuations_reason).
        """
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

        return total_debt_ev, total_cash_ev, ebitda_ev, sec_valuations_reason

    def _compute_gross_and_ebitda_margins(
        self,
        symbol: str,
        gross_profit_direct: float | None,
        cost_of_revenue: float | None,
        revenue: float | None,
        ebitda_ev: float | None,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
    ) -> tuple[float | None, bool]:
        """Gross Margin (with prior-year fallback) and EBITDA Margin.

        Returns (gross_profit_used, no_gross_profit_concept).
        """
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
            computed_gross_margin = (gross_profit_used / gross_profit_revenue) * 100
            if abs(computed_gross_margin) > 1000:
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
                failed_metrics.append("ebitda_margin")
                implausible_ratio_metrics.append("ebitda_margin")
            else:
                metrics["ebitda_margin"] = float(computed_ebitda_margin)
        else:
            failed_metrics.append("ebitda_margin")

        return gross_profit_used, no_gross_profit_concept

    def _compute_core_financial_ratios(
        self,
        symbol: str,
        net_income: float | None,
        stockholders_equity: float | None,
        total_assets: float | None,
        revenue: float | None,
        operating_income: float | None,
        interest_expense: float | None,
        pretax_income: float | None,
        current_assets: float | None,
        current_liabilities: float | None,
        inventory: float | None,
        total_liabilities: float | None,
        gross_profit_direct: float | None,
        cost_of_revenue: float | None,
        ev_metrics: Any,
        interest_coverage_operating_income: float | None,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
    ) -> CoreRatiosResult:
        """ROE/ROA/margins/leverage/liquidity/interest-coverage/EV-extraction/gross+EBITDA margin.

        Thin orchestrator: each sub-metric family is computed by its own helper above (same
        extract-method split the original 2,581-line monolith itself got, one level deeper).
        Writes metrics["roe"], ["roa"], ["operating_margin"], ["net_margin"], ["debt_to_assets"],
        ["current_ratio"], ["quick_ratio"], ["interest_coverage"], ["gross_margin"],
        ["ebitda_margin"] and appends to failed_metrics/implausible_ratio_metrics - identical to
        the original inline code.
        """
        self._compute_roe_roa(
            symbol, net_income, stockholders_equity, total_assets, metrics, failed_metrics, implausible_ratio_metrics
        )

        operating_income_for_margin, no_operating_income_concept = self._compute_operating_and_net_margins(
            symbol,
            operating_income,
            revenue,
            total_assets,
            pretax_income,
            interest_expense,
            net_income,
            metrics,
            failed_metrics,
            implausible_ratio_metrics,
        )

        unclassified_balance_sheet = self._compute_leverage_and_liquidity_ratios(
            symbol,
            current_assets,
            current_liabilities,
            inventory,
            total_liabilities,
            total_assets,
            metrics,
            failed_metrics,
            implausible_ratio_metrics,
        )

        no_recent_interest_expense, no_operating_income_concept_ic = self._compute_interest_coverage_metric(
            symbol,
            interest_expense,
            interest_coverage_operating_income,
            metrics,
            failed_metrics,
            implausible_ratio_metrics,
        )

        total_debt_ev, total_cash_ev, ebitda_ev, sec_valuations_reason = self._extract_ev_metrics(symbol, ev_metrics)

        gross_profit_used, no_gross_profit_concept = self._compute_gross_and_ebitda_margins(
            symbol,
            gross_profit_direct,
            cost_of_revenue,
            revenue,
            ebitda_ev,
            metrics,
            failed_metrics,
            implausible_ratio_metrics,
        )

        return CoreRatiosResult(
            operating_income_for_margin=operating_income_for_margin,
            no_operating_income_concept=no_operating_income_concept,
            unclassified_balance_sheet=unclassified_balance_sheet,
            no_recent_interest_expense=no_recent_interest_expense,
            no_operating_income_concept_ic=no_operating_income_concept_ic,
            total_debt_ev=total_debt_ev,
            total_cash_ev=total_cash_ev,
            ebitda_ev=ebitda_ev,
            sec_valuations_reason=sec_valuations_reason,
            gross_profit_used=gross_profit_used,
            no_gross_profit_concept=no_gross_profit_concept,
        )

    # ------------------------------------------------------------------
    # _compute_roic_roce_and_leverage and its per-sub-metric helpers
    # ------------------------------------------------------------------

    def _resolve_nopat_inputs(
        self,
        symbol: str,
        quality_row: Any,
        income_tax_expense: float | None,
        pretax_income: float | None,
        operating_income: float | None,
        net_income: float | None,
    ) -> _NopatInputs:
        """Resolve the same-fiscal-year tax/pretax/operating-income/interest-expense/net-income
        quintuple NOPAT needs, searching cross-year fallbacks only to rescue whichever of
        operating_income/interest_expense the anchor year is missing (see inline comments).
        """
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
                        safe_float(fallback_tax_row[0], f"{symbol}.income_tax_expense_fallback_year", allow_none=True)
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

        if roic_operating_income is None and roic_pretax_income is not None and roic_interest_expense is not None:
            # EBIT approximation fallback - see comment above. roic_interest_expense is
            # always from the same row as roic_pretax_income (anchor or fallback_tax_row),
            # so this never mixes fiscal years.
            roic_operating_income = roic_pretax_income + roic_interest_expense

        return _NopatInputs(
            tax_expense=roic_tax_expense,
            pretax_income=roic_pretax_income,
            operating_income=roic_operating_income,
            interest_expense=roic_interest_expense,
            net_income=roic_net_income,
        )

    def _compute_effective_tax_rate(
        self,
        symbol: str,
        nopat_inputs: _NopatInputs,
        implausible_ratio_metrics: list[str],
    ) -> tuple[float | None, bool]:
        """Effective tax rate for NOPAT, bounded to [-60%, 60%]. Returns
        (effective_tax_rate, roic_pct_unprofitable)."""
        roic_tax_expense = nopat_inputs.tax_expense
        roic_pretax_income = nopat_inputs.pretax_income
        roic_net_income = nopat_inputs.net_income

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
        elif roic_tax_expense is None and roic_pretax_income is None and symbol in self._get_no_tax_concept_symbols():
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
        elif (
            roic_pretax_income is None
            and roic_tax_expense is not None
            and roic_tax_expense != 0
            and roic_net_income is not None
            and (roic_net_income + roic_tax_expense) > 0
            and symbol in self._get_never_tagged_pretax_income_symbols()
        ):
            # See _get_never_tagged_pretax_income_symbols - REITs/mortgage trusts never tag
            # a distinct pretax_income concept but do report a real, usually small,
            # income_tax_expense. The general net_income+tax_expense approximation for
            # pretax_income is rejected elsewhere (NCI/discontinued-ops noise), but scoped
            # narrowly here (confirmed-absent concept, same-fiscal-year net_income, same
            # [-0.60, 0.60] bound as every other branch) it's safe: when tax is this small
            # relative to net_income, even a materially wrong pretax base yields only a
            # small implied rate.
            candidate_rate = roic_tax_expense / (roic_net_income + roic_tax_expense)
            if -0.60 <= candidate_rate <= 0.60:
                effective_tax_rate = candidate_rate
            else:
                implausible_ratio_metrics.append("roic_pct")

        return effective_tax_rate, roic_pct_unprofitable

    def _resolve_invested_capital(
        self,
        symbol: str,
        stockholders_equity: float | None,
        cash_and_equivalents_bs: float | None,
        long_term_debt_bs: float | None,
        total_debt_ev: float | None,
    ) -> tuple[float | None, float | None, float | None, bool]:
        """Resolve Invested Capital = Stockholders' Equity + Total Debt - Cash & Equivalents.

        Returns (roic_stockholders_equity, debt_for_roic, invested_capital,
        roic_pct_negative_invested_capital).
        """
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
        roic_long_term_debt = long_term_debt_bs
        if total_debt_ev is None and long_term_debt_bs is None:
            # `data_unavailable IS NOT TRUE` (applied inside the helper) excludes an
            # incomplete/stale-orphan stub.
            fallback_debt = self._fetch_balance_sheet_anchor_fallback(symbol, "long_term_debt")
            if fallback_debt is not None:
                roic_long_term_debt = fallback_debt

        invested_capital = None
        debt_for_roic = total_debt_ev if total_debt_ev is not None else roic_long_term_debt

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

        if roic_stockholders_equity is not None and debt_for_roic is not None and roic_cash_and_equivalents is not None:
            invested_capital = roic_stockholders_equity + debt_for_roic - roic_cash_and_equivalents
        # A large cash pile (common for well-capitalized biotechs, e.g. equity-raise-funded)
        # can push equity + debt - cash negative even with real, complete SEC data - a real
        # business-state fact, not an absent concept (same distinction as
        # roic_pct_unprofitable below for pretax losses).
        roic_pct_negative_invested_capital = invested_capital is not None and invested_capital <= 0

        return roic_stockholders_equity, debt_for_roic, invested_capital, roic_pct_negative_invested_capital

    def _compute_roic_pct(
        self,
        effective_tax_rate: float | None,
        roic_operating_income: float | None,
        invested_capital: float | None,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
    ) -> None:
        """ROIC = NOPAT / Invested Capital, NOPAT = EBIT * (1 - effective_tax_rate)."""
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
            if abs(computed_roic_pct) > 1000:
                failed_metrics.append("roic_pct")
                implausible_ratio_metrics.append("roic_pct")
            else:
                metrics["roic_pct"] = float(computed_roic_pct)
        else:
            failed_metrics.append("roic_pct")

    def _compute_roce_pct(
        self,
        roic_operating_income: float | None,
        roic_stockholders_equity: float | None,
        debt_for_roic: float | None,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
    ) -> bool:
        """ROCE = EBIT / (Equity + Debt). Returns roce_pct_negative_capital_employed."""
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
            if abs(computed_roce_pct) > 1000:
                failed_metrics.append("roce_pct")
                implausible_ratio_metrics.append("roce_pct")
            else:
                metrics["roce_pct"] = float(computed_roce_pct)
        else:
            failed_metrics.append("roce_pct")

        return roce_pct_negative_capital_employed

    def _compute_debt_to_equity(
        self,
        roic_stockholders_equity: float | None,
        debt_for_roic: float | None,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
    ) -> None:
        """Debt to Equity: interest-bearing Debt / Equity."""
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
        else:
            failed_metrics.append("debt_to_equity")

    def _compute_roic_roce_and_leverage(
        self,
        symbol: str,
        quality_row: Any,
        income_tax_expense: float | None,
        pretax_income: float | None,
        operating_income: float | None,
        net_income: float | None,
        stockholders_equity: float | None,
        cash_and_equivalents_bs: float | None,
        long_term_debt_bs: float | None,
        total_debt_ev: float | None,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
    ) -> RoicRoceResult:
        """ROIC/ROCE/Debt-to-Equity - share NOPAT/invested-capital/capital-employed inputs.

        Thin orchestrator: NOPAT-input resolution, effective-tax-rate, and invested-capital
        resolution are each genuinely separable sub-concerns (own helpers above) despite
        sharing inputs downstream - only ROIC/ROCE/debt-to-equity themselves stay as three
        small, independent final-ratio helpers since each is a single formula once its inputs
        are resolved. Writes metrics["roic_pct"], ["roce_pct"], ["debt_to_equity"] and appends
        to failed_metrics/implausible_ratio_metrics - identical to the original inline code.
        """
        nopat_inputs = self._resolve_nopat_inputs(
            symbol, quality_row, income_tax_expense, pretax_income, operating_income, net_income
        )

        effective_tax_rate, roic_pct_unprofitable = self._compute_effective_tax_rate(
            symbol, nopat_inputs, implausible_ratio_metrics
        )

        roic_stockholders_equity, debt_for_roic, invested_capital, roic_pct_negative_invested_capital = (
            self._resolve_invested_capital(
                symbol, stockholders_equity, cash_and_equivalents_bs, long_term_debt_bs, total_debt_ev
            )
        )

        roic_operating_income = nopat_inputs.operating_income
        # roic_operating_income (NOPAT's other input) can independently be None for
        # no-tax-concept REITs even when effective_tax_rate's own branch already handles
        # them - same structural-not-missing gate.
        no_operating_income_concept_roic = (
            roic_operating_income is None and symbol in self._get_no_tax_concept_symbols()
        )

        self._compute_roic_pct(
            effective_tax_rate,
            roic_operating_income,
            invested_capital,
            metrics,
            failed_metrics,
            implausible_ratio_metrics,
        )

        roce_pct_negative_capital_employed = self._compute_roce_pct(
            roic_operating_income,
            roic_stockholders_equity,
            debt_for_roic,
            metrics,
            failed_metrics,
            implausible_ratio_metrics,
        )

        self._compute_debt_to_equity(
            roic_stockholders_equity, debt_for_roic, metrics, failed_metrics, implausible_ratio_metrics
        )

        return RoicRoceResult(
            debt_for_roic=debt_for_roic,
            roic_pct_unprofitable=roic_pct_unprofitable,
            roic_pct_negative_invested_capital=roic_pct_negative_invested_capital,
            roce_pct_negative_capital_employed=roce_pct_negative_capital_employed,
            no_operating_income_concept_roic=no_operating_income_concept_roic,
        )
