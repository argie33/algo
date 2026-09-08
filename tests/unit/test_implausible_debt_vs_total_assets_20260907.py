"""Regression test for the 2026-09-07 fix (goal session: live tie-out run against production
DB surfaced 62 annual long_term_debt_le_total_liabilities violations; digging into the worst
ones found a filer/filing-agent XBRL tagging error class, not a tolerance issue).

Live-confirmed via real SEC companyfacts JSON: VGAS (Verde Clean Fuels) FY2023 tags
us-gaap:ConvertibleDebt=$40,963,000,000 (a Q1 2024 10-Q's prior-period comparative column)
against real total_assets of ~$31.9M - a ~1,283x debt-to-assets ratio, impossible for a real
operating company. A DB-wide sweep found 61 similar symbol-years.
"""

from typing import Any

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


class TestImplausibleDebtVsTotalAssets:
    def _make_loader(
        self, statement_type: str = "balance", period: str = "annual"
    ) -> ConsolidatedFinancialStatementsLoader:
        loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = period
        loader.statement_type = statement_type
        loader._explicit_null_rejections = []
        loader._rejection_reasons = {}
        loader._bulk_insert_mgr = type("Mgr", (), {"primary_key": ("symbol", "fiscal_year")})()
        return loader

    def test_vgas_style_implausible_long_term_debt_rejected(self) -> None:
        loader = self._make_loader()
        rows: list[dict[str, Any]] = [
            {"symbol": "VGAS", "fiscal_year": 2023, "total_assets": 31_925_639.0, "long_term_debt": 40_963_000_000.0}
        ]

        loader._reject_implausible_debt_field(rows, "long_term_debt")

        assert rows[0]["long_term_debt"] is None
        assert loader._explicit_null_rejections == [({"symbol": "VGAS", "fiscal_year": 2023}, "long_term_debt")]

    def test_plausible_leveraged_financial_not_rejected(self) -> None:
        loader = self._make_loader()
        rows: list[dict[str, Any]] = [
            {"symbol": "BDC1", "fiscal_year": 2023, "total_assets": 1_000_000_000.0, "long_term_debt": 5_000_000_000.0}
        ]

        loader._reject_implausible_debt_field(rows, "long_term_debt")

        assert rows[0]["long_term_debt"] == 5_000_000_000.0
        assert loader._explicit_null_rejections == []

    def test_skips_when_total_assets_missing(self) -> None:
        loader = self._make_loader()
        rows: list[dict[str, Any]] = [{"symbol": "XYZ", "fiscal_year": 2023, "long_term_debt": 40_963_000_000.0}]

        loader._reject_implausible_debt_field(rows, "long_term_debt")

        assert rows[0]["long_term_debt"] == 40_963_000_000.0

    def test_income_statement_type_is_a_noop(self) -> None:
        loader = self._make_loader(statement_type="income")
        rows: list[dict[str, Any]] = [
            {"symbol": "VGAS", "fiscal_year": 2023, "total_assets": 31_925_639.0, "long_term_debt": 40_963_000_000.0}
        ]

        loader._reject_implausible_debt_field(rows, "long_term_debt")

        assert rows[0]["long_term_debt"] == 40_963_000_000.0
