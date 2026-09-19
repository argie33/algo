"""Regression test for the 2026-09-19 fix (/goal data-confidence audit): ADSK (Autodesk, CIK
0000769397) live-confirmed via the actual FY2026 10-K cash flow statement (R8.htm, accession
0000769397-26-000015) - the FACE of the statement tags "Depreciation, amortization, and
accretion" = $195,000,000 under us-gaap:DepreciationAndAmortization, the filer's own
authoritative combined total. ADSK separately tags a real but narrower footnote-level
"AmortizationOfIntangibleAssets" fact ($53,000,000) that doesn't even sum with "Depreciation"'s
own footnote figure ($43,000,000) to reach $195,000,000 - it is a subset, not an additional
component. Before this fix, "amortization_of_intangible_assets" (processed later per
sec_income_statement.py's concept order) unconditionally overwrote the correct $195,000,000
combined total via ordinary last-listed-wins, storing just $53,000,000 instead - a ~2x
understatement contributing to the ratio ~0.5 depreciation_expense divergence cluster (see
depreciation_expense_generic_overwrite_and_multi_mechanism_cluster_20260919 memory note).
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestAdskDaTotalNotOverwrittenByIntangibleAmortization:
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
            "depreciation_and_amortization": "amortization_expense",
            "amortization_of_intangible_assets": "amortization_expense",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_da_combined_total_survives_narrower_intangible_amortization(self) -> None:
        loader = self._make_loader()
        # Dict-insertion order matches ADSK's real concept-list order: "depreciation" (plain
        # Depreciation footnote concept) and "depreciation_and_amortization" (the face-of-
        # statement combined total) both processed before the narrower
        # "amortization_of_intangible_assets" footnote concept.
        row = {
            "symbol": "ADSK",
            "fiscal_year": 2026,
            "depreciation": 43_000_000.0,
            "depreciation_and_amortization": 195_000_000.0,
            "amortization_of_intangible_assets": 53_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["depreciation_expense"] == 43_000_000.0
        assert transformed[0]["amortization_expense"] == 195_000_000.0

    def test_intangible_amortization_still_wins_when_no_combined_total_present(self) -> None:
        """A filer with no DepreciationAndAmortization concept at all must still get its plain
        AmortizationOfIntangibleAssets figure - the guard only fires to protect an
        already-resolved combined total, not as a blanket rule against this concept."""
        loader = self._make_loader()
        row = {"symbol": "NODA", "fiscal_year": 2025, "amortization_of_intangible_assets": 2_384_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["amortization_expense"] == 2_384_000.0
