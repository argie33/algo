"""Regression test: /api/algo/scores' S&P 500 sub-leaderboard (top_sp500).

Added 2026-09-07 (/goal session: "I know 500 S&P companies that are amazing and I don't
see any of them anywhere near the top"). Root-caused: even restricted to the S&P 500 alone,
Technology has the highest average quality_score (66.6) and growth_score (67.1) of any
sector but the worst average value_score (31.3) - Value is 27% of BASE_PILLAR_WEIGHTS and
structurally penalizes companies whose greatness is already priced in, so a universe-wide
cheapness screen can never put famous megacaps at the top regardless of business quality.
Tested the "obvious" fix (reweighting toward Growth/Quality,
algo/research/pillar_weight_reallocation_test_20260907.py) - it makes holdout-period IC
WORSE (0.0194 -> 0.0152), so it's rejected on the same evidence bar as the earlier
sector-neutral-ranking test. Instead of degrading the validated score, this adds a second,
unmodified view: the same composite_score, restricted to stock_symbols.is_sp500=TRUE, so
recognizable large-cap names can be seen ranked against each other.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api" / "routes"))


def _mock_cursor(sp500_rows=None):
    cursor = Mock()
    # check_data_freshness() unwraps `cur.cursor` if present (DatabaseQueryService wrapper
    # support) - a plain Mock() auto-creates that attribute too, which would silently swap
    # in a second, unrouted mock. Self-reference so the "unwrap" is a no-op.
    cursor.cursor = cursor
    sp500_rows = (
        sp500_rows
        if sp500_rows is not None
        else [
            {
                "symbol": "AAPL",
                "composite_score": 59.53,
                "growth_score": 68.51,
                "momentum_score": 75.98,
                "quality_score": 82.87,
                "value_score": 15.34,
                "risk_score": 66.13,
                "data_completeness": 95.0,
                "company_name": "Apple Inc.",
                "sector": "Technology",
            }
        ]
    )

    def fake_fetchall():
        sql = cursor.execute.call_args.args[0]
        if "FROM algo_config" in sql:
            return [("min_market_cap_millions", "300.0"), ("min_adv_dollars", "500000")]
        if "is_sp500 = TRUE" in sql:
            return sp500_rows
        return []

    def fake_fetchone():
        sql = cursor.execute.call_args.args[0]
        if "universe_total" in sql:
            # A dict (not tuple/list) sidesteps safe_dict_convert's cursor.description
            # requirement entirely - it's already dict-shaped, same as a psycopg2 DictRow.
            return {"universe_total": 0, "avg_composite": None, "a": 0, "b": 0, "c": 0, "d": 0}
        if "null_count" in sql:
            return [0, 0]
        return None

    cursor.fetchall.side_effect = fake_fetchall
    cursor.fetchone.side_effect = fake_fetchone
    return cursor


class TestDashboardScoresSp500SubLeaderboard:
    def test_query_restricted_to_sp500_flag(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor()
        _get_dashboard_scores(cursor, limit=50)

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert any("is_sp500 = TRUE" in sql for sql in executed_queries)

    def test_response_includes_top_sp500(self):
        import json

        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor()
        resp = _get_dashboard_scores(cursor, limit=50)
        body = json.loads(resp["body"]) if isinstance(resp.get("body"), str) else resp
        data = body.get("data", body)

        assert "top_sp500" in data
        assert data["top_sp500"][0]["symbol"] == "AAPL"

    def test_empty_sp500_result_does_not_crash(self):
        import json

        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor(sp500_rows=[])
        resp = _get_dashboard_scores(cursor, limit=50)
        body = json.loads(resp["body"]) if isinstance(resp.get("body"), str) else resp
        data = body.get("data", body)

        assert data["top_sp500"] == []
