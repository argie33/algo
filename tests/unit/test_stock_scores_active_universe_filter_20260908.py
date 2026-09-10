"""Regression test: /api/scores had no active-universe filter at all.

Live-verified (goal session score-sanity sweep, 2026-09-08): 3 delisted/deactivated
symbols (TOI, KORE, PSNYW) cleared every existing filter in
scores_handlers/stock_scores.py's where_clause (ETF exclusion, SIC-code exclusion,
has_annual_report_filing, security-name patterns, data_unavailable) and would still
render on the live leaderboard with a plausible composite_score - indistinguishable
from a real tradeable idea. The scores loader intentionally keeps scoring inactive
symbols (last-known-state bookkeeping), but this user-facing endpoint should only
ever surface the current tradeable universe.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _mock_cursor():
    cursor = Mock()
    cursor.fetchone.return_value = [0]
    cursor.fetchall.return_value = []
    return cursor


class TestStockScoresActiveUniverseFilter:
    def test_bulk_query_filters_to_active_symbols_only(self):
        from routes.scores_handlers.stock_scores import _get_stock_scores

        cursor = _mock_cursor()
        _get_stock_scores(cursor, limit=10, offset=0)

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert any("ss.active = true" in sql for sql in executed_queries)

    def test_single_symbol_query_also_filters_to_active(self):
        """Consistent with this same where_clause's existing ETF/SIC-code/security-name
        filters, which already apply unconditionally even to a single ?symbol= lookup."""
        from routes.scores_handlers.stock_scores import _get_stock_scores

        cursor = _mock_cursor()
        _get_stock_scores(cursor, limit=10, offset=0, symbol="TOI")

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert any("ss.active = true" in sql for sql in executed_queries)
