"""Regression test: /api/scores/incomplete sortOrder param was raw-interpolated into SQL.

Unlike the sibling /api/scores endpoint (which whitelists sort_by/sort_order before
ever building a query - see handle()'s `if sort_order not in ["asc", "desc"]` check),
_get_incomplete_stocks built its ORDER BY clause with an f-string directly containing
the caller-supplied sort_order with no validation:
    sort_clause = f"ORDER BY data_completeness {sort_order}, symbol ASC"
Since sort_order came straight from the `sortOrder` query param (only `.lower()`'d),
this was an exploitable SQL injection via ORDER BY clause manipulation. Fixed by
whitelisting at the handle() call site and mapping to a fixed SQL keyword inside
_get_incomplete_stocks itself, matching the safe pattern already used elsewhere in
this file (see routes/scores.py's `sort_direction = "DESC" if sort_order == "desc"
else "ASC"` in the main _get_stock_scores query).

Also covers a second bug in the same summary block: "meeting_trading_gate" used a
falsy check (`if completeness_threshold_pct else None`) instead of `is not None`, so
a legitimate "0% of returned scores meet the trading gate" result - an important,
alarming signal - silently collapsed to None, indistinguishable from "no completeness
data available at all".
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _mock_cursor(rows):
    cursor = Mock()
    cursor.fetchone.return_value = [len(rows)]
    # _get_stock_scores's default (2026-09-15) IBD-style liquidity screen runs a first,
    # separate `SELECT key, value FROM algo_config ...` fetchall (tuple rows, `row[0]`/`row[1]`
    # indexed) before the main results fetchall - only reachable via handle()'s main "/api/
    # scores" path, not _get_incomplete_stocks (which never joins that query and only ever
    # makes one fetchall call). Returning [] for that first call falls back to this function's
    # own hardcoded defaults (see its except KeyError/TypeError/ValueError branches) rather
    # than crashing on a dict row's `[0]` access.
    #
    # SECOND fetchall added 2026-09-17 (migration 1308 - tilt weight computed at request time,
    # not a stored column): the tilt-weight population query (algo/signals/market_cap_tilt.py)
    # runs between the count query and the main results query - empty population here is fine,
    # it just means every *_tilted_weight comes back None (compute_tilted_weights({}, {})).
    # `rows` (the real payload, possibly dict rows) is returned on the actual results fetchall.
    cursor.fetchall.side_effect = [[], [], rows]
    return cursor


class TestIncompleteStocksSortOrderInjection:
    def test_handle_rejects_non_whitelisted_sort_order_before_query(self):
        from routes.scores import handle

        cursor = _mock_cursor([])
        handle(
            cursor,
            "/api/scores/incomplete",
            "GET",
            {"sortOrder": "asc; DROP TABLE stock_scores;--", "sortBy": "data_completeness"},
        )

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        for sql in executed_queries:
            assert "DROP TABLE" not in sql
            assert ";--" not in sql

    def test_get_incomplete_stocks_maps_unexpected_sort_order_to_fixed_keyword(self):
        from routes.scores import _get_incomplete_stocks

        cursor = _mock_cursor([])
        # Simulate a caller that skips handle()'s whitelist (defense in depth).
        _get_incomplete_stocks(
            cursor, limit=10, offset=0, sort_by="data_completeness", sort_order="asc; DROP TABLE stock_scores;--"
        )

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert any("ORDER BY data_completeness ASC" in sql for sql in executed_queries)
        for sql in executed_queries:
            assert "DROP TABLE" not in sql


class TestMeetingTradingGateZeroNotCollapsedToNone:
    def test_zero_percent_meeting_gate_reported_as_zero_not_none(self):
        from routes.scores import handle

        # All returned items have data_completeness > 0 but below the 70% trading gate,
        # so trading_gate_count == 0 and completeness_threshold_pct == 0.0 exactly.
        rows = [
            {
                "symbol": "AAA",
                "composite_score": 50,
                "data_completeness": 40,
                "current_price": 10.0,
            },
        ]
        cursor = _mock_cursor(rows)
        response = handle(cursor, "/api/scores", "GET", {})

        assert response["data"]["data_health"]["meeting_trading_gate"] == "0%"
