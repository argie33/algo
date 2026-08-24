"""Regression: sector rankings showed the 1-week rank delta labeled as 4-week.

BUG FOUND 2026-08-24 (real-money-readiness goal, dashboard.py panel sweep): _rdelta()
(dashboard/panels/sectors.py) accepted a `wk4` parameter but never referenced it in the
function body - every caller passing wk4="rank_4w_ago" for sector rankings (both the compact
"SECTORS & INDUSTRIES" panel and the full-screen expanded view) silently got the 1-week delta
computed off the default `wk="rank_1w_ago"` instead, even though the panel's own header text
explicitly says "rank change vs 1wk/4wk". Industries intentionally use only the 1-week field
(their own header says "↑↓1wk") and are unaffected by this bug.
"""

from dashboard.panels.sectors import _rdelta


class TestRankDeltaUsesRequestedWindow:
    def test_wk4_argument_is_actually_used_not_ignored(self):
        # current_rank=5, rank_1w_ago=5 (no 1wk change), rank_4w_ago=10 (moved up 5 over 4wk).
        # If wk4 were silently ignored (the bug), this would render "--" or "→" from the
        # unchanged 1wk field instead of the real 4wk move.
        row = {"current_rank": 5, "rank_1w_ago": 5, "rank_4w_ago": 10}

        result_1wk = _rdelta(row)
        result_4wk = _rdelta(row, wk4="rank_4w_ago")

        assert result_1wk == "→", f"expected no-change arrow from rank_1w_ago, got {result_1wk!r}"
        assert result_4wk == "↑5", f"expected +5 upward move from rank_4w_ago, got {result_4wk!r}"

    def test_default_1wk_behavior_unchanged_for_industries(self):
        row = {"current_rank": 3, "rank_1w_ago": 5}
        assert _rdelta(row) == "↑2"
