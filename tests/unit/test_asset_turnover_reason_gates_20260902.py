"""Regression test: asset_turnover_unavailable_reason must distinguish a genuinely revenue-less
filer or one with no extractable total_assets concept (predominantly foreign private issuers
filing under IFRS) from a real SEC extraction gap.

Found live 2026-09-02 (goal: "no SEC data" audit continuation, same mislabeled-genuine-gap bug
class as debt_to_equity's fix): asset_turnover's compute block fails whenever revenue or
total_assets is None, but the reason was 100% unlabeled generic "missing_sec_data" - no gate at
all, unlike sibling ratios. Live-confirmed 206 of 294 universe asset_turnover "missing_sec_data"
rows (70%) split between genuinely revenue-less filers (153, reusing the existing
_get_no_recent_revenue_symbols() gate) and FPIs with no extractable total_assets concept (53,
new _get_no_recent_total_assets_symbols() gate).
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(revenue=None, total_assets=700_000_000.0):
    # 34-column shape (index 33 = prior_year_gross_profit).
    row = [None] * 34
    row[0] = 100_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = total_assets
    row[3] = 50_000_000.0  # net_income
    row[4] = revenue
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    return row


class _FakeCursor:
    def __init__(self, no_recent_revenue_symbols, no_recent_total_assets_symbols):
        self._no_recent_revenue = no_recent_revenue_symbols
        self._no_recent_total_assets = no_recent_total_assets_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "annual_income_statement" in q and "revenue" in q:
            return [(s,) for s in self._no_recent_revenue]
        if "annual_balance_sheet" in q and "total_assets" in q:
            return [(s,) for s in self._no_recent_total_assets]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, no_recent_revenue_symbols=frozenset(), no_recent_total_assets_symbols=frozenset()):
        self._no_recent_revenue = no_recent_revenue_symbols
        self._no_recent_total_assets = no_recent_total_assets_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._no_recent_revenue, self._no_recent_total_assets)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, no_recent_revenue_symbols=frozenset(), no_recent_total_assets_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(
        mod,
        "DatabaseContext",
        _FakeDatabaseContext(no_recent_revenue_symbols, no_recent_total_assets_symbols),
    )
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestAssetTurnoverReasonGates:
    def test_no_recent_revenue_gets_no_revenue_reported(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_revenue_symbols=frozenset({"PRECO"}))
        row = _quality_row(revenue=None)

        metrics = loader._compute_quality_metrics("PRECO", row, ev_metrics=None)

        assert metrics["asset_turnover"] is None
        assert metrics["asset_turnover_unavailable_reason"] == "no_revenue_reported"

    def test_no_recent_total_assets_gets_dedicated_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_total_assets_symbols=frozenset({"FPICO"}))
        row = _quality_row(revenue=500_000_000.0, total_assets=None)

        metrics = loader._compute_quality_metrics("FPICO", row, ev_metrics=None)

        assert metrics["asset_turnover"] is None
        assert metrics["asset_turnover_unavailable_reason"] == "no_recent_total_assets_reported"

    def test_symbol_not_in_either_set_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(revenue=None, total_assets=700_000_000.0)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["asset_turnover"] is None
        assert metrics["asset_turnover_unavailable_reason"] == "missing_sec_data"

    def test_real_inputs_still_compute_normally(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(revenue=350_000_000.0, total_assets=700_000_000.0)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["asset_turnover"] == 50.0
        assert metrics.get("asset_turnover_unavailable_reason") is None
