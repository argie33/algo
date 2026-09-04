"""Regression test (2026-09-04, goal: "Missing SEC/XBRL data" reduction): _compute_quality_metrics's
row-level "mark unavailable if all 7 annual metrics are None" early-return used to fire even when
_compute_quarterly_metrics() (called earlier in the same function) had already computed real
quarterly-derived values - consecutive_positive_quarters/quarterly_growth_momentum/
earnings_growth_4q_avg/eps_growth_stability all got silently wiped by _unavailable_marker's
blanket None+"missing_sec_data" stamp on every column.

Live-confirmed 293 of 378 universe quality_metrics rows currently hitting this early-return path
(77%) have real (data_unavailable=FALSE) quarterly_income_statement data for >=4 quarters -
a symbol with a totally unavailable balance sheet/income statement but a perfectly real quarterly
filing history was throwing away real, computable growth signal.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _empty_quality_row():
    # 34-column shape, every field None - the whole balance-sheet/income-statement side is
    # unavailable, forcing all 7 annual metrics (roe/roa/operating_margin/net_margin/
    # debt_to_equity/debt_to_assets/current_ratio) to None.
    return [None] * 34


def _quarter(fiscal_year, fiscal_quarter, net_income, revenue, eps):
    return (fiscal_year, fiscal_quarter, net_income, revenue, eps)


class _FakeCursor:
    def __init__(self, quarters):
        self._quarters = quarters
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "FROM quarterly_income_statement" in self._last_query:
            return self._quarters
        # Every gate-lookup query (no-recent/never-tagged windowed variants etc.) - empty means
        # the test symbol matches none of them, keeping this test focused on the one behavior
        # under test.
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, quarters):
        self._quarters = quarters

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._quarters)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, quarters):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(quarters))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestQualityRowLevelUnavailablePreservesQuarterly:
    def test_real_quarterly_data_survives_full_annual_unavailability(self, monkeypatch):
        quarters = [
            _quarter(2026, 2, 10_000_000.0, 100_000_000.0, 0.50),
            _quarter(2026, 1, 9_000_000.0, 95_000_000.0, 0.45),
            _quarter(2025, 4, 8_000_000.0, 90_000_000.0, 0.40),
            _quarter(2025, 3, 7_000_000.0, 85_000_000.0, 0.35),
            _quarter(2025, 2, 6_000_000.0, 80_000_000.0, 0.30),
            _quarter(2025, 1, 5_000_000.0, 75_000_000.0, 0.25),
        ]
        loader = _make_loader(monkeypatch, quarters)
        row = _empty_quality_row()

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        # The row-level marker must NOT have fired - real quarterly data survives.
        assert metrics.get("data_unavailable") is not True
        assert metrics["consecutive_positive_quarters"] == 4
        # earnings_growth_4q_avg needs a same-quarter-prior-year match, which this 6-quarter
        # fixture doesn't have - but it must get its OWN specific reason, not the row-level
        # blanket "missing_sec_data".
        assert metrics.get("earnings_growth_4q_avg_unavailable_reason") != "missing_sec_data"
        # The 7 annual fields are still correctly unavailable, each with its own real reason
        # (not silently overwritten by a blanket marker).
        assert metrics["roe"] is None
        assert metrics["debt_to_equity"] is None

    def test_no_quarterly_data_still_marks_row_unavailable(self, monkeypatch):
        loader = _make_loader(monkeypatch, quarters=[])
        row = _empty_quality_row()

        metrics = loader._compute_quality_metrics("SYM", row, ev_metrics=(None, None, None))

        assert metrics.get("data_unavailable") is True
        assert metrics.get("roe_unavailable_reason") in ("missing_sec_data", "no_recent_balance_sheet_data_reported")
