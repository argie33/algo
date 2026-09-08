"""Regression test: /api/algo/scores' tradability floor (market cap + liquidity).

Added 2026-09-07 (/goal session, "I don't know any of these stocks... reloads keep
failing"). This dashboard endpoint (the TUI dashboard's actual "top stocks" panel,
dashboard/fetchers_signals.py's fetch_scores -> /api/algo/scores) had NO investability
screen at all, unlike the separate /api/scores endpoint which got a minMarketCap opt-in
param on 2026-08-31 - that fix never reached this handler. Live-verified the top of the
composite_score ranking included JFIN ($43M market cap), XYF ($114M), KINS ($278M), and
CIG.C ($3.1B market cap but only ~$10K/day average dollar volume - a real company whose
US ADR listing is functionally untradeable). Fixed by reusing the SAME thresholds that
already gate real trade eligibility (algo_config min_market_cap_millions/min_adv_dollars,
algo/risk/liquidity_checks.py) rather than a new number, applied unconditionally (unlike
the opt-in /api/scores param) since this endpoint IS specifically a "best picks" panel,
not a general searchable table.

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
    """Fake cursor that routes fetchone/fetchall by the executed SQL text."""
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


class TestDashboardScoresTradabilityFloor:
    def test_query_filters_by_market_cap_and_liquidity(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor()
        _get_dashboard_scores(cursor, limit=50)

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert any("vm.market_cap" in sql for sql in executed_queries)
        assert any("liq.avg_dollar_volume_20d" in sql for sql in executed_queries)

    def test_uses_configured_thresholds(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor(
            config_rows=[
                ("min_market_cap_millions", "300.0"),
                ("min_adv_dollars", "500000"),
            ]
        )
        _get_dashboard_scores(cursor, limit=50)

        all_params = [p for c in cursor.execute.call_args_list for p in (c.args[1] if len(c.args) > 1 else []) or []]
        assert 300_000_000.0 in all_params
        assert 500_000.0 in all_params

    def test_falls_back_to_safe_defaults_when_config_missing(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor(config_rows=[])
        _get_dashboard_scores(cursor, limit=50)

        all_params = [p for c in cursor.execute.call_args_list for p in (c.args[1] if len(c.args) > 1 else []) or []]
        assert 300_000_000.0 in all_params
        assert 500_000.0 in all_params
