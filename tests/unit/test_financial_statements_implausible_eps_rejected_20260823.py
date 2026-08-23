"""Regression test for the 2026-08-23 implausible-EPS rejection guard.

Live DB audit (goal: real-money-readiness audit) found earnings_per_share values in
annual_income_statement that are confidently wrong, not currency/scale artifacts:
GIBO's real SEC companyfacts JSON tags EarningsPerShareBasic under the correct
"USD/shares" unit but with the SAME raw value as that year's NetIncomeLoss
(FY2023/FY2024: both exactly -12,117,569 / -24,852,333) - the filer's own XBRL
reports total net income as if it were per-share. Also confirmed on BTTC, HQ, GROY,
BRUN, and EP's FY2013/2014 (eps == net_income exactly), 108 distinct symbols total
with |eps| > $1,000. No downstream consumer (growth_metrics' eps_growth_*) reliably
catches this - the YoY ratio between two similarly-corrupted years can look like an
ordinary percentage.

ConsolidatedFinancialStatementsLoader.transform() (statement_type="income") now nulls
earnings_per_share/diluted_eps when net_income implies fewer than 10,000 shares
outstanding - a floor comfortably below any real filer (BRK.A ~1.6M shares, BSAC
~471M, EC ~2.06B all clear it).
"""

from decimal import Decimal
from unittest.mock import patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


class TestImplausibleEpsRejected:
    def _make_loader(self) -> ConsolidatedFinancialStatementsLoader:
        return ConsolidatedFinancialStatementsLoader(statement_type="income", period="annual")

    def _transform(self, loader, rows):
        with patch.object(ConsolidatedFinancialStatementsLoader.__mro__[1], "transform", side_effect=lambda r: r):
            return loader.transform(rows)

    def test_rejects_eps_exactly_equal_to_net_income(self):
        loader = self._make_loader()
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
        result = self._transform(loader, rows)
        assert result[0]["earnings_per_share"] is None
        # revenue/net_income still present -> not a "no data at all" row
        assert result[0]["data_unavailable"] is False

    def test_rejects_thousands_scale_variant(self):
        loader = self._make_loader()
        rows = [
            {
                "symbol": "FLOC",
                "fiscal_year": 2022,
                "revenue": Decimal("50000000"),
                "net_income": Decimal("32729000"),
                "earnings_per_share": Decimal("32729"),
                "diluted_eps": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = self._transform(loader, rows)
        assert result[0]["earnings_per_share"] is None

    def test_keeps_real_high_priced_stock_eps(self):
        """BRK.A: real ~1.6M shares outstanding, legitimately four-figure EPS."""
        loader = self._make_loader()
        rows = [
            {
                "symbol": "BRK.A",
                "fiscal_year": 2013,
                "revenue": Decimal("182150000000"),
                "net_income": Decimal("19476000000"),
                "earnings_per_share": Decimal("2977.00"),
                "diluted_eps": Decimal("2977.00"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = self._transform(loader, rows)
        assert result[0]["earnings_per_share"] == Decimal("2977.00")

    def test_keeps_real_foreign_currency_eps(self):
        """EC (Ecopetrol): reports in COP, net_income in the trillions, ~2.06B shares."""
        loader = self._make_loader()
        rows = [
            {
                "symbol": "EC",
                "fiscal_year": 2022,
                "revenue": Decimal("120000000000000"),
                "net_income": Decimal("31604781000000"),
                "earnings_per_share": Decimal("16249.3606"),
                "diluted_eps": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = self._transform(loader, rows)
        assert result[0]["earnings_per_share"] == Decimal("16249.3606")

    def test_does_not_fire_for_balance_statement_type(self):
        loader = ConsolidatedFinancialStatementsLoader(statement_type="balance", period="annual")
        rows = [
            {
                "symbol": "GIBO",
                "fiscal_year": 2024,
                "total_assets": Decimal("1000000"),
                "stockholders_equity": Decimal("500000"),
                "net_income": Decimal("-24852333"),
                "earnings_per_share": Decimal("-24852333"),
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = self._transform(loader, rows)
        # earnings_per_share isn't a real balance-sheet field; guard is income-only.
        assert result[0]["earnings_per_share"] == Decimal("-24852333")

    def test_leaves_null_eps_untouched(self):
        loader = self._make_loader()
        rows = [
            {
                "symbol": "NEWCO",
                "fiscal_year": 2026,
                "revenue": Decimal("1000000"),
                "net_income": Decimal("-500000"),
                "earnings_per_share": None,
                "diluted_eps": None,
                "data_unavailable": False,
                "reason": None,
            }
        ]
        result = self._transform(loader, rows)
        assert result[0]["earnings_per_share"] is None
