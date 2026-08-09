"""Regression test: _insider_score() must query insider_transactions' real column names.

The original query referenced transaction_type/value/transaction_date - columns that
have never existed in any real insider_transactions table (its real schema is
trade_type/trade_price/trade_date/shares, no `value` column). Every call crashed with
UndefinedColumn. Fixed to compute dollar value as shares * trade_price against the real
column names. See migrations/versions/1146_add_missing_insider_earnings_tables.py for
the schema history.
"""

from datetime import date

from algo.signals.advanced_filters import AdvancedFilters

BASE_CONFIG = {
    "strong_sector_top_n": 5,
    "block_days_before_earnings": 5,
    "max_extension_above_50ma_pct": 15.0,
    "min_avg_daily_dollar_volume": 500_000,
    "require_strong_sector": False,
}


def test_insider_score_query_uses_real_column_names():
    filters = AdvancedFilters(dict(BASE_CONFIG))

    captured = {}

    class FakeCursor:
        def execute(self, query, params):
            captured["query"] = query
            captured["params"] = params

        def fetchone(self):
            return (1000.0, 0.0)

    filters._insider_score("AAPL", date(2026, 8, 7), FakeCursor())

    query = captured["query"]
    assert "trade_type" in query
    assert "trade_price" in query
    assert "trade_date" in query
    assert "transaction_type" not in query
    assert "transaction_date" not in query
    # value is computed as shares * trade_price, not read from a nonexistent `value` column
    assert "shares * trade_price" in query
