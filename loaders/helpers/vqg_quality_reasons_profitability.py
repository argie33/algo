"""QualityReasonsProfitabilityMixin._apply_quality_profitability_reasons, split out of
vqg_quality_reasons.py (2026-09-10, file-size ratchet: a single ~925-line method would have
made that new file itself exceed the 800-line new-file cap - see .file-size-baseline.json /
.pre-commit-scripts/check_file_size_ratchet.py). Pure extraction, no behavior change: this is
the first half of what was one method - the raw-value writes and *_unavailable_reason chains
for gross_profitability/operating_profitability/accruals_ratio/margin_volatility/fcf_margin/
asset_turnover (the composite-score inputs) plus roe/roa/operating_margin/net_margin/
debt_to_equity/current_ratio/quick_ratio/interest_coverage. See
vqg_quality_reasons_valuation.py for the second half (debt_to_assets through the final
quality_score_unavailable_reason/debug-log).

Does NOT inherit SymbolGateMixin - same MRO conflict reasoning as QualityReasonsMixin's own
module docstring (QualityMetricsMixin already inherits both SymbolGateMixin AND this mixin
directly). Gate methods used here are declared TYPE_CHECKING-only.
"""

from typing import TYPE_CHECKING, Any


class QualityReasonsProfitabilityMixin:
    """See module docstring. Mixed into ValueQualityGrowthMetricsLoader alongside
    QualityMetricsMixin - every `self.` call here resolves normally through the instance.
    """

    if TYPE_CHECKING:

        def _get_blank_check_symbols(self) -> frozenset[str]: ...

        def _get_etf_trust_no_stockholders_equity_symbols(self) -> frozenset[str]: ...

        def _get_free_cash_flow_available_elsewhere_symbols(self) -> frozenset[str]: ...

        def _get_net_income_available_elsewhere_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_borrowed_debt_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_current_assets_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_current_liabilities_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_debt_components_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_free_cash_flow_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_net_income_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_operating_cash_flow_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_operating_income_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_revenue_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_stockholders_equity_symbols(self) -> frozenset[str]: ...

        def _get_never_tagged_total_assets_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_capex_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_current_assets_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_current_liabilities_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_debt_components_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_free_cash_flow_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_net_income_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_operating_cash_flow_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_operating_income_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_revenue_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_stockholders_equity_symbols(self) -> frozenset[str]: ...

        def _get_no_recent_total_assets_symbols(self) -> frozenset[str]: ...

        def _get_operating_cash_flow_available_elsewhere_symbols(self) -> frozenset[str]: ...

        def _get_operating_income_available_elsewhere_symbols(self) -> frozenset[str]: ...

        def _get_registered_investment_company_symbols(self) -> frozenset[str]: ...

        def _get_revenue_available_elsewhere_symbols(self) -> frozenset[str]: ...

    def _apply_quality_profitability_reasons(
        self,
        metrics: dict[str, Any],
        symbol: str,
        failed_metrics: list[str],
        implausible_ratio_metrics: list[str],
        gross_profitability: float | None,
        operating_profitability: float | None,
        accruals_ratio: float | None,
        margin_volatility: float | None,
        fcf_margin: float | None,
        asset_turnover: float | None,
        no_gross_profit_concept: bool,
        no_operating_income_concept: bool,
        operating_profitability_negative_equity: bool,
        operating_income_for_margin: float | None,
        stockholders_equity: float | None,
        total_assets: float | None,
        unclassified_balance_sheet: bool,
        current_assets: float | None,
        current_liabilities: float | None,
        no_recent_interest_expense: bool,
        no_operating_income_concept_ic: bool,
        interest_coverage_operating_income: float | None,
        debt_for_roic: float | None,
        net_income: float | None,
        revenue: float | None,
        operating_cash_flow: float | None,
        weighted_score: float | None,
    ) -> None:
        """Write the composite-score-input raw values plus roe/roa/operating_margin/
        net_margin/debt_to_equity/current_ratio/quick_ratio/interest_coverage reason fields.
        See module docstring for what's covered and why every parameter is a pure read.
        """
        metrics["gross_profitability"] = gross_profitability
        metrics["gross_profitability_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "gross_profitability" in implausible_ratio_metrics
                else "reit_special_entity"
                if no_gross_profit_concept
                else "no_revenue_reported"
                if symbol in self._get_blank_check_symbols()
                or symbol in self._get_no_recent_revenue_symbols()
                or symbol in self._get_never_tagged_revenue_symbols()
                else "no_recent_total_assets_reported"
                if (total_assets is None or total_assets <= 0)
                and (
                    symbol in self._get_no_recent_total_assets_symbols()
                    or symbol in self._get_never_tagged_total_assets_symbols()
                )
                else "missing_sec_data"
            )
            if gross_profitability is None
            else None
        )
        metrics["operating_profitability"] = operating_profitability
        metrics["operating_profitability_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "operating_profitability" in implausible_ratio_metrics
                else "negative_book_value"
                if operating_profitability_negative_equity
                else "reit_special_entity"
                if no_operating_income_concept
                # Label-only: the anchor year's income statement can lack operating_income
                # (and its EBIT fallback) even when the symbol reports it in other years.
                else "operating_income_absent_from_anchor_year"
                if operating_income_for_margin is None
                and symbol in self._get_operating_income_available_elsewhere_symbols()
                # operating_profitability_negative_equity only fires when stockholders_equity
                # is a real value <=0 - stays False (not caught) when equity is None.
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
            if operating_profitability is None
            else None
        )
        metrics["accruals_ratio"] = accruals_ratio
        metrics["accruals_ratio_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "accruals_ratio" in implausible_ratio_metrics
                # FIXED 2026-09-05 (goal: "SEC/XBRL missing data to zero" follow-up): a
                # registered investment company files a "Statement of Changes in Net
                # Assets" instead of a conventional cash-flow statement, leaving it with
                # ZERO fiscal_year>0 annual_cash_flow rows - too sparse to match
                # _get_no_recent_operating_cash_flow_symbols()'s own pattern. Live-confirmed
                # GGN (GAMCO Global Gold, Natural Resources & Income Trust). Checked first,
                # same priority as fcf_margin/fcf_yield's identical RIC check elsewhere.
                else "registered_investment_company_no_xbrl"
                if accruals_ratio is None and symbol in self._get_registered_investment_company_symbols()
                # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): same
                # ETF-trust sibling-wiring gap ocf_to_net_income/fcf_to_net_income already
                # closed (an ETF/commodity/currency trust files no cash-flow statement at
                # all, same as a RIC) - accruals_ratio shares operating_cash_flow as an
                # input but was never given the matching ETF check.
                else "etf_trust_no_gaap_financials"
                if operating_cash_flow is None and symbol in self._get_etf_trust_no_stockholders_equity_symbols()
                # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): OR in the
                # full-history sibling gate - see _get_never_tagged_operating_cash_flow_symbols()'s
                # docstring for why this was a real, unmirrored gap versus free_cash_flow's
                # own identical pair of gates.
                else "no_recent_operating_cash_flow_reported"
                if operating_cash_flow is None
                and (
                    symbol in self._get_no_recent_operating_cash_flow_symbols()
                    or symbol in self._get_never_tagged_operating_cash_flow_symbols()
                )
                # Label-only: operating_cash_flow is None because the anchor year's own
                # cash-flow row is unavailable, not because the symbol lacks real OCF.
                else "operating_cash_flow_absent_from_anchor_year"
                if operating_cash_flow is None and symbol in self._get_operating_cash_flow_available_elsewhere_symbols()
                else "no_recent_total_assets_reported"
                if (total_assets is None or total_assets <= 0)
                and (
                    symbol in self._get_no_recent_total_assets_symbols()
                    or symbol in self._get_never_tagged_total_assets_symbols()
                )
                # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): accruals_ratio
                # = (net_income - operating_cash_flow) / total_assets - the OCF numerator and
                # total_assets denominator were both already gated above, but the net_income
                # numerator never was, so a symbol with real net_income missing only for this
                # anchor year (or never tagged at all) fell straight to the generic fallback.
                # Same fcf_to_net_income/ocf_to_net_income sibling gate pair just above in this
                # file.
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
            if accruals_ratio is None
            else None
        )
        metrics["margin_volatility"] = margin_volatility
        metrics["margin_volatility_unavailable_reason"] = "insufficient_history" if margin_volatility is None else None
        # Gate on `X is None` directly (not `"X" in failed_metrics`) - the compute blocks
        # above don't append fcf_margin/asset_turnover to failed_metrics when inputs are
        # merely missing (only when the |ratio|>1000 bound fires), so gating on
        # failed_metrics left many rows with a NULL value and no reason recorded.
        metrics["fcf_margin"] = fcf_margin
        metrics["fcf_margin_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "fcf_margin" in implausible_ratio_metrics
                # Closed-end funds/investment trusts file no cash-flow statement at all
                # (see _get_registered_investment_company_symbols' docstring) - checked
                # before the generic never-tagged-FCF gate below so this more specific,
                # correctly-categorized ("Legitimate / not applicable") reason wins.
                else "registered_investment_company_no_xbrl"
                if symbol in self._get_registered_investment_company_symbols()
                # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): fcf_yield's
                # own reason chain (vqg_value.py) already checks
                # _get_etf_trust_no_stockholders_equity_symbols() alongside the RIC gate;
                # fcf_margin's sibling chain here never did, despite ETF/commodity/currency
                # trusts (FXY, AAAU, GLDM, GBTC, ETHE, BITB/BITW, CANE/CORN/SOYB/WEAT/TAGS/
                # USCI, ...) filing no cash-flow statement at all for the identical reason a
                # RIC doesn't. Live-confirmed 32 universe symbols mislabeled
                # capex_never_tagged_in_recent_filings/no_recent_free_cash_flow_reported/
                # no_revenue_reported instead of this correctly-categorized
                # ("Legitimate / not applicable") reason.
                else "etf_trust_no_gaap_financials"
                if symbol in self._get_etf_trust_no_stockholders_equity_symbols()
                # ADDED 2026-09-05: fcf_yield's own reason chain already checks this gate;
                # fcf_margin's sibling chain here never did (AIG-verified: real OCF every
                # year, capex-shaped concept stops after FY2023, not PPE-delta-recoverable
                # since AIG never tags depreciation either).
                else "capex_never_tagged_in_recent_filings"
                if symbol in self._get_no_recent_capex_symbols()
                # fcf_margin's own cross-year fallback (fcf_margin_free_cash_flow/
                # fcf_margin_revenue above) already looks past the anchor row, so a
                # remaining None here means both inputs are genuinely absent across recent
                # fiscal years, not just off the anchor.
                else "no_recent_free_cash_flow_reported"
                if symbol in self._get_no_recent_free_cash_flow_symbols()
                or symbol in self._get_never_tagged_free_cash_flow_symbols()
                else "no_revenue_reported"
                if symbol in self._get_no_recent_revenue_symbols() or symbol in self._get_never_tagged_revenue_symbols()
                # A real free_cash_flow value exists somewhere in the symbol's history but
                # not in the same fiscal year as a real revenue value (the cross-year
                # fallback above requires both in the SAME year) - live-confirmed FTW/OBX/
                # AADX/AVEX/ALLO. Same reason free_cash_flow_unavailable_reason already
                # uses for this exact gate above - label-only, no value recomputed.
                else "free_cash_flow_absent_from_anchor_year"
                if symbol in self._get_free_cash_flow_available_elsewhere_symbols()
                else "missing_sec_data"
            )
            if fcf_margin is None
            else None
        )
        metrics["asset_turnover"] = asset_turnover
        metrics["asset_turnover_unavailable_reason"] = (
            (
                "implausible_ratio"
                if "asset_turnover" in implausible_ratio_metrics
                else "no_revenue_reported"
                if symbol in self._get_no_recent_revenue_symbols() or symbol in self._get_never_tagged_revenue_symbols()
                else "no_recent_total_assets_reported"
                if (total_assets is None or total_assets <= 0)
                and (
                    symbol in self._get_no_recent_total_assets_symbols()
                    or symbol in self._get_never_tagged_total_assets_symbols()
                )
                # Label-only: revenue is None because the balance-sheet anchor year's own
                # income-statement row is unavailable, not because the symbol lacks real
                # revenue - the windowed gate above already ruled that out.
                else "revenue_absent_from_anchor_year"
                if revenue is None and symbol in self._get_revenue_available_elsewhere_symbols()
                else "missing_sec_data"
            )
            if asset_turnover is None
            else None
        )

        # An unprofitable company still has a real, computed quality score (0,
        # after clamping) - that's honest data, not missing data. Do not mark
        # data_unavailable just because every component came out <= 0.
        if weighted_score is not None:
            metrics["quality_score"] = float(min(100.0, max(0.0, weighted_score)))

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
                if (total_assets is None or total_assets <= 0)
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
                # FIXED 2026-09-07 (goal: "SEC/XBRL missing data to zero" sweep): physical
                # commodity/currency/crypto trusts (BTC/ETH/XRP/GSOL/BSOL-class, see
                # _get_etf_trust_no_stockholders_equity_symbols()'s own docstring) file a
                # "Statement of Assets and Liabilities" with no current/non-current split
                # at all - same structural fact as that gate's own stockholders_equity
                # case, just never checked here. Live-confirmed: BTC/ETH/XRP/GSOL/BSOL and
                # 9 more universe symbols have real annual_balance_sheet history (proving
                # they're established filers) but zero current_assets ever, landing on the
                # generic "no_recent_current_assets_reported" ("Missing SEC/XBRL data")
                # instead of the correct "Legitimate / not applicable" fact. Checked before
                # the generic never-tagged-current-assets gate below, same priority as the
                # ETF-trust check already established for every other metric's chain in
                # this file.
                else "etf_trust_no_gaap_financials"
                if current_assets is None and symbol in self._get_etf_trust_no_stockholders_equity_symbols()
                else "registered_investment_company_no_xbrl"
                if current_assets is None and symbol in self._get_registered_investment_company_symbols()
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
                # Same ETF-trust/RIC fix as current_ratio's identical chain just above -
                # quick_ratio shares current_ratio's structural inputs.
                else "etf_trust_no_gaap_financials"
                if current_assets is None and symbol in self._get_etf_trust_no_stockholders_equity_symbols()
                else "registered_investment_company_no_xbrl"
                if current_assets is None and symbol in self._get_registered_investment_company_symbols()
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
                # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): interest
                # coverage is mathematically undefined - not missing - for a symbol
                # double-confirmed structurally debt-free (never tagged ANY debt component
                # across full balance-sheet history AND never reports nonzero
                # interest_expense - the same evidentiary bar total_debt's own zero-coercion
                # just above uses). Unlike total_debt (a real 0), operating_income/0 has no
                # meaningful value, so this gets its own "Legitimate / not applicable" reason
                # instead of a coerced number - same "mathematically undefined for real
                # business reasons, not a data gap" class as no_revenue_reported/
                # unprofitable_stock/negative_enterprise_value.
                else "no_debt_no_interest_expense"
                if no_recent_interest_expense
                and (
                    symbol in self._get_never_tagged_debt_components_symbols()
                    # FIXED 2026-09-06 (same sweep, see
                    # _get_never_tagged_borrowed_debt_symbols()'s docstring): a company with
                    # only operating/finance lease liabilities and zero borrowed debt never
                    # tags an InterestExpense concept either - lease liabilities don't
                    # generate a separately-disclosed interest fact the way borrowed debt
                    # does, so the stricter all-four-components gate above was wrongly
                    # excluding these from the "Legitimate / not applicable" reason.
                    or symbol in self._get_never_tagged_borrowed_debt_symbols()
                )
                else "interest_expense_not_itemized"
                if no_recent_interest_expense
                else "reit_special_entity"
                if no_operating_income_concept_ic
                # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): same
                # sibling gate operating_profitability/operating_margin already have for
                # operating_income_for_margin - interest_coverage_operating_income is the
                # same EBIT-fallback-aware value, just computed separately for this field
                # (see its own comment above), and was never given the matching anchor-year
                # check. Label-only: the anchor year's income statement can lack operating
                # income (and its EBIT fallback) even when the symbol reports it elsewhere.
                else "operating_income_absent_from_anchor_year"
                if interest_coverage_operating_income is None
                and symbol in self._get_operating_income_available_elsewhere_symbols()
                else "operating_income_not_itemized"
                if symbol in self._get_no_recent_operating_income_symbols()
                or symbol in self._get_never_tagged_operating_income_symbols()
                else "missing_sec_data"
            )
            if "interest_coverage" in failed_metrics
            else None
        )
