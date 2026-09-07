"""Regression test for ConsolidatedFinancialStatementsLoader._reject_implausible_goodwill()
(loaders/load_financial_statements.py).

Live-verified 2026-09-07 via ILLR: algo/monitoring/data_patrol/checks/tie_out.py's
goodwill_le_total_assets check flagged FY2024 goodwill=$1,005,778,000 against total_assets=
$50,578,000 - both facts real, from ILLR's own same-filing 10-K (not a comparative echo or a
wrong-period extraction bug). Goodwill is one of the balance-sheet line items summed INTO
total_assets, so it can never legitimately exceed total_assets, not even slightly - a hard
mathematical impossibility, the same class of guard as _reject_implausible_gross_profit and
_reject_implausible_debt_field already apply to their own respective identities.
"""

from typing import Any

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader() -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
    loader.statement_type = "balance"
    loader.table_name = "annual_balance_sheet"
    loader.period = "annual"
    loader._explicit_null_rejections = []
    loader._rejection_reasons = {}
    loader._bulk_insert_mgr = type("Mgr", (), {"primary_key": ("symbol", "fiscal_year")})()
    return loader


class TestImplausibleGoodwillRejected:
    def test_goodwill_exceeding_total_assets_is_rejected(self) -> None:
        loader = _make_loader()
        rows: list[dict[str, Any]] = [
            {
                "symbol": "ILLR",
                "fiscal_year": 2024,
                "total_assets": 50_578_000,
                "goodwill": 1_005_778_000,
            }
        ]

        loader._reject_implausible_goodwill(rows)

        assert rows[0]["goodwill"] is None
        assert rows[0]["total_assets"] == 50_578_000  # untouched

    def test_plausible_goodwill_within_total_assets_is_kept(self) -> None:
        loader = _make_loader()
        rows: list[dict[str, Any]] = [
            {
                "symbol": "MSFT",
                "fiscal_year": 2025,
                "total_assets": 500_000_000_000,
                "goodwill": 67_000_000_000,
            }
        ]

        loader._reject_implausible_goodwill(rows)

        assert rows[0]["goodwill"] == 67_000_000_000

    def test_income_statement_type_is_a_no_op(self) -> None:
        loader = _make_loader()
        loader.statement_type = "income"
        rows: list[dict[str, Any]] = [
            {
                "symbol": "TEST",
                "fiscal_year": 2024,
                "total_assets": 50_578_000,
                "goodwill": 1_005_778_000,
            }
        ]

        loader._reject_implausible_goodwill(rows)

        # Not a balance-sheet row - this method must not touch it.
        assert rows[0]["goodwill"] == 1_005_778_000
