"""Regression test: /api/algo/trades must sort by exit date, not entry date.

lambda/api/routes/algo_handlers/dashboard.py::_get_algo_trades previously sorted
`ORDER BY trade_date DESC` (entry date), while the dashboard trade-history panels
(dashboard/panels/trades.py) display rows under an "Exit Date" column. Confirmed
live 2026-07-27 against the real algo_trades table: many closed trades share the
same trade_date (entry date) but close on different days, so entry-date sorting
produced a visibly scrambled Exit Date column (e.g. 07-24, 07-24, 07-27, 07-27,
07-24, 07-27, ...). Open trades have exit_date = NULL, so the fix must fall back
to trade_date for those rows rather than sorting NULLs unpredictably.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_algo_trades_query_orders_by_coalesced_exit_date():
    from routes.algo_handlers.dashboard import _get_algo_trades

    cursor = Mock()
    cursor.fetchall.return_value = []

    _get_algo_trades(cursor, limit=10)

    executed_sql = cursor.execute.call_args[0][0]
    assert "ORDER BY COALESCE(exit_date, trade_date) DESC" in executed_sql, (
        "Trades query must sort by exit date (falling back to trade_date for open "
        "positions), matching the Exit Date column shown in the dashboard panels. "
        f"Got: {executed_sql}"
    )
