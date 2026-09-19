"""Regression test for the 2026-09-19 fix (/goal data-confidence backlog, small-bank
long_term_debt cluster flagged by buse_bank_subordinated_debt_partial_lead_20260919.md as
"worth checking as a group next"): is_narrow_standard_debt_blocking_combined_total and its
mirror-image sibling is_immaterial_standard_debt_overwriting_combined_total both assumed a
_COMBINED_DEBT_TOTAL_CONCEPTS value (e.g. "DebtAndCapitalLeaseObligations") is always a strict
structural superset of the plain "LongTermDebt" concept - true for an industrial filer like DPZ,
but not for a bank/thrift holding company, where the combined concept conflates genuine
long-term debt (subordinated notes/trust preferred) with FHLB advances (a separate, shorter-
duration wholesale-funding line yfinance and this codebase's own methodology exclude from
"long-term debt").

Live-confirmed via real SEC companyfacts JSON 2026-09-19: BHB (First Bancorp, CIK 0000743367)
FY2023 plain LongTermDebt=$60,740,000 (exact yfinance match) vs
DebtAndCapitalLeaseObligations=$331,505,000 (~5.5x larger, roughly LongTermDebt + FHLB advances
+ other wholesale borrowings) - the 5x-multiplier heuristic silently swapped in the wrong,
FHLB-inclusive figure across all 3 flagged fiscal years before this fix.

See loaders/helpers/sec_zero_component_guards.py's is_narrow_standard_debt_blocking_combined_total
and is_immaterial_standard_debt_overwriting_combined_total docstrings for the guards this tests.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestBankLongTermDebtCombinedTotalExclusion:
    def _make_loader(
        self, depository_institution_symbols: frozenset[str] = frozenset({"BHB"})
    ) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "long_term_debt", "short_term_debt", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "long_term_debt": "long_term_debt",
            "long_term_debt_and_capital_lease_obligations": "long_term_debt",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"long_term_debt_and_capital_lease_obligations"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        loader._depository_institution_symbols = depository_institution_symbols
        return loader

    def test_bank_standard_concept_processed_first_not_overridden_by_combined_total(self) -> None:
        """Mirrors the DPZ test's fetch order (standard concept first), but for a bank symbol
        the plain LongTermDebt value must survive - the combined total is the wrong figure."""
        loader = self._make_loader()
        row = {
            "symbol": "BHB",
            "fiscal_year": 2023,
            "long_term_debt": 60_740_000.0,
            "long_term_debt_and_capital_lease_obligations": 331_505_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 60_740_000.0

    def test_bank_combined_total_processed_first_still_overridden_by_standard_concept(self) -> None:
        """Mirrors the real live BHB fetch order (combined-total concept first) - the plain
        LongTermDebt concept, processed later, must still be allowed to win for a bank."""
        loader = self._make_loader()
        row = {
            "symbol": "BHB",
            "fiscal_year": 2023,
            "long_term_debt_and_capital_lease_obligations": 331_505_000.0,
            "long_term_debt": 60_740_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 60_740_000.0

    def test_non_bank_dpz_still_gets_the_combined_total_override(self) -> None:
        """The exclusion must be scoped to depository-institution symbols only - DPZ's own
        combined-total override (the case this guard was originally built for) must be
        unaffected."""
        loader = self._make_loader(depository_institution_symbols=frozenset({"BHB"}))
        row = {
            "symbol": "DPZ",
            "fiscal_year": 2025,
            "long_term_debt": 14_600_000.0,
            "long_term_debt_and_capital_lease_obligations": 4_810_683_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["long_term_debt"] == 4_810_683_000.0
