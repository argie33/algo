"""QualityRecategorizeMixin, extracted from vqg_quality.py (2026-09-09, file-size ratchet:
that file is past the hard ceiling - see .file-size-baseline.json /
.pre-commit-scripts/check_file_size_ratchet.py). Pure extraction, no behavior change: these
two methods are the royalty-trust/ETF-trust/RIC/blank-check/unsupported-currency
"recategorize a generic missing_sec_data-class reason to the correct structural one" loops
that used to live inline in _compute_quality_metrics, split into a "pre" half (run before
_apply_structural_entity_type_exemption_reasons) and a "post" half (run after it) purely so
that call's own literal call-site line stays inside _compute_quality_metrics's own source -
see test_quality_metrics_structural_entity_type_exemption_gate_wired_20260907.py's
test_wired_into_compute_quality_metrics_caller_site, which asserts on that exact string via
inspect.getsource(QualityMetricsMixin._compute_quality_metrics). Both methods take and mutate
the `metrics` dict in place, identical to how this code behaved inline.
"""

from typing import TYPE_CHECKING, Any

from loaders.helpers.vqg_shared import recategorize_balance_sheet_currency_fields


class QualityRecategorizeMixin:
    """See module docstring. Mixed into ValueQualityGrowthMetricsLoader alongside
    QualityMetricsMixin - every `self.` call here resolves normally through the instance.
    """

    if TYPE_CHECKING:
        _ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS: frozenset[str]

        def _get_etf_trust_no_stockholders_equity_symbols(self) -> frozenset[str]: ...

        def _get_registered_investment_company_symbols(self) -> frozenset[str]: ...

        def _get_blank_check_symbols(self) -> frozenset[str]: ...

        def _get_unsupported_currency_ocf_symbols(self) -> frozenset[str]: ...

        def _get_unsupported_currency_balance_sheet_symbols(self) -> frozenset[str]: ...

    def _apply_quality_recategorize_reasons_pre(self, metrics: dict[str, Any], symbol: str) -> None:
        """Royalty-trust / ETF-trust / registered-investment-company recategorize loops - run
        BEFORE _apply_structural_entity_type_exemption_reasons() in _compute_quality_metrics.
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
                # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day
                # follow-up to the sibling RIC-loop fix above): these 8 fields share the
                # identical "falls back to a reason already in _trust_source_reasons"
                # shape as the fields already listed above, mirroring the RIC
                # recategorization loop's own extension just above this block. Guarded the
                # same way (only fires when the field is still None AND its reason matches),
                # so this is a no-op for any of these that already resolve via a different
                # path (e.g. current_ratio/quick_ratio/gross_margin's own
                # unclassified_balance_sheet check, referenced in this block's header
                # comment) - purely additive coverage for whichever royalty-trust symbols
                # don't take that other path.
                "payout_ratio",
                "gross_profitability",
                "asset_turnover",
                "roa",
                "net_margin",
                "current_ratio",
                "quick_ratio",
                "gross_margin",
            )
            # FIXED 2026-09-10 (goal: "under 500" missing-XBRL push, same bug found in the
            # sibling RIC/ETF-trust/blank-check loops below - each already includes
            # "capex_never_tagged_in_recent_filings" here, this one never did): a royalty
            # trust's "Statement of Assets and Liabilities" has no CapitalExpenditures
            # concept either (same structural fact as its debt/cash/interest gaps), so
            # fcf_margin/fcf_to_net_income/free_cash_flow (all members of
            # _trust_recategorize_fields above) legitimately hit
            # _get_no_recent_capex_symbols() and were landing on "Missing SEC/XBRL data"
            # instead of this loop's intended "reit_special_entity".
            _trust_source_reasons = {
                "missing_sec_data",
                "total_debt_not_itemized",
                "no_recent_cash_reported",
                "interest_expense_not_itemized",
                "stockholders_equity_not_reported",
                "operating_income_not_itemized",
                "total_liabilities_not_reported",
                "capex_never_tagged_in_recent_filings",
                # FIXED 2026-09-10 (goal: "SEC/XBRL missing data to zero" sweep, under-500
                # push): live-confirmed NRT (Oil Royalty Traders, a member of this exact
                # royalty-trust set) stuck on "no_recent_free_cash_flow_reported" for
                # fcf_margin/free_cash_flow - fcf_margin's own reason chain
                # (vqg_quality_reasons_profitability.py) resolves to this specific reason
                # before ever reaching the generic "missing_sec_data" fallback this loop's
                # source-reason set was built around, so the recategorization never fired
                # for this population's fcf_margin/free_cash_flow fields even though they're
                # both in _trust_recategorize_fields above.
                "no_recent_free_cash_flow_reported",
            }
            for _field in _trust_recategorize_fields:
                _reason_key = f"{_field}_unavailable_reason"
                if metrics.get(_field) is None and metrics.get(_reason_key) in _trust_source_reasons:
                    metrics[_reason_key] = "reit_special_entity"

        # Same recategorization pattern as the royalty-trust block above, for physical
        # commodity/currency/crypto trusts (see _get_etf_trust_no_stockholders_equity_
        # symbols' own docstring - GLDM/USO/UNG/FXA/GBTC-class tickers). ADDED 2026-09-05
        # (goal: "SEC/XBRL missing data to zero" sweep, follow-up to the same day's
        # etf_trust_no_gaap_financials fix): that fix only wired the ETF-trust gate into
        # this function's single "ALL metrics null" early return - live-confirmed via a
        # scoped rerun of the 43 real etf_symbols matching this gate that most (38/43)
        # never hit that early return at all (some other field, e.g. current_ratio,
        # legitimately computes for a Statement-of-Assets-and-Liabilities filer even
        # without stockholders_equity) and fell through to this function's normal per-field
        # `stockholders_equity_not_reported` ternary branches instead (roe/roa/debt_to_
        # equity/roic_pct/roce_pct/sustainable_growth_rate all check that reason before ever
        # reaching the ETF-specific gate) - the exact same "fix wired into only one of
        # several call sites" bug class as the royalty-trust block's own reason set.
        # roa is excluded: it never reaches stockholders_equity_not_reported (gated on
        # total_assets instead, which these trusts DO report).
        if symbol in self._get_etf_trust_no_stockholders_equity_symbols():
            _etf_trust_recategorize_fields = (
                "operating_profitability",
                "roe",
                "debt_to_equity",
                "roic_pct",
                "roce_pct",
                "sustainable_growth_rate",
            )
            for _field in _etf_trust_recategorize_fields:
                _reason_key = f"{_field}_unavailable_reason"
                if metrics.get(_field) is None and metrics.get(_reason_key) == "stockholders_equity_not_reported":
                    metrics[_reason_key] = "etf_trust_no_gaap_financials"
            # total_debt's own ternary chain (unlike the fields above) is gated on debt
            # concepts, not stockholders_equity, so it never lands on
            # "stockholders_equity_not_reported" - it falls to the broader "missing_sec_data"/
            # "total_debt_not_itemized" reasons instead (same reasons the RIC block below
            # reuses for the same field). ADDED 2026-09-06 (goal: "SEC/XBRL missing data to
            # zero" sweep) - live-confirmed GLDM (SPDR Gold MiniShares Trust) has no
            # total_debt concept at all (a physical-commodity trust holds gold, not debt)
            # and was falling to generic "missing_sec_data".
            if metrics.get("total_debt") is None and metrics.get("total_debt_unavailable_reason") in (
                "missing_sec_data",
                "total_debt_not_itemized",
            ):
                metrics["total_debt_unavailable_reason"] = "etf_trust_no_gaap_financials"

            # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day
            # follow-up): the narrow loop above only catches "stockholders_equity_not_
            # reported" for its 6 fields - but a physical/commodity/currency trust (GLD/
            # GLDM/GBTC/ETHE/BITB/the FX*-class currency trusts/the commodity-pool ETFs)
            # files ONLY total_assets/total_liabilities (see this gate's own docstring), so
            # every field below this comment structurally has no revenue/net_income/
            # operating_income/debt/cash/interest-expense concept to tag either, the exact
            # same "Statement of Assets and Liabilities" shape the RIC/royalty-trust blocks
            # already handle with their own broader reason set - just never extended to this
            # population. Reusing the identical reason set (not a new name) since the
            # underlying SEC filing gap is the same across all three trust/fund shapes.
            _etf_trust_broad_recategorize_fields = (
                "payout_ratio",
                "gross_profitability",
                "asset_turnover",
                "roa",
                "operating_margin",
                "net_margin",
                "current_ratio",
                "quick_ratio",
                "interest_coverage",
                "debt_to_assets",
                "gross_margin",
                "ebitda_margin",
                "accruals_ratio",
                "total_cash",
                "cash_per_share",
                "ebitda",
                # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day
                # follow-up): fcf_margin/fcf_to_net_income were never added to this loop,
                # unlike the sibling royalty-trust block below (which already includes
                # both) - a physical commodity/currency trust has no CapitalExpenditures
                # concept either (it holds bullion/currency/crypto, not PP&E), so
                # free_cash_flow's capex dependency fails the same "no such concept exists"
                # way total_cash/interest_coverage/etc already correctly recategorize.
                # Live-confirmed BITW/GLDM/TAGS/WEAT stuck on "capex_never_tagged_in_recent_
                # filings" (Missing SEC/XBRL data) instead of "etf_trust_no_gaap_financials"
                # (Legitimate / not applicable).
                "fcf_margin",
                "fcf_to_net_income",
            )
            _etf_trust_broad_source_reasons = {
                "missing_sec_data",
                "total_debt_not_itemized",
                "no_recent_cash_reported",
                "interest_expense_not_itemized",
                "stockholders_equity_not_reported",
                "operating_income_not_itemized",
                "total_liabilities_not_reported",
                # ADDED 2026-09-06 (same fix as above): the reason fcf_margin/
                # fcf_to_net_income actually carry for this population - see the fields
                # tuple's own comment just above.
                "capex_never_tagged_in_recent_filings",
            }
            for _field in _etf_trust_broad_recategorize_fields:
                _reason_key = f"{_field}_unavailable_reason"
                if metrics.get(_field) is None and metrics.get(_reason_key) in _etf_trust_broad_source_reasons:
                    metrics[_reason_key] = "etf_trust_no_gaap_financials"

        # Same recategorization pattern as the ETF-trust block above, for registered
        # investment companies (closed-end funds/investment trusts - same root fact
        # already established for fcf_margin/fcf_yield/accruals_ratio/ocf_to_net_income
        # elsewhere in this file: a "Statement of Changes in Net Assets" has no
        # stockholders_equity/total_debt concepts to tag at all). ADDED 2026-09-05 (goal:
        # "SEC/XBRL missing data to zero" follow-up): roic_pct/debt_to_equity's own ternary
        # chains never reach a specific reason for a RIC either - live-confirmed GGN (GAMCO
        # Global Gold, Natural Resources & Income Trust): roe computes a real value (its
        # denominator, stockholders_equity, IS available), but roic_pct/debt_to_equity
        # (which also need debt_for_roic, structurally absent) fell all the way through to
        # generic "missing_sec_data" - broader than the ETF-trust block's single
        # "stockholders_equity_not_reported" check, reusing the royalty-trust block's wider
        # source-reason set (which already includes "missing_sec_data", mirroring the
        # royalty-trust block's own _trust_source_reasons above - NOT reused directly since
        # that name is only defined inside the royalty-trust `if`, a scope this RIC check
        # doesn't share) since a RIC can hit any of several different missing-denominator
        # reasons depending on which concept it happens to lack first.
        if symbol in self._get_registered_investment_company_symbols():
            # Not reusing _etf_trust_recategorize_fields above - that name is only defined
            # inside the ETF-trust `if`, a scope this RIC check doesn't share (a RIC that
            # isn't ALSO an etf_symbols-registered ticker, GGN's case, would otherwise hit
            # an UnboundLocalError here).
            _ric_recategorize_fields = (
                "operating_profitability",
                "roe",
                "debt_to_equity",
                "roic_pct",
                "roce_pct",
                "sustainable_growth_rate",
                # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep):
                # total_debt's own ternary chain never had a RIC check at all, unlike its
                # roic_pct/roce_pct/debt_to_equity dependents above - live-confirmed 82
                # active-universe RIC symbols (GGN, BLW, BGY and siblings) report
                # "total_debt_not_itemized" for the same structural "no debt concept in a
                # Statement of Changes in Net Assets" fact already recategorized for those
                # dependents.
                "total_debt",
                # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day
                # follow-up): interest_coverage's own ternary chain (~line 2522) can produce
                # "interest_expense_not_itemized" for a RIC (no interest-expense concept in
                # a Statement of Changes in Net Assets), and that reason was already listed
                # in _ric_source_reasons below as something this loop should catch - but
                # "interest_coverage" itself was never added to this recategorize-fields
                # tuple, so the catch never fired. The sibling royalty-trust block just
                # above (_trust_recategorize_fields) already includes "interest_coverage" -
                # this was a half-wired fix, not a deliberate omission. Live-confirmed 7
                # active-universe RIC symbols stuck on the generic reason.
                "interest_coverage",
                # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day
                # follow-up): total_cash/cash_per_share are also RIC-structural gaps (no
                # cash concept distinct from portfolio holdings in a Statement of Changes
                # in Net Assets) but were never added to this loop either, unlike the
                # sibling royalty-trust block above (which already includes "total_cash"/
                # "cash_per_share"). Live-confirmed 6 active-universe RIC symbols (BGR,
                # BHV, BKT, BMN, BTT, IIM) stuck on "missing_sec_data"/"no_recent_cash_
                # reported" - both already listed in _ric_source_reasons below.
                "total_cash",
                "cash_per_share",
                # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day
                # follow-up): 12 more fields share the identical "no more specific gate
                # matched, fell to the generic missing_sec_data fallback" shape for a RIC as
                # the fields already listed above - live-confirmed via a full scan of every
                # `else "missing_sec_data"` ternary branch in this function against this
                # exact RIC population (GGN/BLW/BGY/BDJ/BUI/BGR/BIT/BGT/IGI/BST/VLT/VPV/VTN/
                # VVR/VCV/VGM/VKI/VKQ/BBN/BTZ/EFT/EOT/EVF and siblings): each of these was
                # never added to this loop despite its own reason already being a member of
                # _ric_source_reasons below, the same half-wired-fix pattern as total_cash/
                # cash_per_share/interest_coverage above.
                "payout_ratio",
                "ebitda_margin",
                "gross_profitability",
                "asset_turnover",
                "roa",
                "operating_margin",
                "net_margin",
                "current_ratio",
                "quick_ratio",
                "debt_to_assets",
                "gross_margin",
                "ebitda",
                # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day
                # follow-up): the sibling royalty-trust block above already includes all 6
                # of these FCF/OCF-derived fields in its own recategorize-fields tuple, but
                # this RIC block never got them - a RIC's "Statement of Changes in Net
                # Assets" has no CapitalExpenditures/OperatingCashFlow concept either (same
                # structural fact as its debt/cash/interest gaps above), so free_cash_flow's
                # capex dependency and operating_cash_flow itself both fall to the generic
                # "missing_sec_data" already in _ric_source_reasons below. Live-confirmed 63
                # active-universe RIC symbols stuck on "missing_sec_data" for fcf_margin/
                # fcf_to_net_income/free_cash_flow (vs. 19 siblings that already resolve to
                # "registered_investment_company_no_xbrl" via some other path) and 14 more
                # for ocf_to_net_income/operating_cash_flow/accruals_ratio.
                "fcf_margin",
                "fcf_to_net_income",
                "free_cash_flow",
                "ocf_to_net_income",
                "operating_cash_flow",
                "accruals_ratio",
            )
            _ric_source_reasons = {
                "missing_sec_data",
                "total_debt_not_itemized",
                "no_recent_cash_reported",
                "interest_expense_not_itemized",
                "stockholders_equity_not_reported",
                "operating_income_not_itemized",
                "total_liabilities_not_reported",
            }
            for _field in _ric_recategorize_fields:
                _reason_key = f"{_field}_unavailable_reason"
                if metrics.get(_field) is None and metrics.get(_reason_key) in _ric_source_reasons:
                    metrics[_reason_key] = "registered_investment_company_no_xbrl"

    def _apply_quality_recategorize_reasons_post(self, metrics: dict[str, Any], symbol: str) -> None:
        """Blank-check-SPAC / unsupported-currency-OCF recategorize loops - run AFTER
        _apply_structural_entity_type_exemption_reasons() in _compute_quality_metrics.
        """
        # FIXED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day follow-up):
        # a pre-merger blank-check SPAC (SIC 6770) already gets "no_revenue_reported"
        # ("Legitimate / not applicable") directly wired into gross_profitability/
        # operating_margin/gross_margin/ebitda_margin/roic_pct/roce_pct's own ternary chains
        # above (see _get_blank_check_symbols()'s docstring) - but the debt/interest/cash-
        # flow-derived fields below never got the same check, despite a blank-check shell
        # having the identical "no real operating business, only trust-account interest
        # income" structural fact: no debt to itemize, no interest expense beyond trust
        # administration, no meaningful operating/free cash flow. Same half-wired-fix
        # pattern as the RIC/royalty-trust/ETF-trust broad loops above/below - reusing this
        # loop's exact mechanism and the identical 7-reason fallback set, targeting the
        # already-correctly-bucketed "no_revenue_reported" reason instead of a new label.
        if symbol in self._get_blank_check_symbols():
            _blank_check_recategorize_fields = (
                "interest_coverage",
                "debt_to_assets",
                "debt_to_equity",
                "asset_turnover",
                "roa",
                "net_margin",
                "current_ratio",
                "quick_ratio",
                "ebitda",
                "total_debt",
                "total_cash",
                "cash_per_share",
                "payout_ratio",
                "accruals_ratio",
                "fcf_margin",
                "fcf_to_net_income",
                "ocf_to_net_income",
                "free_cash_flow",
                "operating_cash_flow",
            )
            # Same 7-reason fallback set as _ric_source_reasons above - kept as its own
            # local rather than reused directly, since that name only exists inside the
            # sibling RIC `if` block above (a blank-check symbol that isn't ALSO RIC-shaped,
            # the normal case, would otherwise hit an UnboundLocalError here).
            # FIXED 2026-09-10 (goal: "under 500" missing-XBRL push): unlike this set,
            # both _ric_source_reasons and _etf_trust_broad_source_reasons above already
            # include "capex_never_tagged_in_recent_filings" (each fixed 2026-09-06 for the
            # identical reason - a fund/trust shape has no CapitalExpenditures concept to
            # tag) - this set never got the same addition, despite fcf_margin/
            # fcf_to_net_income/free_cash_flow already being members of this loop's own
            # _blank_check_recategorize_fields tuple just above. A pre-merger blank-check
            # SPAC has the identical "no real operating business, nothing to capitalize"
            # structural fact, so it hits _get_no_recent_capex_symbols() and lands on
            # "capex_never_tagged_in_recent_filings" ("Missing SEC/XBRL data") instead of
            # this loop's intended "no_revenue_reported" ("Legitimate / not applicable").
            _blank_check_source_reasons = {
                "missing_sec_data",
                "total_debt_not_itemized",
                "no_recent_cash_reported",
                "interest_expense_not_itemized",
                "stockholders_equity_not_reported",
                "operating_income_not_itemized",
                "total_liabilities_not_reported",
                "capex_never_tagged_in_recent_filings",
                # FIXED 2026-09-10 (goal: "SEC/XBRL missing data to zero" sweep, under-500
                # push): live-confirmed COPL/LEGO/MTNE/NWAX/XFLH (all sic_description=
                # "Blank Checks") stuck on "no_recent_free_cash_flow_reported" for fcf_margin
                # instead of this loop's "no_revenue_reported" - the profitability chain's
                # own no_recent_free_cash_flow_reported branch (checked before the generic
                # missing_sec_data fallback this source-reason set was built around) resolves
                # first for these symbols, so this loop never fired for fcf_margin/
                # free_cash_flow/operating_cash_flow/fcf_to_net_income/ocf_to_net_income even
                # though they're all in _blank_check_recategorize_fields above. Same gap
                # class as the royalty-trust source-reason set's identical fix just above.
                "no_recent_free_cash_flow_reported",
            }
            for _field in _blank_check_recategorize_fields:
                _reason_key = f"{_field}_unavailable_reason"
                if metrics.get(_field) is None and metrics.get(_reason_key) in _blank_check_source_reasons:
                    metrics[_reason_key] = "no_revenue_reported"

        # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, same-day follow-up
        # to the has_unsupported_currency_only_fact fix and its sec_valuations.dcf_fcf
        # sibling recategorization): a foreign private issuer whose annual_cash_flow row
        # was already tagged "unsupported_currency_no_fx_rate" (real OCF, only tagged under
        # a hyperinflationary/unsupported currency like ARS) has a real, non-fabricatable
        # ocf=None cascading into every cash-flow-derived field below - same recategorize-
        # loop pattern as the RIC/royalty-trust blocks above, never wired for this cause.
        if symbol in self._get_unsupported_currency_ocf_symbols():
            _unsupported_currency_recategorize_fields = (
                "free_cash_flow",
                "operating_cash_flow",
                "fcf_to_net_income",
                "ocf_to_net_income",
                "fcf_margin",
                "accruals_ratio",
            )
            _unsupported_currency_source_reasons = {
                "missing_sec_data",
                "no_recent_free_cash_flow_reported",
                "no_recent_operating_cash_flow_reported",
                "free_cash_flow_absent_from_anchor_year",
                "operating_cash_flow_absent_from_anchor_year",
                "capex_never_tagged_in_recent_filings",
            }
            for _field in _unsupported_currency_recategorize_fields:
                _reason_key = f"{_field}_unavailable_reason"
                if metrics.get(_field) is None and metrics.get(_reason_key) in _unsupported_currency_source_reasons:
                    metrics[_reason_key] = "unsupported_currency_no_fx_rate"

        # See recategorize_balance_sheet_currency_fields()'s docstring (vqg_shared.py -
        # extracted rather than inlined, same file-size-ratchet discipline as
        # compute_quality_row_level_reason above: vqg_quality.py is past the hard ceiling).
        if symbol in self._get_unsupported_currency_balance_sheet_symbols():
            recategorize_balance_sheet_currency_fields(metrics)
