"""Regression test: /api/scores' minMarketCap eligibility filter.

Added 2026-08-31 (/goal session, "make sure the results make sense" investigation). The
composite_score-sorted default view of this endpoint had no investability screen at all -
live-verified the top of the ranking was dominated by nano/micro-caps (SOGP $37.6M market cap,
COHN $19.6M, several under $200K/day dollar volume) since Size was retired as a scoring pillar
with nothing left to offset small-cap-favoring percentile scoring. A liquidity gate already
exists for real trade execution (algo/risk/liquidity_checks.py) but only fires at Phase 8 entry
time, invisible to anyone just browsing this list. `minMarketCap` is an opt-in query param
(no behavior change when omitted) that joins value_metrics and filters server-side.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _mock_cursor(rows):
    cursor = Mock()
    cursor.fetchone.return_value = [len(rows)]
    cursor.fetchall.return_value = rows
    return cursor


class TestMinMarketCapLiquidityFloor:
    def test_omitted_param_does_not_join_value_metrics(self):
        from routes.scores import handle

        cursor = _mock_cursor([])
        handle(cursor, "/api/scores", "GET", {})

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert not any("JOIN value_metrics mcf" in sql for sql in executed_queries)
        assert not any("mcf.market_cap" in sql for sql in executed_queries)

    def test_min_market_cap_adds_join_and_filter_with_param(self):
        from routes.scores import handle

        cursor = _mock_cursor([])
        handle(cursor, "/api/scores", "GET", {"minMarketCap": "300000000"})

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert any("JOIN value_metrics mcf" in sql for sql in executed_queries)
        assert any("mcf.market_cap >= %s" in sql for sql in executed_queries)

        all_params = [p for c in cursor.execute.call_args_list for p in (c.args[1] if len(c.args) > 1 else []) or []]
        assert 300000000.0 in all_params

    def test_min_market_cap_ignored_for_single_symbol_lookup(self):
        # A specific symbol lookup must always work regardless of its market cap - the
        # investability screen is only meant to shape the ranked/browse list.
        from routes.scores import handle

        cursor = _mock_cursor([])
        handle(cursor, "/api/scores", "GET", {"symbol": "SOGP", "minMarketCap": "300000000"})

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert not any("JOIN value_metrics mcf" in sql for sql in executed_queries)

    def test_non_numeric_min_market_cap_rejected(self):
        from routes.scores import handle

        cursor = _mock_cursor([])
        response = handle(cursor, "/api/scores", "GET", {"minMarketCap": "not-a-number"})

        assert response["statusCode"] == 400
