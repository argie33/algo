#!/usr/bin/env python3
"""Regression test for a dead-code bug in dashboard/panels/signals.py's _build_funnel_row -
found in the same investigation as [[trades_panel_exit_reason_52pct_unresolved_fixed_20260824]]
and [[health_panel_notif_short_names_critical_alerts_fixed_20260824]].

The panel expected funnel["rejected"] to be a LIST of {evaluation_reason, n, description}
per-reason breakdown objects, but lambda/api/routes/algo_handlers/signals.py's
_get_rejection_funnel (the only real source of this field) has only ever returned `rejected`
as a plain int count (`max(0, total - t1)`), never a per-reason list - per that function's own
docstring, a prior "SWING SCORE MIGRATION" changed the funnel to composite_score tiers and
apparently never carried the old per-reason breakdown forward. safe_get_list() on an int
returns a data_unavailable marker dict, not a list, so the entire "blocked: reason:N (...)"
breakdown block was silently unreachable dead code - not wrong information, just a feature
that was never actually wired to real data. Replaced with a display of the real, currently-
available rejected count instead. The dead _shorten_reason/_shorten_type helper functions
(only ever called from the removed dead-list-parsing code) were removed alongside it.
"""

from dashboard.panels.signals import _build_funnel_row


class TestBuildFunnelRowRejectedCount:
    def test_nonzero_rejected_count_is_shown(self):
        sig_eval = {"total": 100, "t1": 60, "t2": 40, "t3": 25, "t4": 12, "t5": 8, "avg_score": 62.5, "rejected": 40}
        rows = _build_funnel_row(sig_eval)
        assert len(rows) == 1
        assert "rejected: 40" in rows[0].plain

    def test_zero_rejected_count_omits_the_segment(self):
        sig_eval = {"total": 100, "t1": 100, "t2": 40, "t3": 25, "t4": 12, "t5": 8, "avg_score": 62.5, "rejected": 0}
        rows = _build_funnel_row(sig_eval)
        assert len(rows) == 1
        assert "rejected" not in rows[0].plain

    def test_missing_rejected_field_does_not_crash(self):
        sig_eval = {"total": 100, "t1": 60, "t2": 40, "t3": 25, "t4": 12, "t5": 8, "avg_score": 62.5}
        rows = _build_funnel_row(sig_eval)
        assert len(rows) == 1
        assert "rejected" not in rows[0].plain

    def test_full_funnel_chain_still_renders(self):
        sig_eval = {"total": 100, "t1": 60, "t2": 40, "t3": 25, "t4": 12, "t5": 8, "avg_score": 62.5, "rejected": 40}
        rows = _build_funnel_row(sig_eval)
        assert "100" in rows[0].plain
        assert "60" in rows[0].plain
        assert "8" in rows[0].plain
