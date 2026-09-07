"""Regression test for the 2026-09-06 fix (goal session: score/tie-out sanity audit,
gross_profit_identity's current top non-CNC/ELV offender).

Live-confirmed via TYGO's (Tigo Energy) real SEC companyfacts JSON: the filer's OWN XBRL
genuinely mistags RevenueFromContractWithCustomerExcludingAssessedTax at exactly 1000x the
correct value for every fiscal year on record, while its "Revenues" concept is correctly
tagged every time - _INCOME_FIELD_MAPPING's documented "ExcludingAssessedTax wins when both are
present" priority (correct for the overwhelming majority of filers) picks the corrupted concept
for this filer specifically.

_reject_scale_mismatched_revenue() force-nulls revenue whenever it's a clean power-of-10
multiple (100x/1000x/10000x, within 1%) of cost_of_revenue + gross_profit - the same magic-ratio
detection already proven safe in sec_statements_entry_resolution.py's frame_magnitude_scale_guard
(the IPAR fix).
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


class TestScaleMismatchedRevenueRejected:
    def test_tygo_style_1000x_revenue_records_rejection(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "TYGO",
                "fiscal_year": 2025,
                "revenue": Decimal("103536000000"),
                "cost_of_revenue": Decimal("59185000"),
                "gross_profit": Decimal("44351000"),
                "net_income": Decimal("-1880000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        transformed = _transform(loader, rows)
        assert ({"symbol": "TYGO", "fiscal_year": 2025}, "revenue") in loader._explicit_null_rejections
        assert transformed[0]["revenue"] is None

    def test_100x_and_10000x_ratios_also_rejected(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "TEST100",
                "fiscal_year": 2025,
                "revenue": Decimal("10000000"),
                "cost_of_revenue": Decimal("60000"),
                "gross_profit": Decimal("40000"),
                "net_income": Decimal("1000"),
                "data_unavailable": False,
                "reason": None,
            },
            {
                "symbol": "TEST10000",
                "fiscal_year": 2025,
                "revenue": Decimal("1000000000"),
                "cost_of_revenue": Decimal("60000"),
                "gross_profit": Decimal("40000"),
                "net_income": Decimal("1000"),
                "data_unavailable": False,
                "reason": None,
            },
        ]
        _transform(loader, rows)
        assert ({"symbol": "TEST100", "fiscal_year": 2025}, "revenue") in loader._explicit_null_rejections
        assert ({"symbol": "TEST10000", "fiscal_year": 2025}, "revenue") in loader._explicit_null_rejections

    def test_normal_revenue_not_a_clean_power_of_ten_is_not_rejected(self) -> None:
        """A real filer's revenue never lands within 1% of an exact power-of-10 multiple of
        cost_of_revenue + gross_profit by coincidence - AAPL-style real numbers must pass."""
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

    def test_missing_gross_profit_is_not_rejected(self) -> None:
        """No independent anchor to compare against - not enough evidence to reject revenue.
        (gross_profit itself gets force-nulled here by the pre-existing
        _reject_stale_gross_profit_without_fresh_concept guard - unrelated to this check -
        so only assert "revenue" specifically was untouched, not that no rejection fired.)"""
        loader = _make_loader()
        rows = [
            {
                "symbol": "TEST",
                "fiscal_year": 2025,
                "revenue": Decimal("1000000"),
                "cost_of_revenue": Decimal("500000"),
                "gross_profit": None,
                "net_income": Decimal("100000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        _transform(loader, rows)
        assert ({"symbol": "TEST", "fiscal_year": 2025}, "revenue") not in loader._explicit_null_rejections

    def test_a_ratio_not_close_to_a_power_of_ten_is_not_rejected(self) -> None:
        """A real, if unusual, ~7x mismatch (e.g. a filer with large unmapped other-income
        lines between revenue and the cogs/gp identity) must not be force-nulled - only a
        clean, suspiciously-exact power-of-10 counts as a scale-error signal."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "TEST7X",
                "fiscal_year": 2025,
                "revenue": Decimal("7000000"),
                "cost_of_revenue": Decimal("600000"),
                "gross_profit": Decimal("400000"),
                "net_income": Decimal("100000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        _transform(loader, rows)
        assert loader._explicit_null_rejections == []


class TestPostRunForcesNullRevenue:
    def test_post_run_issues_update_for_revenue_rejection(self) -> None:
        loader = _make_loader()
        loader._explicit_null_rejections = [({"symbol": "TYGO", "fiscal_year": 2025}, "revenue")]
        mock_ctx, mock_cur = _mock_write_context()
        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()
        queries = [c.args[0] for c in mock_cur.execute.call_args_list]
        assert any("revenue = NULL" in q and "symbol = %s AND fiscal_year = %s" in q for q in queries)
