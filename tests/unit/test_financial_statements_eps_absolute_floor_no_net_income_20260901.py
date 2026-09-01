"""Regression test for the 2026-08-31 fix (recovered from a stranded branch onto main
2026-09-01, /goal session - see risk_min_weight_available_floor_added_20260831 memory entry for
the broader pattern): _reject_implausible_eps()'s implied-shares check requires net_income to be
present and non-zero for the SAME row - live-confirmed via actual loader log output
(logs/load_financial_statements_1788220265.log) that SWK/UAMY quarterly rows hit the raw
NUMERIC(12,4) column-overflow guard in sec_base.py instead of this smarter rejection, because
their garbage per-share values (e.g. earnings_per_share=150330000, 107260472) came from rows
where net_income was missing/None for that specific quarter, so the `if net_income is None or
net_income == 0: continue` skipped the whole row - the same filer-side XBRL mistagging bug this
function already exists to catch, just not caught here.

Fix: an absolute-magnitude fallback ($1,000,000/share) that fires independent of net_income
availability - comfortably above BRK.A's real historical extremes (under $200,000/share even in
exceptional years) but far below the garbage values actually observed (100-160 million).
"""

from decimal import Decimal
from typing import Any
from unittest.mock import patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(period: str = "quarterly") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type="income", period=period)


def _transform(loader: ConsolidatedFinancialStatementsLoader, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
        return loader.transform(rows)


class TestAbsoluteFloorFallbackWhenNetIncomeMissing:
    def test_garbage_eps_rejected_when_net_income_is_none(self) -> None:
        """Exact SWK-shaped reproduction: net_income missing for this row, garbage
        earnings_per_share must still be rejected via the absolute floor, not left to hit the
        raw column-overflow guard downstream."""
        loader = _make_loader()
        rows = [
            {
                "symbol": "SWK",
                "fiscal_year": 2020,
                "fiscal_quarter": 1,
                "revenue": Decimal("2500000000"),
                "net_income": None,
                "earnings_per_share": Decimal("150330000"),
                "diluted_eps": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["earnings_per_share"] is None
        assert ({"symbol": "SWK", "fiscal_year": 2020, "fiscal_quarter": 1}, "earnings_per_share") in (
            loader._explicit_null_rejections
        )

    def test_garbage_eps_rejected_when_net_income_is_zero(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "UAMY",
                "fiscal_year": 2023,
                "fiscal_quarter": 2,
                "revenue": Decimal("5000000"),
                "net_income": Decimal("0"),
                "earnings_per_share": None,
                "diluted_eps": Decimal("107260472"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["diluted_eps"] is None

    def test_net_income_based_rejection_still_takes_priority_and_still_works(self) -> None:
        """Sanity check: this fix must not regress the original net_income-based path - when
        net_income IS available, the more precise implied-shares check still applies (and would
        catch values well under the $1M absolute floor that the floor alone would miss)."""
        loader = _make_loader(period="annual")
        rows = [
            {
                "symbol": "GIBO",
                "fiscal_year": 2024,
                "revenue": Decimal("30000000"),
                "net_income": Decimal("-24852333"),
                "earnings_per_share": Decimal("-24852333"),
                "diluted_eps": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["earnings_per_share"] is None

    def test_real_extreme_but_plausible_eps_not_rejected_by_absolute_floor(self) -> None:
        """A BRK.A-style real extreme (net_income missing this row, EPS genuinely in the tens
        of thousands) must clear the $1M absolute floor comfortably and NOT be rejected."""
        loader = _make_loader(period="annual")
        rows = [
            {
                "symbol": "BRK.A",
                "fiscal_year": 2021,
                "revenue": Decimal("354000000000"),
                "net_income": None,
                "earnings_per_share": Decimal("91568"),
                "diluted_eps": Decimal("91568"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["earnings_per_share"] == Decimal("91568")
        assert result[0]["diluted_eps"] == Decimal("91568")
        assert loader._explicit_null_rejections == []

    def test_normal_eps_with_no_net_income_not_rejected(self) -> None:
        """The common, benign case this fix must not break: a row simply has no net_income
        extracted this run, but its EPS value is completely ordinary - must pass through
        untouched, not be treated as suspicious just because net_income is absent."""
        loader = _make_loader(period="annual")
        rows = [
            {
                "symbol": "AAPL",
                "fiscal_year": 2025,
                "revenue": Decimal("400000000000"),
                "net_income": None,
                "earnings_per_share": Decimal("6.50"),
                "diluted_eps": Decimal("6.48"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["earnings_per_share"] == Decimal("6.50")
        assert result[0]["diluted_eps"] == Decimal("6.48")
        assert loader._explicit_null_rejections == []
