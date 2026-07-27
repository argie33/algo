#!/usr/bin/env python3
"""Regression test: PositionSyncChecker's data integrity queries must cover every live
trade status, not just ('open','filled','partially_filled','active').

The checker previously omitted 'pending'/'paper_pending' from every "is this trade open"
filter - exactly the two statuses a trade sits in before its first broker confirmation,
which is also when it's most likely to have missing/invalid entry data. A trade stuck in
one of those statuses with bad data would silently never be flagged.
"""

from unittest.mock import MagicMock

from utils.ops.position_sync import PositionSyncChecker
from utils.trading import TradeStatus


def test_every_open_trade_query_covers_all_live_statuses():
    checker = PositionSyncChecker()
    cur = MagicMock()
    cur.fetchall.return_value = []
    cur.fetchone.return_value = (0, 0, 0)

    checker._do_check(cur)

    open_trade_queries = [
        c.args[0] for c in cur.execute.call_args_list if "FROM algo_trades" in c.args[0] or "algo_trades" in c.args[0]
    ]
    queries_with_status_filter = [q for q in open_trade_queries if "status IN" in q]
    assert queries_with_status_filter, "expected at least one status IN (...) filter against algo_trades"

    for query in queries_with_status_filter:
        for status in TradeStatus.all_open():
            assert f"'{status}'" in query, f"expected {status!r} in query: {query[:200]}"
