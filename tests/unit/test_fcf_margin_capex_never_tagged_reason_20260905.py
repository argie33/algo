"""Regression test: quality_metrics.fcf_margin_unavailable_reason must distinguish a filer
with real operating_cash_flow but no capex-shaped XBRL concept in its 3 most recent fiscal
years (the same _get_no_recent_capex_symbols() gate value_metrics.fcf_yield's reason chain
already checks) from the generic "no_recent_free_cash_flow_reported" - a "fix landed at one
call site, never wired into the sibling" gap, same class as
debt_fallback_wiring_half_landed_recurring_bug_class_20260903 (memory).

Live-verified 2026-09-05 (goal session: "SEC/XBRL missing data" sweep) via AIG's real SEC
companyfacts: real operating_cash_flow every year, but its only capex-shaped concept
(PaymentsToAcquireProductiveAssets) stops after FY2023 - a genuine "filer stopped disclosing
this line" fact, not recoverable via the PPE-delta fallback either since AIG never tags a
standalone depreciation concept that fallback also needs.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(net_income=50_000_000.0, revenue=500_000_000.0, free_cash_flow=None):
    row = [None] * 34
    row[0] = 100_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = 700_000_000.0  # total_assets
    row[3] = net_income
    row[4] = revenue
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[14] = free_cash_flow
    return row


class _FakeCursor:
    def __init__(self, no_recent_capex_symbols):
        self._no_recent_capex = no_recent_capex_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "COUNT(capex)" in self._last_query:
            return [(s,) for s in self._no_recent_capex]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, no_recent_capex_symbols=frozenset()):
        self._no_recent_capex = no_recent_capex_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._no_recent_capex)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, no_recent_capex_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(no_recent_capex_symbols))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestFcfMarginCapexNeverTaggedReason:
    def test_no_recent_capex_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_capex_symbols=frozenset({"AIG"}))
        row = _quality_row(free_cash_flow=None)

        metrics = loader._compute_quality_metrics("AIG", row, ev_metrics=None)

        assert metrics["fcf_margin"] is None
        assert metrics["fcf_margin_unavailable_reason"] == "capex_never_tagged_in_recent_filings"

    def test_symbol_not_in_gate_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_capex_symbols=frozenset({"AIG"}))
        row = _quality_row(free_cash_flow=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["fcf_margin_unavailable_reason"] == "missing_sec_data"

    def test_real_fcf_margin_still_computes_normally(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_capex_symbols=frozenset({"AIG"}))
        row = _quality_row(free_cash_flow=60_000_000.0)

        metrics = loader._compute_quality_metrics("AIG", row, ev_metrics=None)

        assert metrics["fcf_margin"] is not None
        assert metrics.get("fcf_margin_unavailable_reason") is None
