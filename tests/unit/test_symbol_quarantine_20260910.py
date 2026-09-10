"""Tests for algo/monitoring/data_patrol/quarantine.py (migration 1277, goal session
2026-09-10: per-symbol quarantine so a CRIT/ERROR finding attributable to specific symbols
doesn't halt the whole Phase 1 run for the entire universe).
"""

from unittest.mock import MagicMock, call

from algo.monitoring.data_patrol.quarantine import apply_symbol_quarantine


class TestApplySymbolQuarantine:
    def test_flags_symbols_resolves_previous_and_marks_stock_scores_unavailable(self):
        cur = MagicMock()

        apply_symbol_quarantine(
            cur,
            "ohlc_sanity",
            "critical",
            "run-1",
            [{"symbol": "AAA", "reason": "negative OHLC price"}],
        )

        executed_sql = [c.args[0] for c in cur.execute.call_args_list]
        assert any(
            "UPDATE symbol_quarantine" in sql and "resolved_at = CURRENT_TIMESTAMP" in sql for sql in executed_sql
        )
        assert any("UPDATE stock_scores" in sql and "data_unavailable = TRUE" in sql for sql in executed_sql)
        insert_call = cur.executemany.call_args
        assert "INSERT INTO symbol_quarantine" in insert_call.args[0]
        assert insert_call.args[1] == [("AAA", "ohlc_sanity", "critical", "negative OHLC price", "run-1")]

    def test_no_symbols_resolves_all_open_flags_for_check_and_releases_stock_scores(self):
        cur = MagicMock()

        apply_symbol_quarantine(cur, "ohlc_sanity", "critical", "run-2", [])

        executed_sql = [c.args[0] for c in cur.execute.call_args_list]
        assert any(
            "UPDATE symbol_quarantine" in sql and "WHERE resolved_at IS NULL AND check_name = %s" in sql
            for sql in executed_sql
        )
        release_calls = [c for c in cur.execute.call_args_list if "data_unavailable = FALSE" in c.args[0]]
        assert len(release_calls) == 1
        assert release_calls[0].args[1] == ("quarantined: ohlc_sanity", [""])
        # No new INSERT when nothing is currently flagged
        cur.executemany.assert_not_called()

    def test_release_query_never_touches_symbols_flagged_by_another_check(self):
        cur = MagicMock()

        apply_symbol_quarantine(cur, "ohlc_sanity", "error", "run-3", [{"symbol": "BBB", "reason": "bad OHLC"}])

        release_calls = [c for c in cur.execute.call_args_list if "data_unavailable = FALSE" in c.args[0]]
        assert len(release_calls) == 1
        sql, params = release_calls[0].args
        assert "NOT EXISTS" in sql
        assert params == ("quarantined: ohlc_sanity", ["BBB"])
