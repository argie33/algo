"""Regression test: /api/algo/scores' displayed leaderboard sector-weight deviation band.

Added 2026-09-14 (/goal session - user pushed back that our lists still don't look like a
real industry factor product's holdings). Root cause (see
[[sector_weight_cap_missing_vs_realindex_20260914]] in memory): this endpoint ranked purely
by composite_score DESC with no sector limit, unlike real MSCI/AQR factor indices which cap
sector weight in their published holdings vs. the parent cap-weighted index. Real traded
capital already has a separate flat count cap (algo/orchestrator/phase8_entry_execution.py's
max_positions_per_sector) - this is specifically about the displayed leaderboard, which had
no equivalent control.

Routes fake cursor responses by matching on the rendered SQL text, not call order/fixed
shape - see [[watermark_desync_test_fixture_fix_20260907]] in memory for why a
fixed-shape-per-call mock breaks the moment a new query is added to the handler.
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
    "current_price",
    "change_percent",
    "price_vs_sma_50",
    "price_vs_sma_200",
]
SECTOR_IDX = MAIN_QUERY_COLUMNS.index("sector")


def _row(symbol: str, score: float, sector: str) -> tuple:
    row = [None] * len(MAIN_QUERY_COLUMNS)
    row[0] = symbol
    row[1] = score
    row[SECTOR_IDX] = sector
    return tuple(row)


def _mock_cursor(sector_universe_counts: dict, candidate_rows: list[tuple]):
    # spec= restricts attributes to this list, so `hasattr(cursor, "cursor")` is False -
    # a bare Mock() auto-vivifies ANY attribute access (including `.cursor`), which makes
    # routes/utils.py's set_current_cursor() unwrap loop drill into synthetic child mocks
    # instead of stopping on this cursor's real `.description` - see that function's own
    # "max unwrap depth" guard/comment for the exact failure mode this avoids.
    cursor = Mock(spec=["execute", "fetchall", "fetchone", "description"])
    # Real psycopg2 Column objects are subscriptable (desc[0] == name) - safe_dict_convert
    # (routes/utils.py) relies on that, so a plain tuple matches production shape exactly.
    cursor.description = [(n,) for n in MAIN_QUERY_COLUMNS]

    def fake_execute(sql, *_args, **_kwargs):
        # safe_dict_convert reads the thread-local cursor's CURRENT .description to zip
        # column names onto a tuple row - this handler runs several differently-shaped
        # queries, so description must track whichever query was executed most recently,
        # not stay fixed at the main leaderboard query's shape.
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
            return list(sector_universe_counts.items())
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


class TestDashboardScoresSectorWeightCap:
    def test_dominant_sector_capped_and_backfilled_from_other_sectors(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        # Universe: Healthcare is 20% of the eligible universe, Materials 10%, rest spread out.
        sector_universe_counts = {"Healthcare": 20, "Materials": 10, "Technology": 70}
        # Candidate pool (already ORDER BY composite_score DESC, as the real query returns):
        # Healthcare dominates the top purely on raw score - 8 of the top 10 rows.
        candidate_rows = [_row(f"HC{i}", 100 - i, "Healthcare") for i in range(8)]
        candidate_rows += [_row("TECH1", 90, "Technology"), _row("MAT1", 89, "Materials")]
        candidate_rows += [_row(f"TECH{i}", 80 - i, "Technology") for i in range(2, 12)]

        cursor = _mock_cursor(sector_universe_counts, candidate_rows)
        result = _get_dashboard_scores(cursor, limit=10)

        symbols_by_sector: dict[str, int] = {}
        for s in result["data"]["top"]:
            symbols_by_sector[s["sector"]] = symbols_by_sector.get(s["sector"], 0) + 1

        # Healthcare is 20% of the universe -> cap = ceil(0.20 * 10 * 2.0) = 4, well under the
        # 8 raw-score-ranked Healthcare rows available - the cap must actually bind.
        assert symbols_by_sector.get("Healthcare", 0) <= 4
        # The freed slots must be backfilled from other real candidates, not just dropped -
        # the result should still reach the requested limit.
        assert len(result["data"]["top"]) == 10
        assert symbols_by_sector.get("Technology", 0) > 0

    def test_no_sector_data_falls_back_to_plain_truncation(self):
        from routes.algo_handlers.dashboard.scores import _get_dashboard_scores

        cursor = _mock_cursor({}, [_row(f"S{i}", 100 - i, "Technology") for i in range(15)])
        result = _get_dashboard_scores(cursor, limit=10)

        assert len(result["data"]["top"]) == 10
