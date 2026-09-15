"""Regression: options_data_loader.py's _select_symbols queried a nonexistent
`market_constituents` TABLE (that name is `loaders/load_market_constituents.py`'s own
filename, not a table - the real table it populates is `stock_symbols`) and, separately,
used SELECT DISTINCT with an ORDER BY expression not in the select list, which Postgres
rejects outright. Together these meant the loader's default daily-rotating-sample path
(anything not passing --symbols explicitly) crashed on every single invocation since the
loader was written - fixed 2026-09-12.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from scripts.options_data_loader import _select_symbols


class TestSelectSymbolsQueriesRealTable:
    def test_queries_stock_symbols_not_market_constituents(self):
        cur = MagicMock()
        cur.fetchall.return_value = [("AAPL",), ("MSFT",)]

        result = _select_symbols(cur, limit=2)

        sql = cur.execute.call_args[0][0]
        assert "market_constituents" not in sql
        assert "stock_symbols" in sql
        assert "active" in sql
        assert "is_sp500" in sql and "is_russell2000" in sql
        assert result == ["AAPL", "MSFT"]

    def test_order_by_expression_is_wrapped_in_a_subquery(self):
        """SELECT DISTINCT symbol ... ORDER BY md5(symbol || ...) is invalid Postgres unless
        the ORDER BY expression is pushed into an outer query over a DISTINCT subquery."""
        cur = MagicMock()
        cur.fetchall.return_value = []

        _select_symbols(cur, limit=10)

        sql = cur.execute.call_args[0][0]
        distinct_pos = sql.index("DISTINCT")
        order_by_pos = sql.index("ORDER BY")
        assert order_by_pos > distinct_pos
        assert "SELECT DISTINCT symbol" in sql
        assert sql.count("SELECT") >= 2, "ORDER BY on a derived expr needs an outer SELECT"
