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
    """Routes by query content: the quarterly EPS lookup (fetchall) vs. the
    is_foreign_private_issuer lookup (fetchone) added for the <2-quarters branch."""

    def __init__(self, rows: list[tuple], is_fpi: bool | None = False) -> None:
        self._rows = rows
        self._is_fpi = is_fpi
        self._last_query = ""

    def execute(self, query, params=None) -> None:
        self._last_query = query

    def fetchall(self):
        assert "quarterly_income_statement" in self._last_query
        assert "LIMIT 4" in self._last_query
        return self._rows

    def fetchone(self):
        assert "is_foreign_private_issuer" in self._last_query
        return None if self._is_fpi is None else (self._is_fpi,)


class _FakeDatabaseContext:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, *a):
        return False


def test_fewer_than_two_quarters_is_honestly_unavailable(monkeypatch) -> None:
    import loaders.load_earnings_metrics as mod

    cursor = _FakeCursor([(2026, 2, 1.5)], is_fpi=False)
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

    cursor = _FakeCursor([], is_fpi=False)
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))

    records = _make_loader().fetch_incremental("NOEPS", since=None)

    assert records[0]["data_unavailable"] is True
    assert records[0]["unavailable_reason"] == "insufficient_quarterly_eps_history"


def test_foreign_private_issuer_gets_specific_exemption_reason(monkeypatch) -> None:
    # Regression (2026-08-19, same audit): a foreign private issuer (20-F/40-F filer) is
    # exempt from quarterly 10-Q reporting - quarterly_income_statement is structurally
    # near-empty for it, not a data gap that more loading could ever close. Live-confirmed
    # 229 of 492 universe earnings_metrics "insufficient_quarterly_eps_history" rows are this
    # exact case, same distinction load_value_quality_growth_metrics.py already makes for its
    # own identical <4-quarters check.
    import loaders.load_earnings_metrics as mod

    cursor = _FakeCursor([(2026, 2, 1.5)], is_fpi=True)
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))

    records = _make_loader().fetch_incremental("CHKP", since=None)

    assert records[0]["data_unavailable"] is True
    assert records[0]["unavailable_reason"] == "foreign_private_issuer_no_quarterly_filings"


def test_no_company_info_sec_row_keeps_generic_reason(monkeypatch) -> None:
    # Control: a symbol with no company_info_sec row at all (fetchone returns None) has no
    # way to confirm FPI status - must stay the generic reason, not crash or default to FPI.
    import loaders.load_earnings_metrics as mod

    cursor = _FakeCursor([], is_fpi=None)
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))

    records = _make_loader().fetch_incremental("UNKNOWN", since=None)

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


def test_zero_mean_eps_with_high_variance_gets_maximum_dampening(monkeypatch) -> None:
    """BUG FOUND 2026-08-24: quarters oscillating +2,-2,+2,-2 (avg_eps == 0 exactly, but
    wildly volatile) must NOT get zero dampening just because dividing by |avg_eps| is
    undefined at exactly zero - that's the most unstable pattern possible, not the most
    stable. Same 50% consistency_score as test_volatile_earnings_dampen_quality_score_
    below_consistency, but earnings_quality_score must still be strictly dampened below
    it, not left equal to it."""
    import loaders.load_earnings_metrics as mod

    cursor = _FakeCursor(
        [
            (2026, 2, 2.0),
            (2026, 1, -2.0),
            (2025, 4, 2.0),
            (2025, 3, -2.0),
        ]
    )
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))

    records = _make_loader().fetch_incremental("SEESAW", since=None)

    r = records[0]
    assert r["consistency_score"] == 50.0
    assert r["earnings_quality_score"] < r["consistency_score"]


def test_zero_mean_zero_variance_eps_does_not_crash(monkeypatch) -> None:
    """Control/regression guard: all four quarters exactly 0.0 means avg_eps == 0 AND
    stdev_eps == 0 simultaneously (the one avg_eps==0 case where zero dampening is
    actually correct - genuinely flat, not offsetting swings). Mainly guards against a
    naive stdev_eps/abs(avg_eps) reintroduction raising ZeroDivisionError here; the
    output is 0 either way since 0.0 doesn't count as a positive quarter."""
    import loaders.load_earnings_metrics as mod

    cursor = _FakeCursor(
        [
            (2026, 2, 0.0),
            (2026, 1, 0.0),
            (2025, 4, 0.0),
            (2025, 3, 0.0),
        ]
    )
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))

    records = _make_loader().fetch_incremental("FLATZERO", since=None)

    r = records[0]
    assert r["consistency_score"] == 0.0
    assert r["earnings_quality_score"] == 0.0


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
