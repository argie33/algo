"""Regression test: /api/algo/scores' displayed leaderboard market-cap-weighted tilt.

Added 2026-09-15 (/goal session: "get ours factor and composite scores like theirs").
Root cause (see [[overlap_metric_methodology_clarified_20260915]] in memory): this endpoint
ranked purely by composite_score DESC, a pure-merit percentile score with no size component -
unlike real multi-factor ETFs (LRGF/GSLC), which are float-adjusted market-cap-weighted
portfolios with only a mild factor tilt on top.

REWRITTEN same day (still 2026-09-15): the tilt itself moved OUT of this endpoint's Python
code (a request-time _apply_market_cap_tilt() re-sort keyed off a `market_cap` column this
endpoint used to SELECT and then pop before returning) and into a batch pass
(loaders/stock_scores/market_cap_tilt.py's update_market_cap_tilted_weights(), tested in
tests/unit/test_market_cap_tilted_weights_20260915.py) that computes and stores
stock_scores.composite_tilted_weight once - live-caught bug: the Python tilt only ever
reached this endpoint, not /api/scores/stockscores (the endpoint the actual dashboard page
calls), so it silently never applied to what the user was looking at. This endpoint now just
orders by the stored column directly (available via the candidate-pool CTE's `s.*`, no longer
needs its own `market_cap` SELECT/pop at all).

The OLD version of this test mocked cursor.fetchall() to return `candidate_rows` verbatim
regardless of what SQL was executed, then asserted the RETURNED order matched what
_apply_market_cap_tilt (Python) would have produced. With that Python re-sort (and the
market_cap column it depended on) removed, this file's job changes to: (1) verify the SQL
text this endpoint sends actually orders by composite_tilted_weight (the same "fake-cursor-
matching-on-SQL-text convention" this file's docstring already used, just applied to what's
actually checkable now), and (2) verify the endpoint still handles rows correctly (no crash)
regardless of row order, since it no longer reorders or post-processes market_cap itself.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api" / "routes"))

# Matches _get_dashboard_scores' actual outer SELECT list (lambda/api/routes/algo_handlers/
# dashboard/scores.py) - market_cap is NOT part of this row shape (it's only referenced
# inside the CTE's WHERE filter via vm.market_cap, never selected out to the caller).
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
    "current_price",
    "change_percent",
    "price_vs_sma_50",
    "price_vs_sma_200",
]
SCORE_IDX = MAIN_QUERY_COLUMNS.index("composite_score")


def _row(symbol: str, score: float, sector: str = "Technology") -> tuple[str | float | None, ...]:
    row: list[str | float | None] = [None] * len(MAIN_QUERY_COLUMNS)
    row[0] = symbol
    row[SCORE_IDX] = score
    row[MAIN_QUERY_COLUMNS.index("sector")] = sector
    return tuple(row)


def _mock_cursor(candidate_rows: list[tuple[str | float | None, ...]]) -> Mock:
    cursor = Mock(spec=["execute", "fetchall", "fetchone", "description"])
    cursor.description = [(n,) for n in MAIN_QUERY_COLUMNS]
    executed_sql: list[str] = []

    def fake_execute(sql: str, *_args: object, **_kwargs: object) -> None:
        executed_sql.append(sql)
        if "GROUP BY c.sector" in sql:
            cursor.description = [("sector",), ("n",)]
        elif "FROM filtered_scores fs" in sql:
            cursor.description = [(n,) for n in MAIN_QUERY_COLUMNS]
        elif "AVG(s.composite_score)" in sql:
            cursor.description = [("universe_total",), ("avg_composite",), ("a",), ("b",), ("c",), ("d",)]

    cursor.execute.side_effect = fake_execute
    cursor.executed_sql = executed_sql

    def fake_fetchall() -> list[tuple[str | float | None, ...]]:
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

    def fake_fetchone() -> tuple[int, float, int, int, int, int] | None:
        sql = cursor.execute.call_args.args[0]
        if "AVG(s.composite_score)" in sql:
            return (0, 50.0, 0, 0, 0, 0)
        return None

    cursor.fetchall.side_effect = fake_fetchall
    cursor.fetchone.side_effect = fake_fetchone
    return cursor


class TestDashboardScoresMarketCapTilt:
    def test_query_orders_by_stored_tilted_weight_not_raw_composite_score(self) -> None:
        """The SQL this endpoint sends must order by the batch-computed
        composite_tilted_weight column (both the inner candidate-pool CTE and the outer
        SELECT), not raw composite_score DESC alone - this is what actually produces the
        cap-weighted-tilt ranking now (moved out of Python re-sorting, see this file's own
        module docstring)."""
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        candidate_rows = [_row(f"S{i}", 100 - i) for i in range(10)]
        cursor = _mock_cursor(candidate_rows)
        _get_dashboard_scores(cursor, limit=10)

        main_query_sql = next(sql for sql in cursor.executed_sql if "FROM filtered_scores fs" in sql)
        assert "composite_tilted_weight DESC" in main_query_sql
        # Both the candidate-pool CTE and the final SELECT must order by it - ordering only
        # the CTE would still let the outer join/backfill silently drop back to raw
        # composite_score order.
        assert main_query_sql.count("composite_tilted_weight DESC") >= 2

    def test_no_regression_when_scores_have_no_variance(self) -> None:
        """All candidates tied on composite_score must not crash - the SQL ORDER BY handles
        ties gracefully regardless of variance (unlike the removed Python tilt, which used to
        need an explicit stdev=0 guard)."""
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        candidate_rows = [_row(f"S{i}", 50.0) for i in range(10)]
        cursor = _mock_cursor(candidate_rows)
        result = _get_dashboard_scores(cursor, limit=10)

        assert len(result["data"]["top"]) == 10

    def test_market_cap_not_leaked_into_api_response(self) -> None:
        """market_cap was historically fetched/popped by this endpoint solely to drive the
        now-removed Python tilt - it must not appear in the response, and (post-fix) isn't
        even part of the SQL row shape anymore."""
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        candidate_rows = [_row(f"S{i}", 100 - i) for i in range(5)]
        cursor = _mock_cursor(candidate_rows)
        result = _get_dashboard_scores(cursor, limit=5)

        for entry in result["data"]["top"]:
            assert "market_cap" not in entry
