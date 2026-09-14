"""Regression test for coverage_correctness.py's status classification (goal session
2026-09-14: "fix the data issues we still have" - live-caught the dashboard showing
dividend_data/market_health_daily/sec_valuations as "Findings open" hours after DataPatrol had
already logged them clean).

_classify_status used to receive a 30-day trailing-window occurrence count (`recent`), so a
table that WARNed once during the window and came back clean on every later run still showed
"active_findings" for the rest of the window. It must instead reflect CURRENT state
(data_patrol_log.status = 'open'), which logger.py's PatrolLogger.log_results already maintains
via resolve-on-reinsert.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from routes.scores_handlers.coverage_correctness import _classify_status


class TestClassifyStatusUsesCurrentlyOpen:
    def test_table_fixed_earlier_in_window_is_clean_not_active_findings(self):
        # A WARN fired hours ago and is now resolved - only an INFO row is currently open.
        currently_open = {"critical": 0, "error": 0, "warn": 0, "info": 1}
        assert _classify_status(total_ever=5, days_since_last=0.1, currently_open=currently_open) == "active_clean"

    def test_table_with_a_currently_open_warn_is_active_findings(self):
        currently_open = {"critical": 0, "error": 0, "warn": 1, "info": 0}
        assert _classify_status(total_ever=5, days_since_last=0.1, currently_open=currently_open) == "active_findings"

    def test_never_logged_wins_over_currently_open_shape(self):
        assert (
            _classify_status(
                total_ever=0, days_since_last=None, currently_open={"critical": 0, "error": 0, "warn": 0, "info": 0}
            )
            == "never_logged"
        )

    def test_stale_wins_over_currently_open_when_beyond_lookback(self):
        currently_open = {"critical": 0, "error": 1, "warn": 0, "info": 0}
        assert _classify_status(total_ever=5, days_since_last=45.0, currently_open=currently_open) == "stale"
