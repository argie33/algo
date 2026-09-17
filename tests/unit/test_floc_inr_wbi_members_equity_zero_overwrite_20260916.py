"""Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep,
our_value=0-vs-real-yfinance-value audit): FLOC, INR, and WBI all tag a real, correct
"StockholdersEquity" ($228,626,000/$307,139,000/$602,306,000 respectively, all exactly
matching the yfinance-flagged value, live-confirmed via real SEC companyfacts JSON) AND a
boilerplate "MembersEquity"=0 for the same fiscal year.

"MembersEquity" is meant to be the direct LLC-legal-structure analogue of
StockholdersEquity, assumed mutually exclusive in practice (an LLC never also tags
StockholdersEquity - see sec_balance_sheet.py's own comment on "MembersEquity"). All 3 of
these filers break that assumption, and since MembersEquity is processed after
StockholdersEquity in the concept list, its own real $0 fact unconditionally overwrote the
correct total via ordinary last-processed-wins.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestFlocInrWbiMembersEquityZeroOverwriteFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "stockholders_equity", "data_unavailable", "reason"})
        loader._field_mapping = {
            "stockholders_equity": "stockholders_equity",
            "members_equity": "stockholders_equity",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_zero_members_equity_never_overwrites_the_real_stockholders_equity(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "FLOC",
            "fiscal_year": 2025,
            "stockholders_equity": 228_626_000.0,
            "members_equity": 0.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["stockholders_equity"] == 228_626_000.0

    def test_nonzero_members_equity_still_overwrites_as_normal(self) -> None:
        """A genuinely nonzero MembersEquity concept must still win as intended for the real
        LLC case - this fix only blocks a literal $0 from clobbering an already-resolved
        nonzero value.
        """
        loader = self._make_loader()
        row = {
            "symbol": "TEST",
            "fiscal_year": 2025,
            "stockholders_equity": 100_000_000.0,
            "members_equity": 250_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["stockholders_equity"] == 250_000_000.0
