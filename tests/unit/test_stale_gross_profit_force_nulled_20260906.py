"""Regression test for the 2026-09-06 fix (goal session: tie-out-checker follow-up on the
gross_profit_identity magnitude-bug lead flagged by algo/monitoring/data_patrol/checks/
tie_out.py's Round 2 docstring).

Live-confirmed via real SEC companyfacts JSON: ABBV/GILD/AMGN/ABT's only "GrossProfit" XBRL
facts are a supplementary Q4-only quarterly-data-table stub (~91-day span), correctly rejected
by the annual span_days<330 check in sec_statements_entry_resolution.py - so the current
extraction code produces NO gross_profit value for these filers at all, even though it fetches
real, fresh revenue/cost_of_revenue every run. The gross_profit value already stored for these
rows (a leftover from before that span check existed) was silently protected forever by
preserve_on_missing_fields' COALESCE, since a genuinely-absent fresh value is indistinguishable
from a transient fetch gap at the SQL level.

_reject_stale_gross_profit_without_fresh_concept() force-nulls gross_profit (via the same
_explicit_null_rejections/post_run() bypass-COALESCE mechanism already used for implausible
EPS/shares_outstanding) whenever this run has fresh revenue+cost_of_revenue but no fresh
gross_profit - annual only.
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


def _mock_write_context() -> tuple[MagicMock, MagicMock]:
    mock_cur = MagicMock()
    mock_cur.rowcount = 1
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, mock_cur


class TestStaleGrossProfitRejectionRecorded:
    def test_abbv_style_fresh_revenue_and_cogs_no_fresh_gross_profit_records_rejection(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "ABBV",
                "fiscal_year": 2025,
                "revenue": Decimal("61160000000"),
                "cost_of_revenue": Decimal("18204000000"),
                "gross_profit": None,
                "net_income": Decimal("4226000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        _transform(loader, rows)
        assert ({"symbol": "ABBV", "fiscal_year": 2025}, "gross_profit") in loader._explicit_null_rejections

    def test_fresh_gross_profit_present_is_not_rejected(self) -> None:
        loader = _make_loader()
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
        _transform(loader, rows)
        assert loader._explicit_null_rejections == []

    def test_missing_cost_of_revenue_is_not_rejected(self) -> None:
        """A filer that never tags cost_of_revenue either has no basis for the identity check
        - not enough evidence to force-null gross_profit even if it's also absent."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "TEST",
                "fiscal_year": 2025,
                "revenue": Decimal("1000000"),
                "cost_of_revenue": None,
                "gross_profit": None,
                "net_income": Decimal("100000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        _transform(loader, rows)
        assert loader._explicit_null_rejections == []

    def test_quarterly_period_is_unaffected(self) -> None:
        """The Q4-stub bug only corrupts the ANNUAL bucket - quarterly's own real Q4
        GrossProfit fact legitimately has the same ~90-day span, so this check must not
        apply there."""
        loader = _make_loader(period="quarterly")
        rows = [
            {
                "symbol": "ABBV",
                "fiscal_year": 2025,
                "fiscal_quarter": 4,
                "revenue": Decimal("15000000000"),
                "cost_of_revenue": Decimal("4500000000"),
                "gross_profit": None,
                "net_income": Decimal("1000000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        _transform(loader, rows)
        assert loader._explicit_null_rejections == []


class TestPostRunForcesNullGrossProfit:
    def test_post_run_issues_update_for_gross_profit_rejection(self) -> None:
        loader = _make_loader()
        loader._explicit_null_rejections = [({"symbol": "ABBV", "fiscal_year": 2025}, "gross_profit")]
        mock_ctx, mock_cur = _mock_write_context()
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()
        queries = [c.args[0] for c in mock_cur.execute.call_args_list]
        assert any("gross_profit = NULL" in q and "symbol = %s AND fiscal_year = %s" in q for q in queries)
