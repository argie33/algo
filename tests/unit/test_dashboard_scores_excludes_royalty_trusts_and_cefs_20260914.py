"""Regression test: /api/algo/scores returns raw, unfiltered stock_scores rows.

SUPERSEDED 2026-09-18 (user directive: "it should not filter it should show the raw results
from the table"). This test file originally asserted the OPPOSITE - that this endpoint joined
`stock_symbols` and spliced in `investable_universe_conditions()` (SIC-based royalty-trust/
SPAC/CEF exclusion) to keep bad-quality names like PBT/TPL/SBR off the leaderboard (see git
history on this file for that original regression's full writeup, 2026-09-14). That filter,
along with every other default eligibility screen this endpoint used to apply, was removed
2026-09-18: a stock_scores row that fails an investability/data-quality check is still a REAL
row in the table, and hiding it from this endpoint by default is exactly the "why don't I see
this symbol" confusion the newer directive rejects. A caller who specifically wants an
investable-only view can apply that filtering client-side or via a future explicit opt-in
param - it is no longer this endpoint's default behavior.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api" / "routes"))


def _mock_cursor():
    cursor = Mock()
    cursor.fetchall.return_value = []
    cursor.fetchone.side_effect = lambda: None
    return cursor


class TestDashboardScoresNoDefaultInvestabilityFilter:
    def test_main_query_has_no_investable_universe_filter(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor()
        _get_dashboard_scores(cursor, limit=50)

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        main_query = next(sql for sql in executed_queries if "FROM stock_scores s" in sql and "filtered_scores" in sql)
        # investable_universe_conditions() output - the SIC-based royalty-trust/SPAC/CEF
        # exclusion this file used to require - must NOT be present any more.
        assert "6792" not in main_query, "SIC 6792 (Oil Royalty Traders) exclusion should be gone"
        assert "has_annual_report_filing" not in main_query
        assert "company_info_sec" not in main_query
