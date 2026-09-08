"""Regression test: /api/scores still surfaced 29 structurally-excluded BDCs.

Live-verified (goal session score-sanity sweep, 2026-09-08): utils/loaders/helpers.py's
get_active_symbols() has excluded _KNOWN_BDC_ENTITY_TYPE_OPERATING_SYMBOLS (MAIN, HTGC, GAIN,
TSLX and 26 siblings) from every metrics/scores loader since 2026-09-03 - BDCs are
"structurally unable to report interest_coverage/total_debt/free_cash_flow/etc. the way an
operating company does". Consequence: those symbols' stock_scores rows never get touched again
after that date, but `ss.active` stays true (they're still real, tradeable BDCs), so they sailed
straight through this endpoint's active-universe filter with a plausible-looking composite_score
that is actually a permanently frozen snapshot - same failure shape as the delisted-symbol bug
this same where_clause was just fixed for.
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


class TestStockScoresBdcStructuralExclusion:
    def test_bulk_query_excludes_known_bdc_symbols(self):
        from routes.scores_handlers.stock_scores import _get_stock_scores

        cursor = _mock_cursor()
        _get_stock_scores(cursor, limit=10, offset=0)

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert any("'MAIN'" in sql and "'HTGC'" in sql for sql in executed_queries)
