"""Regression test for the 2026-09-10 fix: _reject_implausible_eps()'s NRC-shaped
shares-ratio cross-check (2026-09-06) assumed a row's own reported share count is always
reliable ground truth, so any big gap against implied_shares (net_income/eps) must mean EPS
is wrong. Live-confirmed via EH (EHang)'s real SEC companyfacts JSON this is backwards for a
distinct failure shape: EH tags a real, correct EarningsPerShareBasic/Diluted (FY2024 -$0.23)
against a real, correct NetIncomeLoss (FY2024 -$31.48M) - implied_shares ~136.9M, a perfectly
plausible real public float - but the filer's own
WeightedAverageNumberOfSharesOutstandingBasic tag is 134,367 (a ~1,020x scale-tagging error on
the SHARES concept itself). The old code nulled EH's genuinely-correct EPS over this corrupted
sibling field. Fix: when reported_shares is itself implausibly small for a real company
(< 1,000,000) while implied_shares is not, keep the EPS instead of rejecting it.

NRC (the original precedent for this ratio check, 2026-09-06) must still be rejected: its
reported_shares (22,396,000) is itself a perfectly plausible real-company share count, so
that case correctly falls through to the existing reject branch below, unchanged.
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


class TestEpsKeptWhenReportedSharesAreTheCorruptedSide:
    def test_eh_shaped_row_keeps_real_eps(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "EH",
                "fiscal_year": 2024,
                "revenue": Decimal("62490000"),
                "net_income": Decimal("-31479000"),
                "earnings_per_share": Decimal("-0.23"),
                "diluted_eps": None,
                "shares_outstanding_basic": Decimal("134367"),
                "shares_outstanding_diluted": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["earnings_per_share"] == Decimal("-0.23")
        assert ({"symbol": "EH", "fiscal_year": 2024}, "earnings_per_share") not in loader._explicit_null_rejections

    def test_nrc_shaped_row_still_rejected(self) -> None:
        """NRC's own reported share count (22.396M) is plausible - the gap means EPS is
        wrong, not the share count. Must still reject, unchanged from the 2026-09-06 fix."""
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
