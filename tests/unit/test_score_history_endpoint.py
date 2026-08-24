"""Regression coverage for /api/scores/history/:symbol (2026-08-24 goal session: track
historical stock_scores/rank movement over time). stock_scores itself is a symbol-keyed
snapshot overwritten in place on every loader run - there was previously nowhere to see how
a stock's composite score or rank moved day over day. stock_scores_history (migration 1221)
and load_stock_scores.py's snapshot_score_history() (called from post_run(), after
update_rs_percentiles()) add the daily snapshot; this endpoint reads it back.
"""

import importlib
from datetime import datetime

scores_mod = importlib.import_module("lambda.api.routes.scores")


class _FakeCursor:
    """Minimal cursor simulating stock_scores_history rows for one symbol."""

    def __init__(self, history_rows):
        self._history_rows = history_rows
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query
        self._last_params = params

    def fetchall(self):
        if "FROM stock_scores_history" in self._last_query:
            return list(self._history_rows)
        return []

    def fetchone(self):
        if "MAX(" in self._last_query:
            return (datetime(2026, 8, 24),)
        return None


def _row(score_date, composite_score, composite_rank, rs_percentile=None):
    return {
        "score_date": score_date,
        "composite_score": composite_score,
        "composite_rank": composite_rank,
        "rs_percentile": rs_percentile,
        "momentum_score": None,
        "quality_score": None,
        "growth_score": None,
        "value_score": None,
        "positioning_score": None,
        "stability_score": None,
        "data_completeness": None,
    }


def test_history_endpoint_routes_through_handle():
    from datetime import date

    rows = [_row(date(2026, 8, 20), 70.0, 500), _row(date(2026, 8, 24), 75.5, 100)]
    cursor = _FakeCursor(rows)
    resp = scores_mod.handle(cursor, "/api/scores/history/AAPL", "GET", {"days": "30"})
    assert resp["statusCode"] == 200
    assert resp["data"]["symbol"] == "AAPL"
    assert len(resp["data"]["points"]) == 2


def test_score_and_rank_improve_over_window():
    from datetime import date

    rows = [
        _row(date(2026, 8, 20), 70.0, 500, rs_percentile=40.0),
        _row(date(2026, 8, 24), 75.5, 100, rs_percentile=55.0),
    ]
    cursor = _FakeCursor(rows)
    resp = scores_mod._get_score_history(cursor, "AAPL", 30)

    assert resp["statusCode"] == 200
    movement = resp["data"]["movement"]
    assert movement["score_change"] == 5.5
    # rank improved (500 -> 100): rank_change must be positive = "moved toward rank 1"
    assert movement["rank_change"] == 400
    assert movement["rs_percentile_change"] == 15.0
    assert movement["start_date"] == "2026-08-20"
    assert movement["end_date"] == "2026-08-24"


def test_single_point_has_no_movement():
    from datetime import date

    rows = [_row(date(2026, 8, 24), 75.5, 100)]
    cursor = _FakeCursor(rows)
    resp = scores_mod._get_score_history(cursor, "AAPL", 30)

    assert resp["statusCode"] == 200
    movement = resp["data"]["movement"]
    assert movement["score_change"] is None
    assert movement["rank_change"] is None


def test_empty_history_is_not_an_error():
    cursor = _FakeCursor([])
    resp = scores_mod._get_score_history(cursor, "NEWIPO", 30)

    assert resp["statusCode"] == 200
    assert resp["data"]["points"] == []


def test_invalid_symbol_format_rejected():
    cursor = _FakeCursor([])
    resp = scores_mod.handle(cursor, "/api/scores/history/DROP TABLE", "GET", {})
    assert resp["statusCode"] == 400
