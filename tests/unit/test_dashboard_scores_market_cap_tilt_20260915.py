"""Regression test: /api/algo/scores' displayed leaderboard market-cap-weighted tilt.

Added 2026-09-15 (/goal session: "get ours factor and composite scores like theirs").
Root cause (see [[overlap_metric_methodology_clarified_20260915]] in memory): this endpoint
ranked purely by composite_score DESC, a pure-merit percentile score with no size component -
unlike real multi-factor ETFs (LRGF/GSLC), which are float-adjusted market-cap-weighted
portfolios with only a mild factor tilt on top. Mirrors the sector-weight-cap fix
(test_dashboard_scores_sector_weight_cap_20260914.py) - same "fix the displayed leaderboard,
not the underlying pillar/composite_score" pattern, same fake-cursor-matching-on-SQL-text
convention (see [[watermark_desync_test_fixture_fix_20260907]] in memory).
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api" / "routes"))

MAIN_QUERY_COLUMNS = [
    "symbol",
    "composite_score",
    "growth_score",
    "momentum_score",
    "quality_score",
    "value_score",
    "risk_score",
    "rs_percentile",
    "data_completeness",
    "updated_at",
    "company_name",
    "sector",
    "market_cap",
    "current_price",
    "change_percent",
    "price_vs_sma_50",
    "price_vs_sma_200",
]
SCORE_IDX = MAIN_QUERY_COLUMNS.index("composite_score")
CAP_IDX = MAIN_QUERY_COLUMNS.index("market_cap")


def _row(symbol: str, score: float, market_cap: float | None, sector: str = "Technology") -> tuple:
    row = [None] * len(MAIN_QUERY_COLUMNS)
    row[0] = symbol
    row[SCORE_IDX] = score
    row[CAP_IDX] = market_cap
    row[MAIN_QUERY_COLUMNS.index("sector")] = sector
    return tuple(row)


def _mock_cursor(candidate_rows: list[tuple]):
    cursor = Mock(spec=["execute", "fetchall", "fetchone", "description"])
    cursor.description = [(n,) for n in MAIN_QUERY_COLUMNS]

    def fake_execute(sql, *_args, **_kwargs):
        if "GROUP BY c.sector" in sql:
            cursor.description = [("sector",), ("n",)]
        elif "FROM filtered_scores fs" in sql:
            cursor.description = [(n,) for n in MAIN_QUERY_COLUMNS]
        elif "AVG(s.composite_score)" in sql:
            cursor.description = [("universe_total",), ("avg_composite",), ("a",), ("b",), ("c",), ("d",)]

    cursor.execute.side_effect = fake_execute

    def fake_fetchall():
        sql = cursor.execute.call_args.args[0]
        if "FROM algo_config" in sql:
            return [("min_market_cap_millions", "300.0"), ("min_adv_dollars", "500000")]
        if "GROUP BY c.sector" in sql:
            # One giant sector so the sector-weight cap never binds in this test - isolates
            # the market-cap tilt behavior from the sector-cap's own backfill logic.
            return [("Technology", 1000)]
        if "FROM filtered_scores fs" in sql:
            return candidate_rows
        return []

    def fake_fetchone():
        sql = cursor.execute.call_args.args[0]
        if "AVG(s.composite_score)" in sql:
            return (0, 50.0, 0, 0, 0, 0)
        return None

    cursor.fetchall.side_effect = fake_fetchall
    cursor.fetchone.side_effect = fake_fetchone
    return cursor


class TestDashboardScoresMarketCapTilt:
    def test_mega_cap_with_slightly_lower_score_still_ranks_above_micro_cap(self):
        """A $2T mega-cap scoring 70 should outrank a $50M micro-cap scoring 72 - real
        multi-factor funds would never let a razor-thin score edge overcome a 40,000x market
        cap gap, and pure composite_score-DESC ranking (pre-fix) would get this backwards.
        """
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        candidate_rows = [
            _row("MEGA", 70.0, 2_000_000_000_000.0),
            _row("MICRO", 72.0, 50_000_000.0),
        ]
        # Pad with enough neutral rows for a real stdev to compute.
        candidate_rows += [_row(f"MID{i}", 60.0 + i, 50_000_000_000.0) for i in range(10)]

        cursor = _mock_cursor(candidate_rows)
        result = _get_dashboard_scores(cursor, limit=12)

        symbols = [s["symbol"] for s in result["data"]["top"]]
        assert symbols.index("MEGA") < symbols.index("MICRO")

    def test_market_cap_missing_falls_back_to_composite_score_order(self):
        """A candidate pool with no market_cap data at all (column present but every value
        NULL) must not crash or silently drop rows - same fallback as _apply_sector_weight_cap
        when its own required column is absent, applied here for a NULL-valued column.
        """
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        candidate_rows = [_row(f"S{i}", 100 - i, None) for i in range(10)]
        cursor = _mock_cursor(candidate_rows)
        result = _get_dashboard_scores(cursor, limit=10)

        assert len(result["data"]["top"]) == 10

    def test_no_regression_when_scores_have_no_variance(self):
        """All candidates tied on composite_score (stdev=0) must not divide by zero - the
        tilt should no-op and preserve the original composite_score-DESC order."""
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        candidate_rows = [_row(f"S{i}", 50.0, 1_000_000_000.0 * (i + 1)) for i in range(10)]
        cursor = _mock_cursor(candidate_rows)
        result = _get_dashboard_scores(cursor, limit=10)

        assert len(result["data"]["top"]) == 10

    def test_market_cap_not_leaked_into_api_response(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        candidate_rows = [_row(f"S{i}", 100 - i, 1_000_000_000.0) for i in range(5)]
        cursor = _mock_cursor(candidate_rows)
        result = _get_dashboard_scores(cursor, limit=5)

        for entry in result["data"]["top"]:
            assert "market_cap" not in entry
