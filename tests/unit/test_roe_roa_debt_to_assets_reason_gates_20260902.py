"""Regression test: roe/roa/debt_to_assets_unavailable_reason must distinguish a genuine SEC
extraction gap (no net_income/equity/assets/liabilities in the 3 most recent fiscal years) from
generic "missing_sec_data" - same mislabeled-genuine-gap bug class as debt_to_equity/
asset_turnover/roic_pct/roce_pct fixed earlier this session.

Found live 2026-09-02: roe/roa/debt_to_assets had zero reason gating - 100% (or near-100%)
generic "missing_sec_data" despite each depending on inputs that already have (or now have)
dedicated structural gates. Live-confirmed 62/133 (47%) roe, 54/124 (44%) roa, 57/88 (65%)
debt_to_assets rows are these exact gaps.
"""

import pytest

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(
    stockholders_equity=100_000_000.0,
    net_income=50_000_000.0,
    total_assets=700_000_000.0,
    total_liabilities=200_000_000.0,
):
    # 34-column shape (index 33 = prior_year_gross_profit).
    row = [None] * 34
    row[0] = stockholders_equity
    row[1] = total_liabilities
    row[2] = total_assets
    row[3] = net_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    return row


class _FakeCursor:
    def __init__(self, no_recent_equity, no_recent_net_income, no_recent_total_assets, no_recent_total_liab):
        self._no_recent_equity = no_recent_equity
        self._no_recent_net_income = no_recent_net_income
        self._no_recent_total_assets = no_recent_total_assets
        self._no_recent_total_liab = no_recent_total_liab
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "annual_income_statement" in q and "net_income" in q:
            return [(s,) for s in self._no_recent_net_income]
        if "annual_balance_sheet" in q and "total_liabilities" in q:
            return [(s,) for s in self._no_recent_total_liab]
        if "annual_balance_sheet" in q and "total_assets" in q:
            return [(s,) for s in self._no_recent_total_assets]
        if "annual_balance_sheet" in q and "stockholders_equity" in q and "cash_and_equivalents" not in q:
            return [(s,) for s in self._no_recent_equity]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(
        self,
        no_recent_equity=frozenset(),
        no_recent_net_income=frozenset(),
        no_recent_total_assets=frozenset(),
        no_recent_total_liab=frozenset(),
    ):
        self._no_recent_equity = no_recent_equity
        self._no_recent_net_income = no_recent_net_income
        self._no_recent_total_assets = no_recent_total_assets
        self._no_recent_total_liab = no_recent_total_liab

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(
            self._no_recent_equity,
            self._no_recent_net_income,
            self._no_recent_total_assets,
            self._no_recent_total_liab,
        )

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, **kwargs):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(**kwargs))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestRoeRoaDebtToAssetsReasonGates:
    def test_roe_no_recent_equity_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_equity=frozenset({"NOEQ"}))
        row = _quality_row(stockholders_equity=None)

        metrics = loader._compute_quality_metrics("NOEQ", row, ev_metrics=None)

        assert metrics["roe"] is None
        assert metrics["roe_unavailable_reason"] == "stockholders_equity_not_reported"

    def test_roe_no_recent_net_income_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_net_income=frozenset({"NOEARN"}))
        row = _quality_row(net_income=None)

        metrics = loader._compute_quality_metrics("NOEARN", row, ev_metrics=None)

        assert metrics["roe"] is None
        assert metrics["roe_unavailable_reason"] == "net_income_not_reported"

    def test_roa_no_recent_total_assets_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_total_assets=frozenset({"NOASSETS"}))
        row = _quality_row(total_assets=None)

        metrics = loader._compute_quality_metrics("NOASSETS", row, ev_metrics=None)

        assert metrics["roa"] is None
        assert metrics["roa_unavailable_reason"] == "no_recent_total_assets_reported"

    def test_roa_no_recent_net_income_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_net_income=frozenset({"NOEARN"}))
        row = _quality_row(net_income=None)

        metrics = loader._compute_quality_metrics("NOEARN", row, ev_metrics=None)

        assert metrics["roa"] is None
        assert metrics["roa_unavailable_reason"] == "net_income_not_reported"

    def test_debt_to_assets_no_recent_total_liabilities_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_total_liab=frozenset({"NOLIAB"}))
        row = _quality_row(total_liabilities=None)

        metrics = loader._compute_quality_metrics("NOLIAB", row, ev_metrics=None)

        assert metrics["debt_to_assets"] is None
        assert metrics["debt_to_assets_unavailable_reason"] == "total_liabilities_not_reported"

    def test_symbols_not_in_any_gate_keep_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(stockholders_equity=None, net_income=None, total_assets=None, total_liabilities=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["roe_unavailable_reason"] == "missing_sec_data"
        assert metrics["roa_unavailable_reason"] == "missing_sec_data"
        assert metrics["debt_to_assets_unavailable_reason"] == "missing_sec_data"

    def test_real_inputs_still_compute_normally(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row()

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["roe"] == 50.0
        assert metrics["roa"] == pytest.approx(50_000_000.0 / 700_000_000.0 * 100.0)
        assert metrics["debt_to_assets"] == pytest.approx(200_000_000.0 / 700_000_000.0)
        assert metrics.get("roe_unavailable_reason") is None
        assert metrics.get("roa_unavailable_reason") is None
        assert metrics.get("debt_to_assets_unavailable_reason") is None
