"""Regression test for loaders/load_dividend_data.py's primary_key declaration.

A prior version declared primary_key = ("symbol", "ex_dividend_date", "dividend_per_share"),
a 3-column key that never matched migration 1155's real uq_dividend_event constraint
(UNIQUE(symbol, ex_dividend_date), 2 columns) - see migration 1168. Two live bugs resulted:

1. OptimalLoader._validate_row() treats every primary_key column as required/non-NULL, so
   the loader's own intentional data_unavailable marker (dividend_per_share=None by design -
   most symbols simply don't pay a dividend) crashed for the vast majority of the universe.
2. BulkInsertManager's runtime self-healing auto-created a second, conflicting unique
   constraint matching the wrong 3-column declaration, causing ON CONFLICT to miss real
   duplicates against the actual 2-column constraint (live-reproduced: symbol APOG,
   ex_dividend_date 2024-10-15 raised psycopg2.errors.UniqueViolation).
"""

from datetime import date

from loaders.load_dividend_data import DividendDataLoader


class TestPrimaryKeyMatchesSchema:
    def test_primary_key_matches_uq_dividend_event(self):
        assert DividendDataLoader.table_name == "dividend_data"
        assert DividendDataLoader.primary_key == ("symbol", "ex_dividend_date")

    def test_validate_row_accepts_data_unavailable_marker_with_null_dividend_per_share(self):
        loader = DividendDataLoader.__new__(DividendDataLoader)
        marker = {
            "symbol": "ANVS",
            "declaration_date": None,
            "ex_dividend_date": date(2026, 7, 27),
            "record_date": None,
            "payment_date": None,
            "dividend_per_share": None,
            "dividend_yield_pct": None,
            "total_dividend_amount": None,
            "dividend_type": None,
            "currency": "USD",
            "data_unavailable": True,
            "data_unavailable_reason": "no_dividend_xbrl_concepts",
            "source": "NONE",
        }
        assert loader._validate_row(marker) is True

    def test_validate_row_still_requires_symbol_and_ex_dividend_date(self):
        loader = DividendDataLoader.__new__(DividendDataLoader)
        row = {"symbol": "AAPL", "ex_dividend_date": None, "dividend_per_share": None}
        try:
            loader._validate_row(row)
            raised = False
        except ValueError:
            raised = True
        assert raised, "ex_dividend_date is a real PK column and must still be required"
