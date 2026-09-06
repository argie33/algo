"""Regression test for the 2026-09-06 fix (goal session: tie-out-checker follow-up on the
pretax_to_net_income magnitude-bug lead flagged by algo/monitoring/data_patrol/checks/
tie_out.py's Round 2 docstring): ORCL/MCD/PYPL/PSX all tag a real Domestic/Foreign
pretax-income split (ASC 740-10-50-11's required disclosure) but have no populated combined-
concept entry for recent fiscal years - the old field_mapping wired "Domestic" straight to
"pretax_income" unconditionally, silently understating true pretax income by the entire
foreign-sourced share (ORCL FY2025: stored $4.376B vs. real $14.160B).

_fill_pretax_income_from_domestic_foreign_split sums Domestic + Foreign and only trusts the
result when it exactly matches the independently-known net_income + income_tax_expense
identity - same validation discipline as the sibling
_fill_pretax_income_from_results_of_operations_when_validated fallback.
"""

import inspect

from utils.external import sec_statements
from utils.external.sec_statements import _fill_pretax_income_from_domestic_foreign_split


class TestPretaxIncomeDomesticForeignSplitFallback:
    def test_concept_is_actually_fetched(self) -> None:
        source = inspect.getsource(sec_statements.get_income_statement)
        assert "IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign" in source

    def test_orcl_style_match_is_promoted(self) -> None:
        rows = [
            {
                "symbol": "ORCL",
                "fiscal_year": 2025,
                "net_income_loss": 12_443_000_000.0,
                "income_tax_expense": 1_717_000_000.0,
                "income_loss_from_continuing_operations_before_income_taxes_domestic": 4_376_000_000.0,
                "income_loss_from_continuing_operations_before_income_taxes_foreign": 9_784_000_000.0,
            }
        ]

        _fill_pretax_income_from_domestic_foreign_split(rows)

        assert rows[0]["pretax_income"] == 14_160_000_000.0
        assert "income_loss_from_continuing_operations_before_income_taxes_domestic" not in rows[0]
        assert "income_loss_from_continuing_operations_before_income_taxes_foreign" not in rows[0]

    def test_domestic_only_filer_still_promoted_when_validated(self) -> None:
        # CNX-style: genuinely no real Foreign concept at all - domestic alone must still
        # validate and be promoted (no regression for this population).
        rows = [
            {
                "symbol": "CNX",
                "fiscal_year": 2023,
                "net_income_loss": 1_720_716_000.0,
                "income_tax_expense": 502_209_000.0,
                "income_loss_from_continuing_operations_before_income_taxes_domestic": 2_222_925_000.0,
            }
        ]

        _fill_pretax_income_from_domestic_foreign_split(rows)

        assert rows[0]["pretax_income"] == 2_222_925_000.0

    def test_falls_back_to_raw_income_tax_expense_benefit_key(self) -> None:
        # PSX-style: no CurrentIncomeTaxExpenseBenefit/DeferredIncomeTaxExpenseBenefit split,
        # so "income_tax_expense" isn't set yet at this pre-transform() stage - only the raw
        # "income_tax_expense_benefit" key from the plain concept is available.
        rows = [
            {
                "symbol": "TEST",
                "fiscal_year": 2024,
                "net_income_loss": 1_000_000.0,
                "income_tax_expense_benefit": 200_000.0,
                "income_loss_from_continuing_operations_before_income_taxes_domestic": 700_000.0,
                "income_loss_from_continuing_operations_before_income_taxes_foreign": 500_000.0,
            }
        ]

        _fill_pretax_income_from_domestic_foreign_split(rows)

        assert rows[0]["pretax_income"] == 1_200_000.0

    def test_mismatch_is_rejected_not_promoted(self) -> None:
        # PSX-real-world-style: material noncontrolling interest makes the sum disagree with
        # net_income + income_tax_expense - must stay unpromoted, not accepted as "close enough".
        rows = [
            {
                "symbol": "PSX",
                "fiscal_year": 2024,
                "net_income_loss": 2_117_000_000.0,
                "income_tax_expense": 500_000_000.0,
                "income_loss_from_continuing_operations_before_income_taxes_domestic": 1_796_000_000.0,
                "income_loss_from_continuing_operations_before_income_taxes_foreign": 879_000_000.0,
            }
        ]

        _fill_pretax_income_from_domestic_foreign_split(rows)

        assert rows[0].get("pretax_income") is None
        assert "income_loss_from_continuing_operations_before_income_taxes_domestic" not in rows[0]
        assert "income_loss_from_continuing_operations_before_income_taxes_foreign" not in rows[0]

    def test_never_overwrites_a_real_pretax_income_value(self) -> None:
        rows = [
            {
                "symbol": "AAPL",
                "fiscal_year": 2024,
                "pretax_income": 999_999_999.0,
                "net_income_loss": 1.0,
                "income_tax_expense": 1.0,
                "income_loss_from_continuing_operations_before_income_taxes_domestic": 2.0,
                "income_loss_from_continuing_operations_before_income_taxes_foreign": 3.0,
            }
        ]

        _fill_pretax_income_from_domestic_foreign_split(rows)

        assert rows[0]["pretax_income"] == 999_999_999.0

    def test_missing_net_income_leaves_candidate_unpromoted(self) -> None:
        rows = [
            {
                "symbol": "XYZ",
                "fiscal_year": 2025,
                "net_income_loss": None,
                "income_tax_expense": 1_000_000.0,
                "income_loss_from_continuing_operations_before_income_taxes_domestic": 5_000_000.0,
            }
        ]

        _fill_pretax_income_from_domestic_foreign_split(rows)

        assert rows[0].get("pretax_income") is None
        assert "income_loss_from_continuing_operations_before_income_taxes_domestic" not in rows[0]

    def test_absent_domestic_is_a_no_op(self) -> None:
        rows = [{"symbol": "NOCANDIDATE", "fiscal_year": 2025, "net_income_loss": 1.0, "income_tax_expense": 1.0}]

        _fill_pretax_income_from_domestic_foreign_split(rows)

        assert rows[0].get("pretax_income") is None
