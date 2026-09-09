"""Regression test for the 2026-09-09 fix (goal: SEC/XBRL missing-data count under 500,
missing_sec_data investigation): a symbol with a real, recent-but-not-current-fiscal-year
annual_income_statement.net_income AND fewer than 4 real quarterly rows (so the existing TTM
fallback also can't fire) was falling all the way through to "missing_sec_data" for
net_margin/roe/roa/sustainable_growth_rate/payout_ratio - live-confirmed MDV: FY2025
net_income=$1,068,000 real, FY2026 anchor row a data_unavailable placeholder, only one real
quarter (Q1 2025) in quarterly_income_statement.

Mirrors `_fetch_balance_sheet_anchor_fallback`'s existing "prior real annual row" pattern,
applied to annual_income_statement.net_income via the same shared `_fetch_annual_fallback_row`
helper.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(net_income=None):
    row = [None] * 34
    row[0] = 100_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = 700_000_000.0  # total_assets
    row[3] = net_income
    row[4] = 100_000_000.0  # revenue
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2026  # fiscal_year
    return row


class _FakeCursor:
    def __init__(self, annual_fallback_net_income):
        self._annual_fallback_net_income = annual_fallback_net_income
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "FROM quarterly_income_statement" in self._last_query:
            return []
        return []

    def fetchone(self):
        # Match only the single-column net_income fallback query (`SELECT net_income FROM
        # annual_income_statement ...`) - other unrelated annual-fallback queries in this same
        # method (e.g. operating_income's 2-column revenue/operating_income fallback) also hit
        # annual_income_statement and must NOT be answered by this fake net_income row.
        if (
            "SELECT net_income FROM annual_income_statement" in self._last_query
            and self._annual_fallback_net_income is not None
        ):
            return (self._annual_fallback_net_income,)
        return None


class _FakeDatabaseContext:
    def __init__(self, annual_fallback_net_income):
        self._annual_fallback_net_income = annual_fallback_net_income

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._annual_fallback_net_income)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, annual_fallback_net_income):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(annual_fallback_net_income))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def test_net_income_recovered_from_prior_annual_fiscal_year(monkeypatch):
    loader = _make_loader(monkeypatch, annual_fallback_net_income=1_068_000.0)
    row = _quality_row(net_income=None)

    metrics = loader._compute_quality_metrics("MDV", row, ev_metrics=None)

    assert metrics["net_margin"] is not None
    assert metrics["net_margin_unavailable_reason"] is None
    assert metrics["data_source"] == "sec_audited_stale_fallback"


def test_net_income_stays_unavailable_with_no_fallback_at_all(monkeypatch):
    loader = _make_loader(monkeypatch, annual_fallback_net_income=None)
    row = _quality_row(net_income=None)

    metrics = loader._compute_quality_metrics("NODATA", row, ev_metrics=None)

    assert metrics["net_margin"] is None
    assert metrics["data_source"] == "sec_audited"
