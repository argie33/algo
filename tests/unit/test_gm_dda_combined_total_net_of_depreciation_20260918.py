"""Regression test for the 2026-09-18 fix (goal session: data-issue reduction): GM (General
Motors) live-confirmed via real SEC companyfacts JSON - "DepreciationDepletionAndAmortization"
is a COMBINED depreciation+amortization total (FY2024 $11,456,000,000), not a pure-amortization
figure. GM also separately tags a real "Depreciation" fact (FY2024 $4,800,000,000, processed
first per sec_income_statement.py's concept order). Before this fix, storing DD&A whole into
amortization_expense (its mapped db_field) double-counted depreciation for any downstream
consumer that sums depreciation_expense + amortization_expense (e.g. an EBITDA calculation, or
scripts/xbrl_yfinance_crosscheck.py's own _COMPOSITE_SUM_FIELDS). The fix subtracts
depreciation_expense from DD&A when depreciation_expense is already populated, storing the
genuine incremental amortization portion ($11,456,000,000 - $4,800,000,000 = $6,656,000,000)
instead - depreciation_expense + amortization_expense now correctly sums back to DD&A's real
total ($11,456,000,000), matching real GM data (close to yfinance's flagged $12,389,000,000).

This also fixes the FOLLOW-ON bug an earlier same-session fix
(is_narrow_intangible_amortization_overwriting_combined_dda in sec_zero_component_guards.py)
would otherwise have needed to protect: GM's later, smaller
"AmortizationOfIntangibleAssets" fact ($146,000,000) must not overwrite the DD&A-derived
value - that guard now protects the correctly-SUBTRACTED $6,656,000,000, not a raw double-
counted total.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestGmDdaCombinedTotalNetOfDepreciation:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "depreciation_expense", "amortization_expense", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "depreciation": "depreciation_expense",
            "depreciation_depletion_and_amortization": "amortization_expense",
            "amortization_of_intangible_assets": "amortization_expense",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_dda_combined_total_stored_net_of_already_populated_depreciation(self) -> None:
        loader = self._make_loader()
        # Dict-insertion order matches GM's real concept-list order: "depreciation" (plain
        # Depreciation concept) processed before "depreciation_depletion_and_amortization",
        # which is itself processed before the small "amortization_of_intangible_assets".
        row = {
            "symbol": "GM",
            "fiscal_year": 2024,
            "depreciation": 4_800_000_000.0,
            "depreciation_depletion_and_amortization": 11_456_000_000.0,
            "amortization_of_intangible_assets": 146_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["depreciation_expense"] == 4_800_000_000.0
        assert transformed[0]["amortization_expense"] == 6_656_000_000.0
        # The whole point: summing the two columns back must equal DD&A's real reported total,
        # not overshoot it (double-count) or undershoot it (the pre-fix small-concept-wins bug).
        assert transformed[0]["depreciation_expense"] + transformed[0]["amortization_expense"] == 11_456_000_000.0

    def test_dda_stored_whole_when_no_separate_depreciation_populated(self) -> None:
        """Most filers using this concept have no separate 'Depreciation' fact at all (per the
        concept's original design comment) - DD&A must still land whole in that ordinary case,
        unchanged from before this fix."""
        loader = self._make_loader()
        row = {"symbol": "NODEP", "fiscal_year": 2025, "depreciation_depletion_and_amortization": 300_772_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["amortization_expense"] == 300_772_000.0
        assert transformed[0].get("depreciation_expense") is None
