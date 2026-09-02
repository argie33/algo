"""Regression test: operating_cash_flow/accruals_ratio_unavailable_reason must distinguish a
filer with genuinely no operating_cash_flow in its 3 most recent fiscal years from generic
"missing_sec_data" - same mislabeled-genuine-gap bug class as the earlier fixes this session.

Found live 2026-09-02: operating_cash_flow is read straight off the anchor row with no
cross-year fallback (deliberately - see _get_no_recent_operating_cash_flow_symbols()'s
docstring). Only 43 of 125 universe operating_cash_flow "missing_sec_data" rows (34%) are
genuinely no-OCF-anywhere - the rest have OCF in an off-anchor year, a separate
anchor-row-selection question deliberately NOT chased (it would change computed VALUES via
cross-year mixing, not just relabel). This test covers only the label-only, unambiguous slice.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(net_income=50_000_000.0, operating_cash_flow=None, total_assets=700_000_000.0):
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
    def __init__(self, no_recent_ocf_symbols):
        self._no_recent_ocf = no_recent_ocf_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "annual_cash_flow" in self._last_query and "operating_cash_flow" in self._last_query:
            return [(s,) for s in self._no_recent_ocf]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, no_recent_ocf_symbols=frozenset()):
        self._no_recent_ocf = no_recent_ocf_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._no_recent_ocf)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, no_recent_ocf_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(no_recent_ocf_symbols))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestOperatingCashFlowAccrualsRatioReasonGate:
    def test_no_recent_ocf_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_ocf_symbols=frozenset({"NOOCF"}))
        row = _quality_row(operating_cash_flow=None)

        metrics = loader._compute_quality_metrics("NOOCF", row, ev_metrics=None)

        assert metrics["operating_cash_flow"] is None
        assert metrics["operating_cash_flow_unavailable_reason"] == "no_recent_operating_cash_flow_reported"
        assert metrics["accruals_ratio"] is None
        assert metrics["accruals_ratio_unavailable_reason"] == "no_recent_operating_cash_flow_reported"
        assert metrics["ocf_to_net_income"] is None
        assert metrics["ocf_to_net_income_unavailable_reason"] == "no_recent_operating_cash_flow_reported"

    def test_symbol_not_in_gate_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_ocf_symbols=frozenset({"NOOCF"}))
        row = _quality_row(operating_cash_flow=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["operating_cash_flow"] is None
        assert metrics["operating_cash_flow_unavailable_reason"] == "missing_sec_data"
        assert metrics["accruals_ratio"] is None
        assert metrics["accruals_ratio_unavailable_reason"] == "missing_sec_data"
        assert metrics["ocf_to_net_income"] is None
        assert metrics["ocf_to_net_income_unavailable_reason"] == "missing_sec_data"

    def test_real_ocf_still_computes_normally(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(net_income=50_000_000.0, operating_cash_flow=60_000_000.0, total_assets=700_000_000.0)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["operating_cash_flow"] == 60_000_000.0
        assert metrics.get("operating_cash_flow_unavailable_reason") is None
        assert metrics["accruals_ratio"] is not None
        assert metrics.get("accruals_ratio_unavailable_reason") is None
        assert metrics["ocf_to_net_income"] is not None
        assert metrics.get("ocf_to_net_income_unavailable_reason") is None
