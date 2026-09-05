"""Unavailable-reason assembly helpers for `_compute_quality_metrics`.

Split out of vqg_quality_metrics.py (2026-09-04, same pass as vqg_quality_ratios.py - see that
module's docstring). Pure extract-method refactor: no reason string, precedence order, or gate
condition was changed from the original inline code. Every fix-history comment/live-verified
sample count/bound below is preserved byte-for-byte.

`QualityReasonsMixin` provides:
- `_assign_core_ratio_unavailable_reasons`: roe/roa/operating_margin/net_margin/
  debt_to_equity/current_ratio/quick_ratio/interest_coverage/debt_to_assets.
- `_assign_extended_metric_unavailable_reasons`: gross_margin/ebitda_margin/roic_pct/
  roce_pct/fcf_to_net_income/ocf_to_net_income/payout_ratio/free_cash_flow/
  operating_cash_flow/total_debt/total_cash/cash_per_share/ebitda/earnings_growth_yoy/
  revenue_growth_yoy.
- `_assign_quarterly_and_analyst_fallback_reasons`: the generic fallback reasons for the
  quarterly-derived and not-yet-implemented analyst-estimate fields, only filled in when
  `_compute_quarterly_metrics` (merged into `metrics` earlier) didn't already set a more
  specific reason.
- `_recategorize_royalty_trust_reasons`: recategorizes grantor-trust symbols' structurally
  absent debt/cash/interest/FCF-derived fields from their generic reason to
  "reit_special_entity".

All four only read from `metrics`/`failed_metrics`/`implausible_ratio_metrics` and the flags
passed in, then write `*_unavailable_reason` keys into `metrics` - none of them compute a new
VALUE.

Mixed into QualityMetricsMixin via multiple inheritance, same pattern as vqg_symbol_gates.py's
SymbolGateMixin - every `self.` call here resolves normally through the final composed instance.
"""

from typing import TYPE_CHECKING, Any

from loaders.helpers.vqg_symbol_gates import SymbolGateMixin


