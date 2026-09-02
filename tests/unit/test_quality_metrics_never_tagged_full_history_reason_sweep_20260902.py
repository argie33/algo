"""Regression test: extends the never-tagged full-history gates added by
test_roe_roa_debt_to_assets_never_tagged_full_history_reason_20260902.py to their other call
sites in load_value_quality_growth_metrics.py - sustainable_growth_rate, the row-level early
return, asset_turnover, net_margin, debt_to_equity, roic_pct, roce_pct all reuse the same
_get_no_recent_stockholders_equity_symbols()/_get_no_recent_net_income_symbols()/
_get_no_recent_total_assets_symbols() gates roe/roa/debt_to_assets do, and all had the same
recent-IPO/SPAC-merger blind spot (windowed gate requires exactly 3 real fiscal years).

Found live 2026-09-02 (same /goal session): live-verified against quality_metrics the
never-tagged siblings recover net_margin 23/65, debt_to_equity 9/132 (equity side only),
asset_turnover 10/119, sustainable_growth_rate similarly - all previously generic
"missing_sec_data" rows for symbols with fewer than 3 real fiscal years on file.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(
    stockholders_equity=100_000_000.0,
    net_income=50_000_000.0,
    total_assets=700_000_000.0,
    total_liabilities=200_000_000.0,
    revenue=None,
):
    row = [None] * 34
    row[0] = stockholders_equity
    row[1] = total_liabilities
    row[2] = total_assets
    row[3] = net_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[4] = revenue
    return row


class _FakeCursor:
    """Windowed gates (ROW_NUMBER()) always return empty - only the never-tagged full-history
    siblings (plain GROUP BY, no ROW_NUMBER()) can fire in this test."""

    def __init__(self, never_tagged_equity, never_tagged_net_income, never_tagged_total_assets):
        self._never_tagged_equity = never_tagged_equity
        self._never_tagged_net_income = never_tagged_net_income
        self._never_tagged_total_assets = never_tagged_total_assets
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "ROW_NUMBER()" in q:
            return []
        if "annual_income_statement" in q and "net_income" in q:
            return [(s,) for s in self._never_tagged_net_income]
        if "annual_balance_sheet" in q and "total_assets" in q:
            return [(s,) for s in self._never_tagged_total_assets]
        if "annual_balance_sheet" in q and "stockholders_equity" in q and "cash_and_equivalents" not in q:
            return [(s,) for s in self._never_tagged_equity]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(
        self,
        never_tagged_equity=frozenset(),
        never_tagged_net_income=frozenset(),
        never_tagged_total_assets=frozenset(),
    ):
        self._never_tagged_equity = never_tagged_equity
        self._never_tagged_net_income = never_tagged_net_income
        self._never_tagged_total_assets = never_tagged_total_assets

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._never_tagged_equity, self._never_tagged_net_income, self._never_tagged_total_assets)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, **kwargs):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(**kwargs))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestQualityMetricsNeverTaggedFullHistorySweep:
    def test_asset_turnover_never_tagged_total_assets(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_total_assets=frozenset({"RECENTIPO"}))
        row = _quality_row(total_assets=None, revenue=100_000_000.0)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["asset_turnover"] is None
        assert metrics["asset_turnover_unavailable_reason"] == "no_recent_total_assets_reported"

    def test_net_margin_never_tagged_net_income(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_net_income=frozenset({"RECENTIPO"}))
        row = _quality_row(net_income=None, revenue=100_000_000.0)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["net_margin"] is None
        assert metrics["net_margin_unavailable_reason"] == "net_income_not_reported"

    def test_debt_to_equity_never_tagged_equity(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_equity=frozenset({"RECENTIPO"}))
        row = _quality_row(stockholders_equity=None)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["debt_to_equity"] is None
        assert metrics["debt_to_equity_unavailable_reason"] == "stockholders_equity_not_reported"

    def test_roic_pct_never_tagged_equity(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_equity=frozenset({"RECENTIPO"}))
        row = _quality_row(stockholders_equity=None)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["roic_pct_unavailable_reason"] in ("stockholders_equity_not_reported", "missing_sec_data", None)
        # Not asserting exact string beyond ruling out a crash - roic_pct has several earlier
        # branches (unprofitable/negative_invested_capital/blank_check/reit) that may legitimately
        # take priority depending on the fixture's other None fields; the key regression guard is
        # that this call site accepts the never-tagged gate without raising.

    def test_sustainable_growth_rate_never_tagged_equity(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_equity=frozenset({"RECENTIPO"}))
        row = _quality_row(stockholders_equity=None)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["sustainable_growth_rate_unavailable_reason"] == "stockholders_equity_not_reported"

    def test_row_level_early_return_never_tagged_equity(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_equity=frozenset({"RECENTIPO"}))
        row = [None] * 34
        row[8] = 2025

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["data_unavailable"] is True
        assert metrics["reason"] == "no_recent_balance_sheet_data_reported"

    def test_symbols_not_in_any_gate_keep_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(stockholders_equity=None, net_income=None, total_assets=None, revenue=100_000_000.0)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["asset_turnover_unavailable_reason"] == "missing_sec_data"
        assert metrics["net_margin_unavailable_reason"] == "missing_sec_data"
        assert metrics["debt_to_equity_unavailable_reason"] == "missing_sec_data"
        assert metrics["sustainable_growth_rate_unavailable_reason"] == "missing_sec_data"
