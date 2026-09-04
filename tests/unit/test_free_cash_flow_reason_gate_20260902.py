"""Regression test: free_cash_flow/fcf_to_net_income/fcf_margin_unavailable_reason must
distinguish a filer with genuinely no free_cash_flow (or, for fcf_margin, no revenue) in its 3
most recent fiscal years from generic "missing_sec_data" - same mislabeled-genuine-gap bug class
as operating_cash_flow/accruals_ratio (test_operating_cash_flow_accruals_ratio_reason_gate_20260902.py).

Found live 2026-09-02: free_cash_flow is read straight off the anchor row with no cross-year
fallback (deliberately - see _get_no_recent_free_cash_flow_symbols()'s docstring). 228 of 424
universe free_cash_flow "missing_sec_data" rows (54%) are genuinely no-FCF-anywhere - the rest
have FCF in an off-anchor year, a separate anchor-row-selection question deliberately NOT chased.
fcf_margin already does its own cross-year fallback for (free_cash_flow, revenue) jointly, so a
remaining None there means both inputs are genuinely absent (359 of 552 rows, 65%, covered by
either gate).
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(net_income=50_000_000.0, revenue=None, free_cash_flow=None, total_assets=700_000_000.0):
    # 34-column shape (index 33 = prior_year_gross_profit).
    row = [None] * 34
    row[0] = 100_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = total_assets
    row[3] = net_income
    row[4] = revenue
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[14] = free_cash_flow
    return row


class _FakeCursor:
    def __init__(self, no_recent_fcf_symbols, no_recent_revenue_symbols):
        self._no_recent_fcf = no_recent_fcf_symbols
        self._no_recent_revenue = no_recent_revenue_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "annual_cash_flow" in q and "free_cash_flow" in q and "COUNT(free_cash_flow)" in q:
            return [(s,) for s in self._no_recent_fcf]
        if "WITH recent AS" in q and "revenue" in q:
            return [(s,) for s in self._no_recent_revenue]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, no_recent_fcf_symbols=frozenset(), no_recent_revenue_symbols=frozenset()):
        self._no_recent_fcf = no_recent_fcf_symbols
        self._no_recent_revenue = no_recent_revenue_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._no_recent_fcf, self._no_recent_revenue)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, no_recent_fcf_symbols=frozenset(), no_recent_revenue_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(no_recent_fcf_symbols, no_recent_revenue_symbols))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestFreeCashFlowReasonGate:
    def test_no_recent_fcf_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_fcf_symbols=frozenset({"NOFCF"}))
        row = _quality_row(free_cash_flow=None, revenue=500_000_000.0)

        metrics = loader._compute_quality_metrics("NOFCF", row, ev_metrics=None)

        assert metrics["free_cash_flow"] is None
        assert metrics["free_cash_flow_unavailable_reason"] == "no_recent_free_cash_flow_reported"
        assert metrics["fcf_to_net_income"] is None
        assert metrics["fcf_to_net_income_unavailable_reason"] == "no_recent_free_cash_flow_reported"
        assert metrics["fcf_margin"] is None
        assert metrics["fcf_margin_unavailable_reason"] == "no_recent_free_cash_flow_reported"

    def test_no_recent_revenue_gets_specific_fcf_margin_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_revenue_symbols=frozenset({"NOREV"}))
        row = _quality_row(free_cash_flow=None, revenue=None)

        metrics = loader._compute_quality_metrics("NOREV", row, ev_metrics=None)

        assert metrics["fcf_margin"] is None
        assert metrics["fcf_margin_unavailable_reason"] == "no_revenue_reported"

    def test_symbol_not_in_gate_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_fcf_symbols=frozenset({"NOFCF"}))
        row = _quality_row(free_cash_flow=None, revenue=500_000_000.0)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["free_cash_flow"] is None
        assert metrics["free_cash_flow_unavailable_reason"] == "missing_sec_data"
        assert metrics["fcf_to_net_income"] is None
        assert metrics["fcf_to_net_income_unavailable_reason"] == "missing_sec_data"
        assert metrics["fcf_margin"] is None
        assert metrics["fcf_margin_unavailable_reason"] == "missing_sec_data"

    def test_real_fcf_still_computes_normally(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(net_income=50_000_000.0, revenue=500_000_000.0, free_cash_flow=60_000_000.0)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["free_cash_flow"] == 60_000_000.0
        assert metrics.get("free_cash_flow_unavailable_reason") is None
        assert metrics["fcf_to_net_income"] is not None
        assert metrics.get("fcf_to_net_income_unavailable_reason") is None
        assert metrics["fcf_margin"] is not None
        assert metrics.get("fcf_margin_unavailable_reason") is None