class QualityReasonsMixin(SymbolGateMixin):
    """See module docstring."""

    if TYPE_CHECKING:
        _ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS: frozenset[str]

    def _assign_core_ratio_unavailable_reasons(
        self,
        symbol: str,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
        stockholders_equity: float | None,
        net_income: float | None,
        total_assets: float | None,
        no_operating_income_concept: bool,
        operating_income_for_margin: float | None,
        no_recent_interest_expense: bool,
        no_operating_income_concept_ic: bool,
        unclassified_balance_sheet: bool,
        current_assets: float | None,
        current_liabilities: float | None,
        total_liabilities: float | None,
        debt_for_roic: float | None,
    ) -> None:
        """roe/roa/operating_margin/net_margin/debt_to_equity/current_ratio/quick_ratio/
        interest_coverage/debt_to_assets `*_unavailable_reason` fields - identical
        precedence/gates to the original inline code.
        """
        # Only mark data_unavailable if ALL metrics are missing - partial quality data
        # (2-3 metrics) is legitimate and scored with completeness tracking, not discarded.
        metrics["roe_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "roe" in implausible_ratio_metrics
                else "stockholders_equity_not_reported"
                if stockholders_equity is None
                and (
                    symbol in self._get_no_recent_stockholders_equity_symbols()
                    or symbol in self._get_never_tagged_stockholders_equity_symbols()
                )
                else "net_income_not_reported"
                if net_income is None
                and (
                    symbol in self._get_no_recent_net_income_symbols()
                    or symbol in self._get_never_tagged_net_income_symbols()
                )
                # Label-only: net_income is None because the anchor year's own
                # income-statement row is unavailable, not because it lacks real net_income.
                else "net_income_absent_from_anchor_year"
                if net_income is None and symbol in self._get_net_income_available_elsewhere_symbols()
                else "missing_sec_data"
            )
            if "roe" in failed_metrics
            else None
        )
        metrics["roa_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "roa" in implausible_ratio_metrics
                else "no_recent_total_assets_reported"
                if total_assets is None
                and (
                    symbol in self._get_no_recent_total_assets_symbols()
                    or symbol in self._get_never_tagged_total_assets_symbols()
                )
                else "net_income_not_reported"
                if net_income is None
                and (
                    symbol in self._get_no_recent_net_income_symbols()
                    or symbol in self._get_never_tagged_net_income_symbols()
                )
                else "net_income_absent_from_anchor_year"
                if net_income is None and symbol in self._get_net_income_available_elsewhere_symbols()
                else "missing_sec_data"
            )
            if "roa" in failed_metrics
            else None
        )
        metrics["operating_margin_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "operating_margin" in implausible_ratio_metrics
                # Tonnage-tax shipping cos + REITs structurally never tag
                # pretax_income/income_tax_expense (_get_no_tax_concept_symbols) -
                # recategorized as reit_special_entity, not generic missing_sec_data.
                else "reit_special_entity"
                if no_operating_income_concept
                # Label-only: anchor year's income statement lacks operating_income even
                # though the symbol reports it elsewhere.
                else "operating_income_absent_from_anchor_year"
                if operating_income_for_margin is None
                and symbol in self._get_operating_income_available_elsewhere_symbols()
                else "no_revenue_reported"
                if operating_income_for_margin is None
                and (
                    symbol in self._get_blank_check_symbols()
                    or symbol in self._get_no_recent_revenue_symbols()
                    or symbol in self._get_never_tagged_revenue_symbols()
                )
                # Real, revenue-generating filer whose income statement never itemizes a
                # distinct operating income subtotal.
                else "operating_income_not_itemized"
                if operating_income_for_margin is None
                and (
                    symbol in self._get_no_recent_operating_income_symbols()
                    or symbol in self._get_never_tagged_operating_income_symbols()
                )
                else "missing_sec_data"
            )
            if "operating_margin" in failed_metrics
            else None
        )
        metrics["net_margin_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "net_margin" in implausible_ratio_metrics
                else "net_income_not_reported"
                if net_income is None
                and (
                    symbol in self._get_no_recent_net_income_symbols()
                    or symbol in self._get_never_tagged_net_income_symbols()
                )
                # Label-only: net_income is None because the balance-sheet anchor year's
                # own income-statement row is unavailable, not because the symbol lacks
                # real net_income - both gates above already ruled that out.
                else "net_income_absent_from_anchor_year"
                if net_income is None and symbol in self._get_net_income_available_elsewhere_symbols()
                else "missing_sec_data"
            )
            if "net_margin" in failed_metrics
            else None
        )
        metrics["debt_to_equity_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "debt_to_equity" in implausible_ratio_metrics
                else "stockholders_equity_not_reported"
                if stockholders_equity is None
                and (
                    symbol in self._get_no_recent_stockholders_equity_symbols()
                    or symbol in self._get_never_tagged_stockholders_equity_symbols()
                )
                # debt_to_equity fails when EITHER roic_stockholders_equity or debt_for_roic
                # is None - check the debt side too, not just equity.
                else "total_debt_not_itemized"
                if debt_for_roic is None
                and (
                    symbol in self._get_no_recent_debt_components_symbols()
                    or symbol in self._get_never_tagged_debt_components_symbols()
                )
                else "missing_sec_data"
            )
            if "debt_to_equity" in failed_metrics
            else None
        )
        metrics["current_ratio_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "current_ratio" in implausible_ratio_metrics
                else "reit_special_entity"
                if unclassified_balance_sheet
                else "no_recent_current_assets_reported"
                if current_assets is None
                and (
                    symbol in self._get_no_recent_current_assets_symbols()
                    or symbol in self._get_never_tagged_current_assets_symbols()
                )
                else "no_recent_current_liabilities_reported"
                if current_liabilities is None
                and (
                    symbol in self._get_no_recent_current_liabilities_symbols()
                    or symbol in self._get_never_tagged_current_liabilities_symbols()
                )
                else "missing_sec_data"
            )
            if "current_ratio" in failed_metrics
            else None
        )
        metrics["quick_ratio_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "quick_ratio" in implausible_ratio_metrics
                else "reit_special_entity"
                if unclassified_balance_sheet
                # quick_ratio shares current_ratio's structural inputs; inventory's absence
                # is a normal "not a goods business" fact, not a data gap, deliberately not
                # gated.
                else "no_recent_current_assets_reported"
                if current_assets is None
                and (
                    symbol in self._get_no_recent_current_assets_symbols()
                    or symbol in self._get_never_tagged_current_assets_symbols()
                )
                else "no_recent_current_liabilities_reported"
                if current_liabilities is None
                and (
                    symbol in self._get_no_recent_current_liabilities_symbols()
                    or symbol in self._get_never_tagged_current_liabilities_symbols()
                )
                else "missing_sec_data"
            )
            if "quick_ratio" in failed_metrics
            else None
        )
        metrics["interest_coverage_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "interest_coverage" in implausible_ratio_metrics
                else "interest_expense_not_itemized"
                if no_recent_interest_expense
                else "reit_special_entity"
                if no_operating_income_concept_ic
                else "operating_income_not_itemized"
                if symbol in self._get_no_recent_operating_income_symbols()
                or symbol in self._get_never_tagged_operating_income_symbols()
                else "missing_sec_data"
            )
            if "interest_coverage" in failed_metrics
            else None
        )
        metrics["debt_to_assets_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "debt_to_assets" in implausible_ratio_metrics
                else "no_recent_total_assets_reported"
                if total_assets is None
                and (
                    symbol in self._get_no_recent_total_assets_symbols()
                    or symbol in self._get_never_tagged_total_assets_symbols()
                )
                else "total_liabilities_not_reported"
                if total_liabilities is None
                and (
                    symbol in self._get_no_recent_total_liabilities_symbols()
                    or symbol in self._get_never_tagged_total_liabilities_symbols()
                )
                else "missing_sec_data"
            )
            if "debt_to_assets" in failed_metrics
            else None
        )

    def _assign_extended_metric_unavailable_reasons(
        self,
        symbol: str,
        metrics: dict[str, Any],
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
        no_gross_profit_concept: bool,
        revenue: float | None,
        no_operating_income_concept: bool,
        roic_pct_unprofitable: bool,
        roic_pct_negative_invested_capital: bool,
        no_operating_income_concept_roic: bool,
        debt_for_roic: float | None,
        stockholders_equity: float | None,
        roce_pct_negative_capital_employed: bool,
        free_cash_flow: float | None,
        net_income: float | None,
        operating_cash_flow: float | None,
        cash_per_share_shares_missing: bool,
        ev_metrics: Any,
        sec_valuations_reason: str | None,
        payout_ratio_reason: str | None,
    ) -> None:
        """gross_margin/ebitda_margin/roic_pct/roce_pct/fcf_to_net_income/ocf_to_net_income/
        payout_ratio/free_cash_flow/operating_cash_flow/total_debt/total_cash/
        cash_per_share/ebitda/earnings_growth_yoy/revenue_growth_yoy
        `*_unavailable_reason` fields - identical precedence/gates to the original inline
        code.
        """
        # Phase 3 Expansion (Session 357+): New metrics - initialize their _unavailable_reason fields
        metrics["gross_margin_unavailable_reason"] = (
            (
                "reit_special_entity"
                if no_gross_profit_concept
                else "implausible_ratio"
                if "gross_margin" in implausible_ratio_metrics
                else "no_revenue_reported"
                if symbol in self._get_blank_check_symbols()
                or symbol in self._get_no_recent_revenue_symbols()
                or symbol in self._get_never_tagged_revenue_symbols()
                # Label-only: gross_profit_revenue (this field's own denominator, read from
                # the same balance-sheet-anchor-joined row as `revenue`) is None because
                # that anchor fiscal year's own income-statement row lacks it, not because
                # the symbol lacks real revenue anywhere.
                else "revenue_absent_from_anchor_year"
                if revenue is None and symbol in self._get_revenue_available_elsewhere_symbols()
                else "missing_sec_data"
            )
            if "gross_margin" in failed_metrics
            else None
        )
        metrics["ebitda_margin_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "ebitda_margin" in implausible_ratio_metrics
                # load_sec_valuations.py's own EBITDA computation (EBITDA = OperatingIncome
                # + D&A) requires operating_income and stays None when it's absent - same
                # REIT/tonnage-tax-exempt population no_operating_income_concept identifies,
                # cascading into ebitda_ev is None here.
                else "reit_special_entity"
                if no_operating_income_concept
                else "no_revenue_reported"
                if symbol in self._get_no_recent_revenue_symbols()
                or symbol in self._get_never_tagged_revenue_symbols()
                or symbol in self._get_blank_check_symbols()
                # Label-only, no value recomputed.
                else "revenue_absent_from_anchor_year"
                if revenue is None and symbol in self._get_revenue_available_elsewhere_symbols()
                # ebitda_margin also depends on operating_income via EBITDA = OperatingIncome
                # + D&A - same operating_income_not_itemized case as operating_margin/
                # interest_coverage above.
                else "operating_income_not_itemized"
                if symbol in self._get_no_recent_operating_income_symbols()
                or symbol in self._get_never_tagged_operating_income_symbols()
                else "missing_sec_data"
            )
            if "ebitda_margin" in failed_metrics
            else None
        )
        metrics["roic_pct_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "roic_pct" in implausible_ratio_metrics
                else "unprofitable_stock"
                if roic_pct_unprofitable
                else "negative_invested_capital"
                if roic_pct_negative_invested_capital
                # Commodity/crypto trusts (GLD, GLDM, GLTR, IAUM, AAAU, BTCO) structurally
                # report no revenue by their trust/ETF nature - same "no operating business"
                # fact blank-check SPACs represent, just not SIC-classified as one.
                else "no_revenue_reported"
                if symbol in self._get_blank_check_symbols()
                or symbol in self._get_no_recent_revenue_symbols()
                or symbol in self._get_never_tagged_revenue_symbols()
                else "reit_special_entity"
                if no_operating_income_concept_roic
                # invested_capital (this field's own denominator) comes back None whenever
                # debt_for_roic OR roic_stockholders_equity is None - the
                # negative_invested_capital branch above only catches a computed non-None
                # value <= 0, not a missing input.
                else "total_debt_not_itemized"
                if debt_for_roic is None
                and (
                    symbol in self._get_no_recent_debt_components_symbols()
                    or symbol in self._get_never_tagged_debt_components_symbols()
                )
                else "stockholders_equity_not_reported"
                if stockholders_equity is None
                and (
                    symbol in self._get_no_recent_stockholders_equity_symbols()
                    or symbol in self._get_never_tagged_stockholders_equity_symbols()
                )
                else "operating_income_not_itemized"
                if symbol in self._get_no_recent_operating_income_symbols()
                or symbol in self._get_never_tagged_operating_income_symbols()
                else "missing_sec_data"
            )
            if "roic_pct" in failed_metrics
            else None
        )
        metrics["roce_pct_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "roce_pct" in implausible_ratio_metrics
                else "negative_capital_employed"
                if roce_pct_negative_capital_employed
                else "no_revenue_reported"
                if symbol in self._get_blank_check_symbols()
                or symbol in self._get_no_recent_revenue_symbols()
                or symbol in self._get_never_tagged_revenue_symbols()
                # roce_pct shares roic_operating_income (EBIT numerator) with roic_pct -
                # same REIT structural gap.
                else "reit_special_entity"
                if no_operating_income_concept_roic
                # capital_employed (this field's own denominator) comes back None whenever
                # debt_for_roic OR roic_stockholders_equity is None, which
                # negative_capital_employed's <=0 check doesn't catch.
                else "total_debt_not_itemized"
                if debt_for_roic is None
                and (
                    symbol in self._get_no_recent_debt_components_symbols()
                    or symbol in self._get_never_tagged_debt_components_symbols()
                )
                else "stockholders_equity_not_reported"
                if stockholders_equity is None
                and (
                    symbol in self._get_no_recent_stockholders_equity_symbols()
                    or symbol in self._get_never_tagged_stockholders_equity_symbols()
                )
                else "operating_income_not_itemized"
                if symbol in self._get_no_recent_operating_income_symbols()
                or symbol in self._get_never_tagged_operating_income_symbols()
                else "missing_sec_data"
            )
            if "roce_pct" in failed_metrics
            else None
        )
        metrics["fcf_to_net_income_unavailable_reason"] = (
            (
                "no_recent_free_cash_flow_reported"
                if free_cash_flow is None
                and (
                    symbol in self._get_no_recent_free_cash_flow_symbols()
                    or symbol in self._get_never_tagged_free_cash_flow_symbols()
                )
                # Label-only, no value recomputed.
                else "free_cash_flow_absent_from_anchor_year"
                if free_cash_flow is None and symbol in self._get_free_cash_flow_available_elsewhere_symbols()
                # fcf_to_net_income = free_cash_flow / net_income - check the net_income
                # denominator too, not just the FCF numerator.
                else "net_income_not_reported"
                if net_income is None
                and (
                    symbol in self._get_no_recent_net_income_symbols()
                    or symbol in self._get_never_tagged_net_income_symbols()
                )
                else "net_income_absent_from_anchor_year"
                if net_income is None and symbol in self._get_net_income_available_elsewhere_symbols()
                else "missing_sec_data"
            )
            if "fcf_to_net_income" in failed_metrics
            else None
        )
        metrics["ocf_to_net_income_unavailable_reason"] = (
            (
                "no_recent_operating_cash_flow_reported"
                if operating_cash_flow is None and symbol in self._get_no_recent_operating_cash_flow_symbols()
                # Label-only, no value recomputed.
                else "operating_cash_flow_absent_from_anchor_year"
                if operating_cash_flow is None and symbol in self._get_operating_cash_flow_available_elsewhere_symbols()
                # ocf_to_net_income = operating_cash_flow / net_income - check the net_income
                # denominator too, not just the OCF numerator.
                else "net_income_not_reported"
                if net_income is None
                and (
                    symbol in self._get_no_recent_net_income_symbols()
                    or symbol in self._get_never_tagged_net_income_symbols()
                )
                else "net_income_absent_from_anchor_year"
                if net_income is None and symbol in self._get_net_income_available_elsewhere_symbols()
                else "missing_sec_data"
            )
            if "ocf_to_net_income" in failed_metrics
            else None
        )
        metrics["payout_ratio_unavailable_reason"] = payout_ratio_reason
        metrics["free_cash_flow_unavailable_reason"] = (
            (
                # Only covers the unambiguous "genuinely no FCF in the 3 most recent fiscal
                # years" case - the rest have FCF in an off-anchor year (see
                # _get_free_cash_flow_available_elsewhere_symbols() below).
                "no_recent_free_cash_flow_reported"
                if symbol in self._get_no_recent_free_cash_flow_symbols()
                or symbol in self._get_never_tagged_free_cash_flow_symbols()
                # Label-only, no value recomputed.
                else "free_cash_flow_absent_from_anchor_year"
                if symbol in self._get_free_cash_flow_available_elsewhere_symbols()
                else "missing_sec_data"
            )
            if "free_cash_flow" in failed_metrics
            else None
        )
        metrics["operating_cash_flow_unavailable_reason"] = (
            (
                # Only covers the unambiguous "genuinely no OCF in the 3 most recent fiscal
                # years" case - the rest have OCF in an off-anchor year (see
                # _get_operating_cash_flow_available_elsewhere_symbols() below).
                "no_recent_operating_cash_flow_reported"
                if symbol in self._get_no_recent_operating_cash_flow_symbols()
                # Label-only, no value recomputed.
                else "operating_cash_flow_absent_from_anchor_year"
                if symbol in self._get_operating_cash_flow_available_elsewhere_symbols()
                else "missing_sec_data"
            )
            if "operating_cash_flow" in failed_metrics
            else None
        )
        metrics["total_debt_unavailable_reason"] = (
            (
                "total_debt_not_itemized"
                if symbol in self._get_no_recent_debt_components_symbols()
                or symbol in self._get_never_tagged_debt_components_symbols()
                # total_debt_ev comes from the same ev_metrics tuple as total_cash_ev/
                # ebitda_ev below - reuse sec_valuations' own reason. Checked after the
                # debt-components gate above (largest, best-tested population).
                else "no_sec_valuations_row"
                if ev_metrics is None
                else sec_valuations_reason
                if sec_valuations_reason
                else "missing_sec_data"
            )
            if "total_debt" in failed_metrics
            else None
        )
        # total_cash_ev is None whenever sec_valuations has no row at all for this symbol,
        # or has a row but load_sec_valuations.py already recorded why total_cash came back
        # NULL there - reuse that reason. A genuinely never-tagged cash concept doesn't fail
        # the rest of the valuation row, so sec_valuations_reason can stay empty even then -
        # check cash_and_equivalents against its own no-data gate too.
        no_recent_cash_concept = (
            symbol in self._get_no_recent_cash_symbols() or symbol in self._get_never_tagged_cash_symbols()
        )
        metrics["total_cash_unavailable_reason"] = (
            (
                "no_sec_valuations_row"
                if ev_metrics is None
                else sec_valuations_reason
                if sec_valuations_reason
                else "no_recent_cash_reported"
                if no_recent_cash_concept
                else "missing_sec_data"
            )
            if "total_cash" in failed_metrics
            else None
        )
        metrics["cash_per_share_unavailable_reason"] = (
            (
                "shares_outstanding_unavailable"
                if cash_per_share_shares_missing
                else "no_sec_valuations_row"
                if ev_metrics is None
                else sec_valuations_reason
                if sec_valuations_reason
                else "no_recent_cash_reported"
                if no_recent_cash_concept
                else "missing_sec_data"
            )
            if "cash_per_share" in failed_metrics
            else None
        )
        metrics["ebitda_unavailable_reason"] = (
            (
                # ebitda is the same load_sec_valuations.py-derived absolute-dollar value
                # ebitda_margin's numerator uses - fails structurally for the same
                # REIT/tonnage-tax-exempt population.
                "reit_special_entity"
                if no_operating_income_concept
                # ebitda = OperatingIncome + D&A, so a real filer that never itemizes a
                # distinct operating income subtotal fails here too.
                else "operating_income_not_itemized"
                if symbol in self._get_no_recent_operating_income_symbols()
                or symbol in self._get_never_tagged_operating_income_symbols()
                # ebitda_ev comes from the same ev_metrics tuple as total_cash_ev - reuse the
                # sec_valuations `reason` column instead of a generic label.
                else "no_sec_valuations_row"
                if ev_metrics is None
                else sec_valuations_reason
                if sec_valuations_reason
                else "missing_sec_data"
            )
            if "ebitda" in failed_metrics
            else None
        )
        metrics["earnings_growth_yoy_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "earnings_growth_yoy" in implausible_ratio_metrics
                else "insufficient_prior_year_data"
            )
            if "earnings_growth_yoy" in failed_metrics
            else None
        )
        metrics["revenue_growth_yoy_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "revenue_growth_yoy" in implausible_ratio_metrics
                else "insufficient_prior_year_data"
            )
            if "revenue_growth_yoy" in failed_metrics
            else None
        )

    def _assign_quarterly_and_analyst_fallback_reasons(self, metrics: dict[str, Any]) -> None:
        """Generic fallback reasons for quarterly-derived and not-yet-implemented analyst
        fields - only fills in when a more specific reason wasn't already set (by
        `_compute_quarterly_metrics`, merged into `metrics` earlier). Identical to the
        original inline code.
        """
        # Quarterly metrics unavailable reasons (Session 78+). Only fill the generic
        # fallback when _compute_quarterly_metrics() (merged into `metrics` above) didn't
        # already set a more specific reason (e.g. "insufficient_eps_data",
        # "insufficient_revenue_data", "insufficient_eps_growth_datapoints",
        # "insufficient_quarterly_history") - this block previously overwrote every one of
        # those with the generic "insufficient_quarterly_data" unconditionally, silently
        # discarding the more specific diagnosis the moment it was computed.
        if metrics.get("consecutive_positive_quarters") is None and not metrics.get(
            "consecutive_positive_quarters_unavailable_reason"
        ):
            metrics["consecutive_positive_quarters_unavailable_reason"] = "insufficient_quarterly_data"
        if metrics.get("earnings_growth_4q_avg") is None and not metrics.get(
            "earnings_growth_4q_avg_unavailable_reason"
        ):
            metrics["earnings_growth_4q_avg_unavailable_reason"] = "insufficient_quarterly_data"
        if metrics.get("eps_growth_stability") is None and not metrics.get("eps_growth_stability_unavailable_reason"):
            metrics["eps_growth_stability_unavailable_reason"] = "insufficient_quarterly_data"
        if metrics.get("quarterly_growth_momentum") is None and not metrics.get(
            "quarterly_growth_momentum_unavailable_reason"
        ):
            metrics["quarterly_growth_momentum_unavailable_reason"] = "insufficient_quarterly_data"

        # Analyst metrics - not yet implemented. Guard all fields to avoid clobbering prior reasons.
        # _compute_quarterly_metrics() sets "insufficient_quarterly_history" for quarterly fields;
        # we must not override with "no_analyst_estimates" if that was already set.
        if metrics.get("earnings_surprise_avg") is None and not metrics.get("earnings_surprise_avg_unavailable_reason"):
            metrics["earnings_surprise_avg_unavailable_reason"] = "no_analyst_estimates"
        if metrics.get("earnings_beat_rate") is None and not metrics.get("earnings_beat_rate_unavailable_reason"):
            metrics["earnings_beat_rate_unavailable_reason"] = "no_analyst_estimates"
        if metrics.get("estimate_revision_direction") is None and not metrics.get(
            "estimate_revision_direction_unavailable_reason"
        ):
            metrics["estimate_revision_direction_unavailable_reason"] = "no_analyst_estimates"
        if metrics.get("revision_activity_30d") is None and not metrics.get("revision_activity_30d_unavailable_reason"):
            metrics["revision_activity_30d_unavailable_reason"] = "no_analyst_estimates"
        if metrics.get("estimate_momentum_60d") is None and not metrics.get("estimate_momentum_60d_unavailable_reason"):
            metrics["estimate_momentum_60d_unavailable_reason"] = "no_analyst_estimates"
        if metrics.get("estimate_momentum_90d") is None and not metrics.get("estimate_momentum_90d_unavailable_reason"):
            metrics["estimate_momentum_90d_unavailable_reason"] = "no_analyst_estimates"
        if metrics.get("revision_trend_score") is None and not metrics.get("revision_trend_score_unavailable_reason"):
            metrics["revision_trend_score_unavailable_reason"] = "no_analyst_estimates"

    def _recategorize_royalty_trust_reasons(self, symbol: str, metrics: dict[str, Any]) -> None:
        """Recategorize grantor trusts' structurally-absent debt/cash/interest/FCF-derived
        fields to "reit_special_entity" - identical to the original inline code.
        """
        # Recategorize debt/cash/interest/FCF-derived fields these grantor trusts
        # structurally never report to "reit_special_entity" (same label as their
        # current_ratio/quick_ratio/gross_margin siblings) - only when the field is None and
        # already carries one of the reasons this structural gap produces, so real data or
        # an unrelated reason is left untouched.
        if symbol in self._ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS:
            _trust_recategorize_fields = (
                "total_debt",
                "debt_to_equity",
                "debt_to_assets",
                "roic_pct",
                "roce_pct",
                "interest_coverage",
                "total_cash",
                "cash_per_share",
                "free_cash_flow",
                "operating_cash_flow",
                "fcf_to_net_income",
                "ocf_to_net_income",
                "accruals_ratio",
                "fcf_margin",
                "ebitda",
                "ebitda_margin",
                "operating_margin",
            )
            _trust_source_reasons = {
                "missing_sec_data",
                "total_debt_not_itemized",
                "no_recent_cash_reported",
                "interest_expense_not_itemized",
                "stockholders_equity_not_reported",
                "operating_income_not_itemized",
                "total_liabilities_not_reported",
            }
            for _field in _trust_recategorize_fields:
                _reason_key = f"{_field}_unavailable_reason"
                if metrics.get(_field) is None and metrics.get(_reason_key) in _trust_source_reasons:
                    metrics[_reason_key] = "reit_special_entity"
