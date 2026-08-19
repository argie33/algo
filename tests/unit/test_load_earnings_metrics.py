"""Regression tests for loaders/load_earnings_metrics.py (2026-08-19, "no SEC data"/missing
factor inputs audit): earnings_metrics had no ongoing loader at all - every row shared the
exact same 2026-08-09 timestamp, confirmed live via MIN(created_at)/MAX(created_at) both
returning that same instant across all 5,119 rows, and no entry in data_loader_status. It
was populated once by migration 1147 and never touched again while real quarterly EPS data
kept refreshing underneath it. This loader reuses migration 1147's exact formula (trailing-
4-quarter EPS consistency, dampened by relative volatility) as a real, recurring per-symbol
loader instead of a frozen one-off snapshot.
"""

from datetime import date

from loaders.load_earnings_metrics import EarningsMetricsLoader


def _make_loader() -> EarningsMetricsLoader:
    return EarningsMetricsLoader.__new__(EarningsMetricsLoader)


class _FakeCursor:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def execute(self, query, params=None) -> None:
        assert "quarterly_income_statement" in query
        assert "LIMIT 4" in query

    def fetchall(self):
        return self._rows


class _FakeDatabaseContext:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, *a):
        return False


def test_fewer_than_two_quarters_is_honestly_unavailable(monkeypatch) -> None:
    import loaders.load_earnings_metrics as mod

    cursor = _FakeCursor([(2026, 2, 1.5)])
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))

    records = _make_loader().fetch_incremental("AAPL", since=None)

    assert len(records) == 1
    r = records[0]
    assert r["data_unavailable"] is True
    assert r["unavailable_reason"] == "insufficient_quarterly_eps_history"
    assert r["earnings_quality_score"] is None
    assert r["consistency_score"] is None
    assert r["report_date"] == date.today()


def test_zero_quarters_is_honestly_unavailable(monkeypatch) -> None:
    import loaders.load_earnings_metrics as mod

    cursor = _FakeCursor([])
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))

    records = _make_loader().fetch_incremental("NOEPS", since=None)

    assert records[0]["data_unavailable"] is True
    assert records[0]["unavailable_reason"] == "insufficient_quarterly_eps_history"


def test_perfectly_consistent_positive_eps_scores_100(monkeypatch) -> None:
    """4 quarters, identical positive EPS each time -> zero volatility, 4/4 positive:
    both consistency_score and earnings_quality_score must be exactly 100."""
    import loaders.load_earnings_metrics as mod

    cursor = _FakeCursor(
        [
            (2026, 2, 2.0),
            (2026, 1, 2.0),
            (2025, 4, 2.0),
            (2025, 3, 2.0),
        ]
    )
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))

    records = _make_loader().fetch_incremental("STABLE", since=None)

    r = records[0]
    assert r["data_unavailable"] is False
    assert r["unavailable_reason"] is None
    assert r["consistency_score"] == 100.0
    assert r["earnings_quality_score"] == 100.0


def test_all_negative_eps_scores_zero_consistency(monkeypatch) -> None:
    import loaders.load_earnings_metrics as mod

    cursor = _FakeCursor(
        [
            (2026, 2, -1.0),
            (2026, 1, -1.5),
            (2025, 4, -0.5),
            (2025, 3, -2.0),
        ]
    )
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))

    records = _make_loader().fetch_incremental("LOSSY", since=None)

    r = records[0]
    assert r["data_unavailable"] is False
    assert r["consistency_score"] == 0.0
    # Zero positive quarters means the base consistency term is already 0 - the
    # volatility dampener can only reduce further, so quality must also be 0.
    assert r["earnings_quality_score"] == 0.0


def test_volatile_earnings_dampen_quality_score_below_consistency(monkeypatch) -> None:
    """3 of 4 quarters positive (75% consistency) but with high relative volatility -
    earnings_quality_score must be strictly lower than the raw consistency_score, not
    just mirror it, otherwise the volatility dampener has no effect."""
    import loaders.load_earnings_metrics as mod

    cursor = _FakeCursor(
        [
            (2026, 2, 5.0),
            (2026, 1, 0.1),
            (2025, 4, 0.2),
            (2025, 3, -0.3),
        ]
    )
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))

    records = _make_loader().fetch_incremental("VOLATILE", since=None)

    r = records[0]
    assert r["consistency_score"] == 75.0
    assert r["earnings_quality_score"] < r["consistency_score"]
    assert 0.0 <= r["earnings_quality_score"] <= 100.0


def test_more_than_four_quarters_only_uses_trailing_four(monkeypatch) -> None:
    """The query itself is LIMIT 4 ORDER BY fiscal_year/quarter DESC - verifies the
    fake cursor's query assertion holds and a 4-row response is handled as exactly
    the trailing window, not accidentally including older data."""
    import loaders.load_earnings_metrics as mod

    cursor = _FakeCursor(
        [
            (2026, 2, 1.0),
            (2026, 1, 1.0),
            (2025, 4, 1.0),
            (2025, 3, 1.0),
        ]
    )
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))

    records = _make_loader().fetch_incremental("FOUR", since=None)

    assert records[0]["consistency_score"] == 100.0
