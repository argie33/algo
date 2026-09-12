"""Regression test for the 2026-09-11 fix (goal session: "SEC/XBRL missing data under 200"
push, found via scripts/audit_statement_tie_outs.py's cash-flow reconciliation check flagging
UPC as the single largest residual in the entire universe).

Live-confirmed via UPC's (Universe Pharmaceuticals Inc) real SEC companyfacts JSON: its FY2025
20-F retags the SAME comparative historical dates at exactly 1000x their real, previously-filed
values across multiple independent concepts (Cash, NetIncomeLoss) - a whole-filing scale error
that no per-field ratio guard (e.g. _reject_scale_mismatched_revenue) can catch, since every
concept in that one filing is inflated by the same factor and so looks internally consistent.

_reject_known_bad_filing_scale_errors() nulls every numeric field on a row matching the
KNOWN_BAD_FILING_SCALE_ERRORS registry - runs first, before any other guard.
"""

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "income", period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


def _transform(loader: ConsolidatedFinancialStatementsLoader, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
        return loader.transform(rows)


class TestKnownBadFilingScaleErrorRejected:
    def test_upc_fy2025_income_fields_all_nulled(self) -> None:
        loader = _make_loader(statement_type="income")
        rows = [
            {
                "symbol": "UPC",
                "fiscal_year": 2025,
                "revenue": Decimal("17858732000"),
                "cost_of_revenue": Decimal("16000000000"),
                "gross_profit": Decimal("1858732000"),
                "net_income": Decimal("-3672055000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        transformed = _transform(loader, rows)
        row = transformed[0]
        assert row["revenue"] is None
        assert row["cost_of_revenue"] is None
        assert row["gross_profit"] is None
        assert row["net_income"] is None
        rejected_fields = {field for _, field in loader._explicit_null_rejections}
        assert {"revenue", "cost_of_revenue", "gross_profit", "net_income"} <= rejected_fields

    def test_upc_fy2025_cashflow_fields_all_nulled(self) -> None:
        loader = _make_loader(statement_type="cashflow")
        rows = [
            {
                "symbol": "UPC",
                "fiscal_year": 2025,
                "operating_cash_flow": Decimal("-5052319000"),
                "investing_cash_flow": Decimal("-341807000"),
                "financing_cash_flow": Decimal("9726130000"),
                "capex": Decimal("266771000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        transformed = _transform(loader, rows)
        row = transformed[0]
        assert row["operating_cash_flow"] is None
        assert row["investing_cash_flow"] is None
        assert row["financing_cash_flow"] is None
        assert row["capex"] is None

    def test_upc_unaffected_fiscal_years_untouched(self) -> None:
        """Only the confirmed-bad fiscal years (2023-2025, all restated by the same corrupted
        FY2025 20-F) are rejected - UPC's own real historical data from earlier, unaffected
        filings (e.g. FY2022) must keep flowing normally."""
        loader = _make_loader(statement_type="income")
        rows = [
            {
                "symbol": "UPC",
                "fiscal_year": 2022,
                "revenue": Decimal("40143151"),
                "cost_of_revenue": Decimal("30000000"),
                "gross_profit": Decimal("10143151"),
                "net_income": Decimal("11319952"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        transformed = _transform(loader, rows)
        row = transformed[0]
        assert row["revenue"] == Decimal("40143151")
        assert row["net_income"] == Decimal("11319952")
        assert loader._explicit_null_rejections == []

    def test_upc_fy2023_and_fy2024_comparative_restatements_also_rejected(self) -> None:
        """The corrupted FY2025 20-F retags its OWN comparative FY2023/FY2024 figures at
        1000x too, not just its new fiscal year - both must be rejected."""
        loader = _make_loader(statement_type="income")
        rows = [
            {
                "symbol": "UPC",
                "fiscal_year": 2023,
                "revenue": Decimal("32308735000"),
                "cost_of_revenue": Decimal("30000000000"),
                "gross_profit": Decimal("2308735000"),
                "net_income": Decimal("-6581024000"),
                "data_unavailable": False,
                "reason": None,
            },
            {
                "symbol": "UPC",
                "fiscal_year": 2024,
                "revenue": Decimal("23024458000"),
                "cost_of_revenue": Decimal("20000000000"),
                "gross_profit": Decimal("3024458000"),
                "net_income": Decimal("-8727298000"),
                "data_unavailable": False,
                "reason": None,
            },
        ]
        transformed = _transform(loader, rows)
        assert transformed[0]["revenue"] is None
        assert transformed[1]["revenue"] is None

    def test_unrelated_symbol_untouched(self) -> None:
        loader = _make_loader(statement_type="income")
        rows = [
            {
                "symbol": "AAPL",
                "fiscal_year": 2025,
                "revenue": Decimal("400000000000"),
                "cost_of_revenue": Decimal("200000000000"),
                "gross_profit": Decimal("200000000000"),
                "net_income": Decimal("100000000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        transformed = _transform(loader, rows)
        assert transformed[0]["revenue"] == Decimal("400000000000")
        assert loader._explicit_null_rejections == []


class TestPostRunForcesNullForKnownBadFiling:
    def test_post_run_issues_update_for_upc_rejection(self) -> None:
        loader = _make_loader()
        loader._explicit_null_rejections = [({"symbol": "UPC", "fiscal_year": 2025}, "revenue")]
        mock_cur = MagicMock()
        mock_cur.rowcount = 1
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur
        mock_ctx.__exit__.return_value = False
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()
        queries = [c.args[0] for c in mock_cur.execute.call_args_list]
        assert any("revenue = NULL" in q and "symbol = %s AND fiscal_year = %s" in q for q in queries)
