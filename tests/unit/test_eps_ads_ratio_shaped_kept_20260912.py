"""Regression test for the 2026-09-12 fix: _reject_implausible_eps()'s NRC-shaped
shares-ratio cross-check (2026-09-06) rejected any >10x gap between implied_shares
(net_income/eps) and the row's own reported share count as a filer-side scale-tagging
error, even when that gap is a genuine ADS-vs-ordinary-share unit-basis difference rather
than a mistake.

Live-confirmed via ATHE (Alterity Therapeutics, 20-F/IFRS, real ADS ratio 1 ADS = 100
ordinary shares): its EarningsPerShareBasic (ifrs-full:BasicEarningsLossPerShare) is
genuinely tagged per-ADS (FY2023 -0.57 AUD) while its WeightedAverageShares concept is
genuinely tagged in ordinary shares (2,427,841,917) - both real, correctly-tagged facts,
just on two different real unit bases. The ratio held at ~100x across 4 separate fiscal
years (99.24x/99.75x/100.00x/100.04x), the signature of a fixed real-world ADS ratio,
unlike NRC's one-off ~96.53x scale error (3.5% away from the nearest clean ratio
candidate, 100) which must still be rejected unchanged.
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


class TestEpsKeptWhenGapIsAdsRatioShaped:
    def test_athe_shaped_row_keeps_real_eps(self) -> None:
        loader = _make_loader()
        rows = [
            {
                "symbol": "ATHE",
                "fiscal_year": 2023,
                "revenue": None,
                "net_income": Decimal("-9148840.37"),
                "earnings_per_share": Decimal("-0.3777"),
                "diluted_eps": None,
                "shares_outstanding_basic": Decimal("2427841917"),
                "shares_outstanding_diluted": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = _transform(loader, rows)
        assert result[0]["earnings_per_share"] == Decimal("-0.3777")
        assert ({"symbol": "ATHE", "fiscal_year": 2023}, "earnings_per_share") not in loader._explicit_null_rejections

    def test_nrc_shaped_row_still_rejected(self) -> None:
        """NRC's ~96.53x gap is 3.5% away from the nearest clean ADS ratio (100) - not
        within the tight tolerance a genuine ADS ratio would land inside. Must still
        reject, unchanged from the 2026-09-06/09-10 fixes."""
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
