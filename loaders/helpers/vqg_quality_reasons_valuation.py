"""QualityReasonsValuationMixin._apply_quality_valuation_reasons, split out of
vqg_quality_reasons.py (2026-09-10, file-size ratchet: a single ~925-line method would have
made that new file itself exceed the 800-line new-file cap - see .file-size-baseline.json /
.pre-commit-scripts/check_file_size_ratchet.py). Pure extraction, no behavior change: this is
the second half of what was one method - debt_to_assets/gross_margin/ebitda_margin/roic_pct/
roce_pct/fcf_to_net_income/ocf_to_net_income/payout_ratio/free_cash_flow/operating_cash_flow/
total_debt/total_cash/cash_per_share/ebitda/earnings_growth_yoy/revenue_growth_yoy reason
chains, plus the quarterly/analyst generic-reason fallbacks and the final
quality_score_unavailable_reason/debug-log. See vqg_quality_reasons_profitability.py for the
first half (the composite-score raw values through interest_coverage).

Does NOT inherit SymbolGateMixin - same MRO conflict reasoning as QualityReasonsMixin's own
module docstring (QualityMetricsMixin already inherits both SymbolGateMixin AND this mixin
directly). Gate methods used here are declared TYPE_CHECKING-only.
"""

import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger("loaders.load_value_quality_growth_metrics")


