"""Regression test: /api/algo/scores applies no default liquidity/tradability screen.

SUPERSEDED 2026-09-18 (user directive: "it should not filter it should show the raw results
from the table"). This test file originally asserted the OPPOSITE - that this endpoint
applied an IBD-style liquidity screen (algo_config min_stock_price/min_adv_dollars) as its
default investability floor (see git history on this file for that original regression's full
writeup, 2026-09-07/09-16). That screen, along with every other default eligibility filter
this endpoint used to apply, was removed 2026-09-18: a stock_scores row that fails a
liquidity check is still a REAL row in the table, and hiding it from this endpoint by default
is exactly the "why don't I see this symbol" confusion the newer directive rejects.

Routes fake cursor responses by matching on the rendered SQL text, not call order/fixed
shape - see [[watermark_desync_test_fixture_fix_20260907]] in memory for why a
fixed-shape-per-call mock breaks the moment a new query is added to the handler.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api" / "routes"))


def _mock_cursor():
    """Fake cursor that routes fetchone/fetchall by the executed SQL text."""
    cursor = Mock()

    def fake_fetchall():
        return []

    def fake_fetchone():
        sql = cursor.execute.call_args.args[0]
        if "universe_total" in sql:
            return [0, None, 0, 0, 0, 0]
        if "null_count" in sql:
            return [0, 0]
        return None

    cursor.fetchall.side_effect = fake_fetchall
    cursor.fetchone.side_effect = fake_fetchone
    return cursor


class TestDashboardScoresNoDefaultLiquidityFloor:
    def test_query_has_no_liquidity_screen(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor()
        _get_dashboard_scores(cursor, limit=50)

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert not any("liq.latest_close" in sql for sql in executed_queries)
        assert not any("liq.avg_dollar_volume_20d" in sql for sql in executed_queries)

    def test_does_not_read_liquidity_config(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor()
        _get_dashboard_scores(cursor, limit=50)

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert not any("FROM algo_config" in sql for sql in executed_queries)
