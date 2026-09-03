"""Regression test: accruals_ratio_unavailable_reason must distinguish a filer with genuinely
no total_assets tagged from generic "missing_sec_data" - same mislabeled-genuine-gap bug class
as test_operating_cash_flow_accruals_ratio_reason_gate_20260902.py, but for the denominator
instead of the numerator.

Found live 2026-09-03 (SEC/XBRL missing-data sweep, generic missing_sec_data bucket
breakdown): accruals_ratio = (net_income - operating_cash_flow) / total_assets, so it also
fails whenever total_assets is None - but the reason gate only ever checked the OCF inputs
against the structural no-data gates, never total_assets, even though roa/debt_to_assets/
asset_turnover right below already reuse the exact same total_assets gates for the identical
cause. WPP/RTO (real net_income and operating_cash_flow every recent year, but total_assets
genuinely never tagged) fell to the generic fallback despite the specific cause already being
computable from an existing, reused gate.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(net_income=50_000_000.0, operating_cash_flow=60_000_000.0, total_assets=None):
    # 34-column shape (index 33 = prior_year_gross_profit).
    row = [None] * 34
    row[0] = 100_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = total_assets
    row[3] = net_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[13] = operating_cash_flow
    return row


class _FakeCursor:
    def __init__(self, no_recent_ta_symbols):
        self._no_recent_ta = no_recent_ta_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "annual_balance_sheet" in self._last_query and "total_assets" in self._last_query:
            return [(s,) for s in self._no_recent_ta]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, no_recent_ta_symbols=frozenset()):
        self._no_recent_ta = no_recent_ta_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._no_recent_ta)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, no_recent_ta_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(no_recent_ta_symbols))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestAccrualsRatioTotalAssetsReasonGate:
    def test_no_recent_total_assets_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_ta_symbols=frozenset({"WPP"}))
        row = _quality_row(total_assets=None)

        metrics = loader._compute_quality_metrics("WPP", row, ev_metrics=None)

        assert metrics["accruals_ratio"] is None
        assert metrics["accruals_ratio_unavailable_reason"] == "no_recent_total_assets_reported"

    def test_symbol_not_in_gate_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_ta_symbols=frozenset({"WPP"}))
        row = _quality_row(total_assets=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["accruals_ratio"] is None
        assert metrics["accruals_ratio_unavailable_reason"] == "missing_sec_data"

    def test_real_total_assets_still_computes_normally(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(net_income=50_000_000.0, operating_cash_flow=60_000_000.0, total_assets=700_000_000.0)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["accruals_ratio"] is not None
        assert metrics.get("accruals_ratio_unavailable_reason") is None
