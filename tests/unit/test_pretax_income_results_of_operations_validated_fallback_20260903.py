"""Regression test for the 2026-09-03 fix (goal session: "Missing SEC/XBRL data" reduction,
pretax_income investigation): "ResultsOfOperationsIncomeBeforeIncomeTaxes" is genuinely
ambiguous per-filer - live-confirmed CNX Resources tags it as an ASC 932 oil-and-gas-producing-
activities supplementary disclosure (NOT consolidated pretax income, already documented in the
concept-list comment above get_income_statement()'s concepts list), while RRC (Range Resources,
same SIC 1311 E&P classification) tags the IDENTICAL concept name as its real consolidated
pretax income - FY2020/2021/2022 values (-$737,329,000 / $402,035,000 / $1,413,830,000) match
net_income + income_tax_expense to the exact dollar in all 3 years.

Rather than blindly trusting the concept for every filer (which would be wrong for CNX) or
rejecting it universally (which leaves RRC's real pretax_income unrecovered), cross-validate
the filer's own tagged value against its own already-known net_income + income_tax_expense
identity before promoting it - only an exact match is trusted. This is NOT the blanket
"pretax_income = net_income + income_tax_expense" reconstruction already investigated and
rejected as a scoring-layer fallback (~75% accurate universe-wide, see MEMORY.md's
pretax_income_derivation_rejected) - it only ever uses the filer's OWN real tagged value, and
only when independently corroborated, never a computed number.
"""

import inspect

from utils.external import sec_statements
from utils.external.sec_statements import _fill_pretax_income_from_results_of_operations_when_validated


class TestPretaxIncomeResultsOfOperationsValidatedFallback:
    def test_concept_is_actually_fetched(self) -> None:
        source = inspect.getsource(sec_statements.get_income_statement)
        assert "ResultsOfOperationsIncomeBeforeIncomeTaxes" in source

    def test_rrc_style_match_is_promoted(self) -> None:
        rows = [
            {
                "symbol": "RRC",
                "fiscal_year": 2022,
                "net_income_loss": 1_183_370_000.0,
                "income_tax_expense": 230_460_000.0,
                "results_of_operations_income_before_income_taxes": 1_413_830_000.0,
            }
        ]

        _fill_pretax_income_from_results_of_operations_when_validated(rows)

        assert rows[0]["pretax_income"] == 1_413_830_000.0
        assert "results_of_operations_income_before_income_taxes" not in rows[0]

    def test_cnx_style_mismatch_is_rejected_not_promoted(self) -> None:
        # CNX's real supplementary-disclosure value ($2,317,918,000) does NOT match its real
        # consolidated net_income + income_tax_expense ($1,720,716,000 + $502,209,000 =
        # $2,222,925,000) - must stay unpromoted, not silently accepted as "close enough".
        rows = [
            {
                "symbol": "CNX",
                "fiscal_year": 2023,
                "net_income_loss": 1_720_716_000.0,
                "income_tax_expense": 502_209_000.0,
                "results_of_operations_income_before_income_taxes": 2_317_918_000.0,
            }
        ]

        _fill_pretax_income_from_results_of_operations_when_validated(rows)

        assert rows[0].get("pretax_income") is None
        assert "results_of_operations_income_before_income_taxes" not in rows[0]

    def test_never_overwrites_a_real_pretax_income_value(self) -> None:
        rows = [
            {
                "symbol": "AAPL",
                "fiscal_year": 2024,
                "pretax_income": 999_999_999.0,
                "net_income_loss": 1.0,
                "income_tax_expense": 1.0,
                "results_of_operations_income_before_income_taxes": 2.0,
            }
        ]

        _fill_pretax_income_from_results_of_operations_when_validated(rows)

        assert rows[0]["pretax_income"] == 999_999_999.0

    def test_missing_net_income_or_tax_leaves_candidate_unpromoted(self) -> None:
        rows = [
            {
                "symbol": "XYZ",
                "fiscal_year": 2025,
                "net_income_loss": None,
                "income_tax_expense": 1_000_000.0,
                "results_of_operations_income_before_income_taxes": 5_000_000.0,
            }
        ]

        _fill_pretax_income_from_results_of_operations_when_validated(rows)

        assert rows[0].get("pretax_income") is None
        assert "results_of_operations_income_before_income_taxes" not in rows[0]

    def test_absent_candidate_is_a_no_op(self) -> None:
        rows = [{"symbol": "NOCANDIDATE", "fiscal_year": 2025, "net_income_loss": 1.0, "income_tax_expense": 1.0}]

        _fill_pretax_income_from_results_of_operations_when_validated(rows)

        assert rows[0].get("pretax_income") is None
