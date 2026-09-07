"""Regression test for the 2026-09-07 fix: _reject_implausible_shares_outstanding() only
guarded shares_outstanding_basic/shares_outstanding_diluted against filer/filing-agent XBRL
scale-tagging errors - shares_outstanding_dei sits in the exact same fallback chain
(transform()'s `shares = diluted or basic or dei`, used when a filer never tags either period-
average concept) but was never covered, so a tagging error on it could sail straight through
into EPS derivation.

Live-confirmed via EEFT's (Euronet Worldwide) own filed 10-K XBRL (CIK 0001029199, accn
0001213900-21-010724): dei:EntityCommonStockSharesOutstanding tagged as
52,752,851,000,000,000 for FY2020, while the filer's own three FY2020 10-Qs on file all show a
real ~52.2-52.3M share count - the same many-orders-of-magnitude tagging error class as NMR's
diluted-shares case this guard already exists for (see
test_financial_statements_implausible_rejection_force_nulled_20260823.py), just on the DEI
cover-page concept instead.
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


class TestDeiSharesOutstandingScaleGuard:
    def test_dei_absolute_ceiling_rejection_records(self) -> None:
        """EEFT-shaped case: dei tagged ~1,000,000x too large, basic/diluted both absent."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "EEFT",
                "fiscal_year": 2020,
                "revenue": Decimal("2600000000"),
                "net_income": Decimal("140000000"),
                "shares_outstanding_basic": None,
                "shares_outstanding_diluted": None,
                "shares_outstanding_dei": Decimal("52752851000000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        transformed = _transform(loader, rows)
        assert (
            {"symbol": "EEFT", "fiscal_year": 2020},
            "shares_outstanding_dei",
        ) in loader._explicit_null_rejections
        assert transformed[0]["shares_outstanding_dei"] is None

    def test_dei_absolute_floor_rejection_records(self) -> None:
        """Mirror of the basic/diluted 'reported in thousands' floor case, applied to dei."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "TINY",
                "fiscal_year": 2024,
                "revenue": Decimal("5000000"),
                "net_income": Decimal("300000"),
                "shares_outstanding_basic": None,
                "shares_outstanding_diluted": None,
                "shares_outstanding_dei": Decimal("52205"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        _transform(loader, rows)
        assert (
            {"symbol": "TINY", "fiscal_year": 2024},
            "shares_outstanding_dei",
        ) in loader._explicit_null_rejections

    def test_plausible_dei_not_rejected(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "PJT",
                "fiscal_year": 2020,
                "revenue": Decimal("400000000"),
                "net_income": Decimal("50000000"),
                "shares_outstanding_basic": None,
                "shares_outstanding_diluted": None,
                "shares_outstanding_dei": Decimal("28000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        transformed = _transform(loader, rows)
        assert loader._explicit_null_rejections == []
        assert transformed[0]["shares_outstanding_dei"] == Decimal("28000000")

    def test_dei_relative_cross_check_rejection_records(self) -> None:
        """A dei value that clears the absolute ceiling but still disagrees >20x with
        company_info_sec.shares_outstanding (the same relative cross-check basic/diluted
        already get) should also be rejected."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "RATX",
                "fiscal_year": 2024,
                "revenue": Decimal("10000000"),
                "net_income": Decimal("500000"),
                "shares_outstanding_basic": None,
                "shares_outstanding_diluted": None,
                "shares_outstanding_dei": Decimal("5000000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]

        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [("RATX", 20_000_000.0)]
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur
        mock_ctx.__exit__.return_value = False

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            _transform(loader, rows)

        assert (
            {"symbol": "RATX", "fiscal_year": 2024},
            "shares_outstanding_dei",
        ) in loader._explicit_null_rejections