class QualityReasonsValuationMixin:
    """See module docstring. Mixed into ValueQualityGrowthMetricsLoader alongside
    QualityMetricsMixin - every `self.` call here resolves normally through the instance.
    """

    if TYPE_CHECKING:

        def _get_blank_check_symbols(self) -> frozenset[str]: ...

        def _get_etf_symbols(self) -> frozenset[str]: ...

        def _get_etf_trust_no_stockholders_equity_symbols(self) -> frozenset[str]: ...

        def _get_free_cash_flow_available_elsewhere_symbols(self) -> frozenset[str]: ...

        def _get_net_income_available_elsewhere_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_borrowed_debt_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_cash_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_debt_components_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_free_cash_flow_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_net_income_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_operating_cash_flow_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_operating_income_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_revenue_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_stockholders_equity_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_total_assets_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_total_liabilities_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_capex_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_cash_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_debt_components_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_free_cash_flow_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_net_income_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_operating_cash_flow_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_operating_income_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_revenue_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_stockholders_equity_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_total_assets_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_total_liabilities_symbols(self) -> frozenset[str]: ...

        def _get_operating_cash_flow_available_elsewhere_symbols(self) -> frozenset[str]: ...

        def _get_operating_income_available_elsewhere_symbols(self) -> frozenset[str]: ...

        def _get_registered_investment_company_symbols(self) -> frozenset[str]: ...

        def _get_revenue_available_elsewhere_symbols(self) -> frozenset[str]: ...

    def _apply_quality_valuation_reasons(
        self,
        metrics: dict[str, Any],
        symbol: str,
        ev_metrics: Any,
        sec_valuations_reason: str | None,
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
        payout_ratio_reason: str | None,
        no_gross_profit_concept: bool,
        no_operating_income_concept: bool,
        operating_income_for_margin: float | None,
        stockholders_equity: float | None,
        total_assets: float | None,
        total_liabilities: float | None,
        cash_per_share_shares_missing: bool,
        roic_pct_unprofitable: bool,
        roic_pct_negative_invested_capital: bool,
        no_operating_income_concept_roic: bool,
        debt_for_roic: float | None,
        roce_pct_negative_capital_employed: bool,
        net_income: float | None,
        revenue: float | None,
        free_cash_flow: float | None,
        operating_cash_flow: float | None,
        weighted_score: float | None,
        available_quality_weight: float,
        min_quality_weight_pct: float,
    ) -> None:
        """Write the debt_to_assets-through-revenue_growth_yoy reason fields, the quarterly/
        analyst generic-reason fallbacks, and the final quality_score_unavailable_reason/
        debug-log. See module docstring for what's covered and why every parameter is a pure
        read.
        """
        metrics["debt_to_assets_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "debt_to_assets" in implausible_ratio_metrics
                else "no_recent_total_assets_reported"
                if (total_assets is None or total_assets <= 0)
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
                # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): same
                # sibling gate operating_profitability/operating_margin already have for
                # operating_income_for_margin - ebitda_margin shares that exact variable
                # (EBITDA = OperatingIncome + D&A) but was never given the matching
                # anchor-year check. Label-only, no value recomputed.
                else "operating_income_absent_from_anchor_year"
                if operating_income_for_margin is None
                and symbol in self._get_operating_income_available_elsewhere_symbols()
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
                "implausible_ratio"
                if "fcf_to_net_income" in implausible_ratio_metrics
                # See fcf_margin_unavailable_reason above for why this check comes first.
                else "registered_investment_company_no_xbrl"
                if free_cash_flow is None and symbol in self._get_registered_investment_company_symbols()
                # FIXED 2026-09-06: same fcf_margin sibling-wiring gap, ETF-trust side.
                else "etf_trust_no_gaap_financials"
                if free_cash_flow is None and symbol in self._get_etf_trust_no_stockholders_equity_symbols()
                # ADDED 2026-09-05: same sibling-wiring gap as fcf_margin above.
                else "capex_never_tagged_in_recent_filings"
                if free_cash_flow is None and symbol in self._get_no_recent_capex_symbols()
                else "no_recent_free_cash_flow_reported"
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
                "implausible_ratio"
                if "ocf_to_net_income" in implausible_ratio_metrics
                # Same RIC gap as accruals_ratio_unavailable_reason above. Live-confirmed
                # 14 universe symbols (IGI/TY/ASA/GAM/GGN/GGT/GLU/PIM/PMM/GNT/HQH/PPT/NXP/
                # SOR).
                else "registered_investment_company_no_xbrl"
                if operating_cash_flow is None and symbol in self._get_registered_investment_company_symbols()
                # FIXED 2026-09-06: same fcf_margin sibling-wiring gap, ETF-trust side -
                # ETF/commodity/currency trusts file no cash-flow statement, same as a RIC.
                else "etf_trust_no_gaap_financials"
                if operating_cash_flow is None and symbol in self._get_etf_trust_no_stockholders_equity_symbols()
                # FIXED 2026-09-06: OR in the full-history sibling gate, same fix as
                # accruals_ratio_unavailable_reason above.
                else "no_recent_operating_cash_flow_reported"
                if operating_cash_flow is None
                and (
                    symbol in self._get_no_recent_operating_cash_flow_symbols()
                    or symbol in self._get_never_tagged_operating_cash_flow_symbols()
                )
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
                # See fcf_margin_unavailable_reason above for why this check comes first.
                "registered_investment_company_no_xbrl"
                if symbol in self._get_registered_investment_company_symbols()
                # FIXED 2026-09-06: same fcf_margin sibling-wiring gap, ETF-trust side.
                else "etf_trust_no_gaap_financials"
                if symbol in self._get_etf_trust_no_stockholders_equity_symbols()
                # ADDED 2026-09-05: same sibling-wiring gap as fcf_margin above.
                else "capex_never_tagged_in_recent_filings"
                if symbol in self._get_no_recent_capex_symbols()
                # Only covers the unambiguous "genuinely no FCF in the 3 most recent fiscal
                # years" case - the rest have FCF in an off-anchor year (see
                # _get_free_cash_flow_available_elsewhere_symbols() below).
                else "no_recent_free_cash_flow_reported"
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
                # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): same
                # fcf_margin/ocf_to_net_income sibling-wiring gap - this chain never checked
                # RIC/ETF-trust at all (both file no cash-flow statement whatsoever).
                "registered_investment_company_no_xbrl"
                if symbol in self._get_registered_investment_company_symbols()
                else "etf_trust_no_gaap_financials"
                if symbol in self._get_etf_trust_no_stockholders_equity_symbols()
                # FIXED 2026-09-06: OR in the full-history sibling gate (recent IPOs/SPAC-
                # mergers too thin for the windowed gate's 3-year requirement but genuinely
                # never tagging OCF) - the rest still have OCF in an off-anchor year (see
                # _get_operating_cash_flow_available_elsewhere_symbols() below).
                else "no_recent_operating_cash_flow_reported"
                if symbol in self._get_no_recent_operating_cash_flow_symbols()
                or symbol in self._get_never_tagged_operating_cash_flow_symbols()
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
                # ADDED 2026-09-05 (goal: "SEC/XBRL missing data to zero" follow-up):
                # etf_symbols tickers with ZERO annual_balance_sheet rows ever (SPY/IGV/
                # BKDV live-confirmed) fall through every check above - they have no
                # sec_valuations row's own reason to inherit AND no real balance-sheet
                # history to even attempt the debt-components gate against. Unlike
                # _get_etf_trust_no_stockholders_equity_symbols() (which requires real
                # balance-sheet history to distinguish "weird trust filing shape" from
                # "too new to have filed yet"), an ETF's total_debt/total_cash absence
                # doesn't depend on listing age at all - a UIT/index-tracking ETF never
                # files an operating-company-style GAAP balance sheet regardless of how
                # long it's been trading (SPY: listed 1993, zero balance-sheet rows,
                # obviously not "too new"). etf_symbols membership alone is sufficient.
                else "etf_trust_no_gaap_financials"
                if symbol in self._get_etf_symbols()
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
                # Same etf_symbols fallback as total_debt_unavailable_reason above - same
                # root fact (no GAAP balance sheet at all), same 3 live-confirmed symbols
                # (SPY/IGV/BKDV).
                else "etf_trust_no_gaap_financials"
                if symbol in self._get_etf_symbols()
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
                # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): same
                # sibling gate operating_profitability/operating_margin/ebitda_margin
                # already have for operating_income_for_margin - ebitda shares that exact
                # variable (EBITDA = OperatingIncome + D&A) but was never given the
                # matching anchor-year check. Label-only, no value recomputed.
                else "operating_income_absent_from_anchor_year"
                if operating_income_for_margin is None
                and symbol in self._get_operating_income_available_elsewhere_symbols()
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

        # Score can be partial; only mark unavailable if ALL metrics failed OR the
        # available weight didn't clear the completeness floor above (thin-sample
        # extrapolation, not honest partial data - see quality_components' own comment).
        if weighted_score is None and available_quality_weight < min_quality_weight_pct:
            metrics["quality_score_unavailable_reason"] = "insufficient_completeness"
        else:
            metrics["quality_score_unavailable_reason"] = None

        if failed_metrics:
            # Log which metrics are incomplete (for debugging), but don't mark data_unavailable
            logger.debug(
                f"[VALUE_QUALITY_GROWTH] {symbol}: Quality metrics computed from available data. "
                f"Unavailable: {', '.join(sorted(set(failed_metrics)))} (insufficient SEC data)"
            )
