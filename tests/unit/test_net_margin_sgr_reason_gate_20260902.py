"""Regression test: net_margin/sustainable_growth_rate_unavailable_reason must distinguish a
genuine SEC extraction gap (no net_income/stockholders_equity in the 3 most recent fiscal years)
from generic "missing_sec_data" - same mislabeled-genuine-gap bug class as
test_roe_roa_debt_to_assets_reason_gates_20260902.py.

Found live 2026-09-02: net_margin/sustainable_growth_rate both fail whenever net_income (and,
for sustainable_growth_rate, stockholders_equity) is None, but neither reused the existing
net_income_not_reported/stockholders_equity_not_reported gates already wired into roe/roa above
them in the same file. Live-confirmed 28/111 (25%) net_margin, 62/181 (34%)
sustainable_growth_rate rows are these exact gaps.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(
    stockholders_equity=100_000_000.0,
    net_income=50_000_000.0,
    revenue=500_000_000.0,
    total_assets=700_000_000.0,
):
    # 34-column shape (index 33 = prior_year_gross_profit).
    row = [None] * 34
    row[0] = stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = total_assets
    row[3] = net_income
    row[4] = revenue
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    return row


class _FakeCursor:
    def __init__(self, no_recent_equity, no_recent_net_income):
        self._no_recent_equity = no_recent_equity
        self._no_recent_net_income = no_recent_net_income
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "annual_income_statement" in q and "net_income" in q:
            return [(s,) for s in self._no_recent_net_income]
        # "etf_symbols" excluded 2026-09-05 (real-money-readiness audit): a newer sibling gate
        # (_get_etf_trust_no_stockholders_equity_symbols, vqg_symbol_gates.py) also queries
        # annual_balance_sheet+stockholders_equity (joined against etf_symbols) and was
        # otherwise indistinguishable from this fixture's own no-recent-equity query.
        if (
            "annual_balance_sheet" in q
            and "stockholders_equity" in q
            and "cash_and_equivalents" not in q
            and "etf_symbols" not in q
        ):
            return [(s,) for s in self._no_recent_equity]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, no_recent_equity=frozenset(), no_recent_net_income=frozenset()):
        self._no_recent_equity = no_recent_equity
        self._no_recent_net_income = no_recent_net_income

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._no_recent_equity, self._no_recent_net_income)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, **kwargs):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(**kwargs))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestNetMarginSgrReasonGate:
    def test_net_margin_no_recent_net_income_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_net_income=frozenset({"NOEARN"}))
        row = _quality_row(net_income=None)

        metrics = loader._compute_quality_metrics("NOEARN", row, ev_metrics=None)

        assert metrics["net_margin"] is None
        assert metrics["net_margin_unavailable_reason"] == "net_income_not_reported"

    def test_net_margin_symbol_not_in_gate_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(net_income=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["net_margin"] is None
        assert metrics["net_margin_unavailable_reason"] == "missing_sec_data"

    def test_net_margin_real_inputs_still_compute_normally(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row()

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["net_margin"] == 10.0
        assert metrics.get("net_margin_unavailable_reason") is None

    def test_sgr_no_recent_equity_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_equity=frozenset({"NOEQ"}))
        row = _quality_row(stockholders_equity=None)

        metrics = loader._compute_quality_metrics("NOEQ", row, ev_metrics=None)

        assert metrics["sustainable_growth_rate"] is None
        assert metrics["sustainable_growth_rate_unavailable_reason"] == "stockholders_equity_not_reported"

    def test_sgr_no_recent_net_income_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_net_income=frozenset({"NOEARN"}))
        row = _quality_row(net_income=None)

        metrics = loader._compute_quality_metrics("NOEARN", row, ev_metrics=None)

        assert metrics["sustainable_growth_rate"] is None
        assert metrics["sustainable_growth_rate_unavailable_reason"] == "net_income_not_reported"

    def test_sgr_symbol_not_in_any_gate_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(stockholders_equity=None, net_income=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["sustainable_growth_rate"] is None
        assert metrics["sustainable_growth_rate_unavailable_reason"] == "missing_sec_data"

    def test_sgr_real_inputs_still_compute_normally(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row()

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["sustainable_growth_rate"] is not None
        assert metrics.get("sustainable_growth_rate_unavailable_reason") is None
