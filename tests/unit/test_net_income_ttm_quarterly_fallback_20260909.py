"""Regression test for the 2026-09-09 fix (goal: SEC/XBRL missing-data count under 700):
recent IPOs (and pre-IPO S-1 stub annual rows) can have a real annual_balance_sheet anchor row
but no usable annual_income_statement.net_income - no 10-K filed yet, only 10-Qs. Previously
this fell straight to "net_income_not_reported" even when the symbol has 4+ real quarters of
SEC-reported net_income sitting in quarterly_income_statement, cascading into roa/roe/
net_margin/sustainable_growth_rate/payout_ratio all going unavailable together.

`_fetch_ttm_net_income_from_quarterly` sums the 4 most recent real quarters as a TTM figure,
only when all 4 exist (never fabricates a partial-year number from 1-3 quarters).
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
    def __init__(self, quarterly_net_incomes):
        self._quarterly_net_incomes = quarterly_net_incomes
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "FROM quarterly_income_statement" in self._last_query:
            return [(v,) for v in self._quarterly_net_incomes]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, quarterly_net_incomes):
        self._quarterly_net_incomes = quarterly_net_incomes

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._quarterly_net_incomes)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, quarterly_net_incomes):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(quarterly_net_incomes))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def test_net_income_recovered_from_four_real_quarters(monkeypatch):
    loader = _make_loader(monkeypatch, [10_000_000.0, 12_000_000.0, 9_000_000.0, 11_000_000.0])
    row = _quality_row(net_income=None)

    metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

    assert metrics["net_margin"] is not None
    assert metrics["net_margin_unavailable_reason"] is None
    assert metrics["data_source"] == "sec_audited_ttm_quarterly"


def test_net_income_not_recovered_from_fewer_than_four_quarters(monkeypatch):
    loader = _make_loader(monkeypatch, [10_000_000.0, 12_000_000.0])
    row = _quality_row(net_income=None)

    metrics = loader._compute_quality_metrics("TOOFRESH", row, ev_metrics=None)

    assert metrics["net_margin"] is None
    assert metrics["data_source"] == "sec_audited"


def test_annual_net_income_preferred_over_quarterly_when_present(monkeypatch):
    loader = _make_loader(monkeypatch, [10_000_000.0, 12_000_000.0, 9_000_000.0, 11_000_000.0])
    row = _quality_row(net_income=50_000_000.0)

    metrics = loader._compute_quality_metrics("NORMAL", row, ev_metrics=None)

    assert metrics["data_source"] == "sec_audited"
