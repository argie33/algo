"""Regression test: /api/scores/stockscores (scores_handlers/stock_scores.py's
_get_stock_scores) never applied any market-cap tilt at all - unlike its sibling
/api/algo/scores endpoint, which got a market-cap tilt fix earlier the same day
(2026-09-15) that never reached this endpoint. Live-caught bug: the actual dashboard page
(webapp/frontend/src/pages/ScoresDashboard.jsx) calls THIS endpoint, so the fix never
reached what the user was actually looking at - the Rankings table and all 5 per-pillar
Leaders/Laggards tabs kept showing raw-percentile micro/small-cap names with no
cap-weighting.

Fixed by mapping each requested `sort_by` (composite_score/momentum_score/quality_score/
value_score/growth_score/risk_score) to its batch-computed *_tilted_weight column
(loaders/stock_scores/market_cap_tilt.py, migration 1294) instead of the raw score column,
and including all 6 *_tilted_weight fields in the response so the frontend can sort its
client-side Leaders/Laggards tabs by the same stored numbers instead of re-deriving/
duplicating the tilt formula itself.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _mock_cursor() -> Mock:
    cursor = Mock()
    cursor.fetchone.return_value = [0]
    cursor.fetchall.return_value = []
    return cursor


class TestStockScoresTiltedWeightSort:
    def test_composite_score_sort_orders_by_tilted_weight(self) -> None:
        """UPDATED 2026-09-15 (same day, later fix - see MEMORY.md
        leaders_laggards_wrongly_tilted_by_cap_fixed_20260915 / this endpoint's own
        `weighting` param docstring): tilted weight is opt-in now (?weighting=tilted), not
        the default - applying it to every sort_by silently market-cap-dominated every
        non-composite caller (SectorAnalysis.jsx's "Top Companies", the per-pillar
        Leaders/Laggards tabs). This test now explicitly requests weighting="tilted" to
        cover that opt-in path; the default-is-raw behavior is covered by the new test
        below."""
        from routes.scores_handlers.stock_scores import _get_stock_scores

        cursor = _mock_cursor()
        _get_stock_scores(cursor, limit=10, offset=0, sort_by="composite_score", sort_order="desc", weighting="tilted")

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert any("ORDER BY sc.composite_tilted_weight DESC NULLS LAST" in sql for sql in executed_queries)
        assert not any("ORDER BY sc.composite_score " in sql for sql in executed_queries)

    def test_default_weighting_orders_by_raw_score_not_tilted(self) -> None:
        """The counterpart to the test above: with no `weighting` argument (the real default
        every existing caller uses), sort_by=composite_score must order by the raw score
        column, not silently fall back to market-cap-tilted."""
        from routes.scores_handlers.stock_scores import _get_stock_scores

        cursor = _mock_cursor()
        _get_stock_scores(cursor, limit=10, offset=0, sort_by="composite_score", sort_order="desc")

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert any("ORDER BY sc.composite_score DESC NULLS LAST" in sql for sql in executed_queries)
        assert not any("ORDER BY sc.composite_tilted_weight " in sql for sql in executed_queries)

    def test_raw_score_fallback_tiebreak_present(self) -> None:
        """Every *_tilted_weight is NULL until the batch pass runs at least once after
        migration 1294 - without a secondary ORDER BY key, that entire window would sort
        database-arbitrarily instead of gracefully degrading to this endpoint's pre-fix
        raw-score-DESC behavior. Only relevant in the opt-in tilted path (the default raw
        path has no tilted/raw fallback distinction to test - it's raw all the way through)."""
        from routes.scores_handlers.stock_scores import _get_stock_scores

        cursor = _mock_cursor()
        _get_stock_scores(cursor, limit=10, offset=0, sort_by="quality_score", sort_order="desc", weighting="tilted")

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        main_query = next(sql for sql in executed_queries if "filtered_scores AS" in sql)
        assert "sc.quality_tilted_weight DESC NULLS LAST, sc.quality_score DESC NULLS LAST" in main_query

    def test_each_pillar_sort_maps_to_its_own_tilted_weight_column(self) -> None:
        """Real ActiveBeta-style construction tilts EACH factor sub-index by that factor's
        own z-score, not composite's - a Quality Leaders request (with weighting="tilted"
        explicitly opted into) must order by quality_tilted_weight, not composite_tilted_weight
        or raw quality_score."""
        from routes.scores_handlers.stock_scores import _get_stock_scores

        pillar_to_weight_col = {
            "momentum_score": "momentum_tilted_weight",
            "quality_score": "quality_tilted_weight",
            "value_score": "value_tilted_weight",
            "growth_score": "growth_tilted_weight",
            "risk_score": "risk_tilted_weight",
        }
        for sort_by, weight_col in pillar_to_weight_col.items():
            cursor = _mock_cursor()
            _get_stock_scores(cursor, limit=10, offset=0, sort_by=sort_by, sort_order="desc", weighting="tilted")
            executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
            assert any(f"ORDER BY sc.{weight_col} DESC NULLS LAST" in sql for sql in executed_queries), (
                f"sort_by={sort_by} did not order by {weight_col}"
            )

    def test_symbol_sort_is_unaffected(self) -> None:
        """Alphabetical symbol sort has no tilted-weight analog and must stay literal."""
        from routes.scores_handlers.stock_scores import _get_stock_scores

        cursor = _mock_cursor()
        _get_stock_scores(cursor, limit=10, offset=0, sort_by="symbol", sort_order="asc")

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        assert any("ORDER BY sc.symbol ASC NULLS LAST" in sql for sql in executed_queries)

    def test_response_includes_all_six_tilted_weight_columns(self) -> None:
        """The main query must select every *_tilted_weight column so the frontend can sort
        its client-side Leaders/Laggards tabs by the stored number instead of duplicating the
        tilt formula (a real bug this same session: a near-third copy was drafted directly in
        ScoresDashboard.jsx before being caught and reverted)."""
        from routes.scores_handlers.stock_scores import _get_stock_scores

        cursor = _mock_cursor()
        _get_stock_scores(cursor, limit=10, offset=0)

        executed_queries = [c.args[0] for c in cursor.execute.call_args_list]
        main_query = next(sql for sql in executed_queries if "filtered_scores AS" in sql)
        for col in (
            "composite_tilted_weight",
            "momentum_tilted_weight",
            "quality_tilted_weight",
            "value_tilted_weight",
            "growth_tilted_weight",
            "risk_tilted_weight",
        ):
            assert f"fs.{col}" in main_query, f"{col} not selected in the main query"
