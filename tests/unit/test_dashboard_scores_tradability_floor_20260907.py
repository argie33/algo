"""Regression test: /api/algo/scores' tradability floor (liquidity screen).

Added 2026-09-07 (/goal session, "I don't know any of these stocks... reloads keep
failing"). This dashboard endpoint (the TUI dashboard's actual "top stocks" panel,
dashboard/fetchers_signals.py's fetch_scores -> /api/algo/scores) had NO investability
screen at all, unlike the separate /api/scores endpoint which got a minMarketCap opt-in
param on 2026-08-31 - that fix never reached this handler. Live-verified the top of the
composite_score ranking included JFIN ($43M market cap), XYF ($114M), KINS ($278M), and
CIG.C ($3.1B market cap but only ~$10K/day average dollar volume - a real company whose
US ADR listing is functionally untradeable). Originally fixed with a market-cap floor
(algo_config min_market_cap_millions).

REPLACED 2026-09-16 (/goal session: "filtering in place in python dashboard.py scores...
different scores there vs http://localhost:5173/app/scores") - this endpoint's market-cap
floor was live-diverging from lambda/api/routes/scores_handlers/stock_scores.py (what the
webapp's /app/scores page actually calls), which had ITS OWN market-cap floor deliberately
removed 2026-09-15 on live-verified evidence that real IBD screens (IBD 50) have no
market-cap floor at all - only a minimum share price and minimum average dollar volume. This
endpoint now uses the identical IBD-style liquidity-only screen (algo_config
min_stock_price/min_adv_dollars) so the TUI dashboard and the webapp can't silently disagree
on which stocks are investable.

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
            ("min_stock_price", "5.0"),
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
    def test_query_filters_by_price_and_liquidity(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor()
        _get_dashboard_scores(cursor, limit=50)

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert any("liq.latest_close" in sql for sql in executed_queries)
        assert any("liq.avg_dollar_volume_20d" in sql for sql in executed_queries)

    def test_uses_configured_thresholds(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor(
            config_rows=[
                ("min_stock_price", "5.0"),
                ("min_adv_dollars", "500000"),
            ]
        )
        _get_dashboard_scores(cursor, limit=50)

        all_params = [p for c in cursor.execute.call_args_list for p in (c.args[1] if len(c.args) > 1 else []) or []]
        assert 5.0 in all_params
        assert 500_000.0 in all_params

    def test_falls_back_to_safe_defaults_when_config_missing(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor(config_rows=[])
        _get_dashboard_scores(cursor, limit=50)

        all_params = [p for c in cursor.execute.call_args_list for p in (c.args[1] if len(c.args) > 1 else []) or []]
        assert 5.0 in all_params
        assert 500_000.0 in all_params
