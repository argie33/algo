"""Regression test: /api/algo/scores excludes inactive symbols and structurally-frozen BDCs.

Added 2026-09-08 (/goal session, score-sanity sweep). This dashboard endpoint (the TUI
dashboard's actual "top stocks" panel, dashboard/fetchers_signals.py's fetch_scores ->
/api/algo/scores) had neither an `ss.active` check nor the BDC exclusion already shipped to
the separate /api/scores endpoint (scores_handlers/stock_scores.py) the same day for the
identical failure - live-verified LIEN (a BDC frozen at its 2026-09-03 stock_scores snapshot,
see utils/loaders/helpers.py's get_active_symbols() BDC exclusion) ranked in today's
(2026-09-08) top-25 composite leaderboard on this endpoint, indistinguishable from a live
score. Same "fix landed on the wrong endpoint" gap as this file's own tradability-floor fix.

Routes fake cursor responses by matching on the rendered SQL text, not call order/fixed
shape - see [[watermark_desync_test_fixture_fix_20260907]] in memory for why a
fixed-shape-per-call mock breaks the moment a new query is added to the handler.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api" / "routes"))


def _mock_cursor(config_rows=None):
    cursor = Mock()
    config_rows = (
        config_rows
        if config_rows is not None
        else [
            ("min_market_cap_millions", "300.0"),
            ("min_adv_dollars", "500000"),
        ]
    )

    def fake_fetchall():
        sql = cursor.execute.call_args.args[0]
        if "FROM algo_config" in sql:
            return config_rows
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


class TestDashboardScoresActiveAndBdcFilter:
    def test_main_leaderboard_filters_inactive_and_bdc_symbols(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor()
        _get_dashboard_scores(cursor, limit=50)

        executed = [(c.args[0], c.args[1] if len(c.args) > 1 else None) for c in cursor.execute.call_args_list]
        main_query = next(sql for sql, _ in executed if "filtered_scores" in sql)
        assert "ss.active = true" in main_query
        assert "JOIN stock_symbols ss ON ss.symbol = s.symbol" in main_query
        assert "s.symbol NOT IN %s" in main_query

        main_params = next(params for sql, params in executed if "filtered_scores" in sql)
        bdc_tuple = main_params[0]
        assert "MAIN" in bdc_tuple
        assert "HTGC" in bdc_tuple

    def test_sp500_subleaderboard_filters_inactive_and_bdc_symbols(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor()
        _get_dashboard_scores(cursor, limit=50)

        executed = [(c.args[0], c.args[1] if len(c.args) > 1 else None) for c in cursor.execute.call_args_list]
        sp500_query = next(sql for sql, _ in executed if "is_sp500" in sql)
        assert "ss.active = true" in sp500_query
        assert "s.symbol NOT IN %s" in sp500_query

    def test_summary_query_filters_inactive_and_bdc_symbols(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor()
        _get_dashboard_scores(cursor, limit=50)

        executed = [c.args[0] for c in cursor.execute.call_args_list]
        summary_query = next(sql for sql in executed if "universe_total" in sql)
        assert "ss.active = true" in summary_query
        assert "JOIN stock_symbols ss ON ss.symbol = s.symbol" in summary_query
