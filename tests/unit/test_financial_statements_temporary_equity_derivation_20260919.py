"""Regression test for the 2026-09-19 temporary_equity fix to the total_assets/
total_liabilities derivation fallbacks (data-quality-issue-reduction goal session).

Live-confirmed via real SEC data: SOUN (SoundHound AI, formerly Archimedes Tech
SPAC Partners Co, CIK 0001840856) FY2020 stored total_assets=-276,352,284 - a
data_patrol_log total_assets_nonnegative WARN. Root cause: the fallback derivation
`total_assets = total_liabilities + stockholders_equity` (and its total_liabilities
counterpart) assumed the balance-sheet identity has only two components, but a SPAC's
large `temporary_equity` (redeemable shares in trust, classified as mezzanine equity -
neither a liability nor permanent equity) was silently dropped, producing a deeply
negative, mathematically impossible result: 716 (total_liabilities) +
-276,353,000 (stockholders_equity) = -276,352,284, exactly matching the corrupted
stored value. The real identity is Assets = Liabilities + Temporary Equity +
Stockholders' Equity.

Both derivations now include temporary_equity (defaulting to 0 when absent, so the
existing BTTC/XLAB-style two-component filers are unaffected) and reject a still-
negative result rather than storing an impossible value.
"""

from decimal import Decimal
from unittest.mock import patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


class TestTemporaryEquityDerivation:
    def _make_loader(self) -> ConsolidatedFinancialStatementsLoader:
        return ConsolidatedFinancialStatementsLoader(statement_type="balance", period="annual")

    def test_total_assets_includes_temporary_equity(self):
        loader = self._make_loader()
        rows = [
            {
                "symbol": "SPACCO",
                "fiscal_year": 2024,
                "total_assets": None,
                "stockholders_equity": Decimal("-50000000"),
                "total_liabilities": Decimal("1000"),
                "temporary_equity": Decimal("60000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
            result = loader.transform(rows)

        # 1000 + -50000000 + 60000000 = 10001000, not the pre-fix -49999000.
        assert result[0]["total_assets"] == Decimal("10001000")

    def test_total_liabilities_includes_temporary_equity(self):
        loader = self._make_loader()
        rows = [
            {
                "symbol": "SPACCO",
                "fiscal_year": 2024,
                "total_assets": Decimal("10001000"),
                "stockholders_equity": Decimal("-50000000"),
                "total_liabilities": None,
                "temporary_equity": Decimal("60000000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
            result = loader.transform(rows)

        assert result[0]["total_liabilities"] == Decimal("1000")

    def test_rejects_still_negative_total_assets_soun_fy2020(self):
        """SOUN FY2020's exact real inputs: even after including temporary_equity,
        the identity still yields a negative result (a pre-IPO SPAC formation-stage
        stub with no real Assets fact tagged) - must be left NULL, not stored."""
        loader = self._make_loader()
        rows = [
            {
                "symbol": "SOUN",
                "fiscal_year": 2020,
                "total_assets": None,
                "stockholders_equity": Decimal("-276353000"),
                "total_liabilities": Decimal("716"),
                "temporary_equity": Decimal("273687000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
            result = loader.transform(rows)

        assert result[0]["total_assets"] is None

    def test_rejects_still_negative_total_liabilities(self):
        loader = self._make_loader()
        rows = [
            {
                "symbol": "SOUN",
                "fiscal_year": 2020,
                "total_assets": Decimal("-276352284"),
                "stockholders_equity": Decimal("-276353000"),
                "total_liabilities": None,
                "temporary_equity": Decimal("273687000"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
            result = loader.transform(rows)

        assert result[0]["total_liabilities"] is None

    def test_missing_temporary_equity_defaults_to_zero(self):
        """Existing two-component filers (no mezzanine equity at all, e.g. BTTC/XLAB)
        must keep behaving exactly as before this fix."""
        loader = self._make_loader()
        rows = [
            {
                "symbol": "BTTC",
                "fiscal_year": 2025,
                "total_assets": None,
                "stockholders_equity": Decimal("-167120"),
                "total_liabilities": Decimal("167120"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
            result = loader.transform(rows)

        assert result[0]["total_assets"] == Decimal("0")
