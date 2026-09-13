"""Regression test for ConsolidatedFinancialStatementsLoader.
_reject_implausible_asset_liability_subtotals() (loaders/load_financial_statements.py).

Live-verified 2026-09-13 via NXAT (Nexus Advanced Technologies, formerly K Wave Media - CIK
0002000756): FY2024 total_assets=$50,000/total_liabilities=$12,807 (sourced from a stale
pre-merger blank-check-shell 6-K placeholder balance sheet) against current_assets=
$11,237,510/current_liabilities=$15,854,527 (real post-merger operating-company figures) on
the SAME row. A "total" can never legitimately be smaller than a subset of the line items
summed into it - the same class of hard mathematical-impossibility guard as
_reject_implausible_goodwill, but rejecting the coarse subtotal instead of the fine-grained
component, since here the components are the trustworthy (real-scale, internally consistent)
values and the total is the outlier.
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


class TestImplausibleAssetLiabilitySubtotalsRejected:
    def test_total_assets_below_current_assets_is_rejected(self) -> None:
        loader = _make_loader()
        rows: list[dict[str, Any]] = [
            {
                "symbol": "NXAT",
                "fiscal_year": 2024,
                "total_assets": 50_000,
                "current_assets": 11_237_510,
                "total_liabilities": 12_807,
                "current_liabilities": 15_854_527,
            }
        ]

        loader._reject_implausible_asset_liability_subtotals(rows)

        assert rows[0]["total_assets"] is None
        assert rows[0]["total_liabilities"] is None
        assert rows[0]["current_assets"] == 11_237_510  # untouched - the trustworthy value
        assert rows[0]["current_liabilities"] == 15_854_527  # untouched

    def test_plausible_totals_above_components_are_kept(self) -> None:
        loader = _make_loader()
        rows: list[dict[str, Any]] = [
            {
                "symbol": "MSFT",
                "fiscal_year": 2025,
                "total_assets": 500_000_000_000,
                "current_assets": 150_000_000_000,
                "total_liabilities": 200_000_000_000,
                "current_liabilities": 100_000_000_000,
            }
        ]

        loader._reject_implausible_asset_liability_subtotals(rows)

        assert rows[0]["total_assets"] == 500_000_000_000
        assert rows[0]["total_liabilities"] == 200_000_000_000

    def test_income_statement_type_is_a_no_op(self) -> None:
        loader = _make_loader()
        loader.statement_type = "income"
        rows: list[dict[str, Any]] = [
            {
                "symbol": "TEST",
                "fiscal_year": 2024,
                "total_assets": 50_000,
                "current_assets": 11_237_510,
            }
        ]

        loader._reject_implausible_asset_liability_subtotals(rows)

        # Not a balance-sheet row - this method must not touch it.
        assert rows[0]["total_assets"] == 50_000

    def test_missing_fields_are_skipped_without_error(self) -> None:
        loader = _make_loader()
        rows: list[dict[str, Any]] = [
            {"symbol": "NOASSETS", "fiscal_year": 2024, "current_assets": 100},
            {"symbol": "NOCOMPONENT", "fiscal_year": 2024, "total_assets": 100},
        ]

        loader._reject_implausible_asset_liability_subtotals(rows)

        assert rows[0]["current_assets"] == 100
        assert rows[1]["total_assets"] == 100
