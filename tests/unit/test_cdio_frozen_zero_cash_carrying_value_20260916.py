"""Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep,
our_value=0-vs-real-yfinance-value audit): CDIO (Cardio Diagnostics) and 3 other micro-cap
filers (FAC/INDO/AKTX) tag a permanently frozen $0 under the standard
"CashAndCashEquivalentsAtCarryingValue" concept across EVERY fiscal year on file
(2021-2025 for CDIO, live-confirmed via real SEC companyfacts JSON), while their real,
evolving cash balance sits entirely under the combined
"CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents" concept
($5,110,630 FY2025 for CDIO, exactly matching the yfinance-flagged value).

sec_balance_sheet.py's own design deliberately lists the combined concept BEFORE the
standard one so the standard concept - assumed more authoritative - wins via ordinary
last-processed-wins when a filer reports both. That assumption breaks when the "more
authoritative" concept is a boilerplate frozen $0, not a real distinguishing fact - the
standard concept's $0 unconditionally overwrote the real combined total. Same "$0 of one
narrow category must not clobber an already-resolved nonzero total" pattern as the
CMCT preferred/common dividend fix - extended to cash_and_equivalents.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestCdioFrozenZeroCashCarryingValueFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "cash_and_equivalents", "data_unavailable", "reason"})
        loader._field_mapping = {
            "cash_and_equivalents": "cash_and_equivalents",
            "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents": "cash_and_equivalents",
            "cash_and_cash_equivalents_at_carrying_value": "cash_and_equivalents",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_frozen_zero_carrying_value_never_overwrites_the_real_combined_total(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "CDIO",
            "fiscal_year": 2025,
            "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents": 5_110_630.0,
            "cash_and_cash_equivalents_at_carrying_value": 0.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["cash_and_equivalents"] == 5_110_630.0

    def test_nonzero_carrying_value_still_wins_as_normal(self) -> None:
        """A genuinely nonzero, more-standard carrying-value concept must still win last -
        this fix only blocks a literal $0 from clobbering an already-resolved nonzero
        value.
        """
        loader = self._make_loader()
        row = {
            "symbol": "TEST",
            "fiscal_year": 2025,
            "cash_cash_equivalents_restricted_cash_and_restricted_cash_equivalents": 5_000_000.0,
            "cash_and_cash_equivalents_at_carrying_value": 4_500_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["cash_and_equivalents"] == 4_500_000.0
