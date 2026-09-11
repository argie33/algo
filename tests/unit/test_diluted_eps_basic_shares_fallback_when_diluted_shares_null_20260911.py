"""Regression test for the 2026-09-11 fix: _reject_implausible_eps()'s NRC-shaped
shares-ratio cross-check for the "diluted_eps" field only ever compared against
shares_outstanding_diluted - when a filer reports no dilutive securities and tags only
WeightedAverageNumberOfSharesOutstandingBasic (never a separate diluted variant),
shares_outstanding_diluted is NULL, so the cross-check silently never ran and let the
exact same scale-mistagged value the sibling "earnings_per_share" check correctly
rejected sail into diluted_eps unguarded.

Live-confirmed via ATHE (Alterity Therapeutics, ASX-listed biotech filing 20-F): every
annual_income_statement row has shares_outstanding_diluted NULL, shares_outstanding_basic
a real, large value (e.g. FY2020 894,872,224), and diluted_eps==earnings_per_share (both
sourced from the filer's ifrs-full:BasicEarningsLossPerShare/DilutedEarningsLossPerShare,
tagged identically) - the basic value was correctly rejected as a ~100x scale mismatch
against shares_outstanding_basic, but diluted_eps kept the same bad value since its own
denominator was missing. Fix: fall back to shares_outstanding_basic for the diluted_eps
check when shares_outstanding_diluted is null - basic and diluted share counts are always
close, so basic is a safe proxy.
"""

from decimal import Decimal
from typing import Any
from unittest.mock import patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "income", period: str = "annual") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


def _transform(loader: ConsolidatedFinancialStatementsLoader, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
        return loader.transform(rows)


class TestDilutedEpsFallsBackToBasicSharesWhenDilutedSharesNull:
    def test_athe_shaped_row_rejects_diluted_eps_via_basic_shares_fallback(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "ATHE",
                "fiscal_year": 2020,
                "revenue": Decimal("0"),
                "net_income": Decimal("-9220144"),
                "earnings_per_share": None,
                "diluted_eps": Decimal("-1.027749229188078"),
                "shares_outstanding_basic": Decimal("894872224"),
                "shares_outstanding_diluted": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["diluted_eps"] is None
        assert ({"symbol": "ATHE", "fiscal_year": 2020}, "diluted_eps") in loader._explicit_null_rejections

    def test_real_diluted_eps_kept_when_basic_shares_corroborate_it(self) -> None:
        """A genuinely correct diluted_eps must survive the basic-shares fallback too."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "REALCO",
                "fiscal_year": 2024,
                "revenue": Decimal("500000000"),
                "net_income": Decimal("50000000"),
                "earnings_per_share": None,
                "diluted_eps": Decimal("0.50"),
                "shares_outstanding_basic": Decimal("100000000"),
                "shares_outstanding_diluted": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["diluted_eps"] == Decimal("0.50")

    def test_nrc_shaped_row_still_uses_real_diluted_shares_not_the_fallback(self) -> None:
        """When shares_outstanding_diluted IS present, the fallback must never override it -
        unchanged from the existing 2026-09-10 EH/NRC behavior."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "NRC",
                "fiscal_year": 2025,
                "revenue": Decimal("500000000"),
                "net_income": Decimal("11600000"),
                "earnings_per_share": None,
                "diluted_eps": Decimal("50.00"),
                "shares_outstanding_basic": None,
                "shares_outstanding_diluted": Decimal("22396000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["diluted_eps"] is None
        assert ({"symbol": "NRC", "fiscal_year": 2025}, "diluted_eps") in loader._explicit_null_rejections
