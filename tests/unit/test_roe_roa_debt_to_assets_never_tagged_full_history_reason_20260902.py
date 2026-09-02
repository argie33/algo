"""Regression test: roe/roa/debt_to_assets_unavailable_reason must reuse their existing
specific reason labels for a symbol that has never once tagged the required field ANYWHERE in
its filing history, even when it doesn't yet have the 3 consecutive real fiscal years the
existing windowed gates (_get_no_recent_stockholders_equity_symbols() etc.) require - not just
fall through to the generic "missing_sec_data". Same pattern as
test_interest_coverage_never_tagged_full_history_reason_20260902.py, applied to the 4 gates
(stockholders_equity, net_income, total_assets, total_liabilities) roe/roa/debt_to_assets share.

Found live 2026-09-02: of roe's 68 universe "missing_sec_data" rows, the never-tagged full-
history stockholders_equity+net_income gates together match 27 (vs 9 for equity alone); roa's
70 rows match 28 (vs 10 for total_assets alone); debt_to_assets' 31 rows match 11 via
total_assets+total_liabilities together.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(
    stockholders_equity=100_000_000.0,
    net_income=50_000_000.0,
    total_assets=700_000_000.0,
    total_liabilities=200_000_000.0,
):
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
    """Distinguishes the windowed (ROW_NUMBER()/rn<=3) gate queries from their never-tagged
    full-history (no ROW_NUMBER(), plain GROUP BY) siblings by SQL shape, not just table/column
    substrings - both query families touch the same tables and columns."""

    def __init__(
        self, never_tagged_equity, never_tagged_net_income, never_tagged_total_assets, never_tagged_total_liab
    ):
        self._never_tagged_equity = never_tagged_equity
        self._never_tagged_net_income = never_tagged_net_income
        self._never_tagged_total_assets = never_tagged_total_assets
        self._never_tagged_total_liab = never_tagged_total_liab
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "ROW_NUMBER()" in q:
            return []  # windowed gates: empty, so only the never-tagged siblings can fire
        if "annual_income_statement" in q and "net_income" in q:
            return [(s,) for s in self._never_tagged_net_income]
        if "annual_balance_sheet" in q and "total_liabilities" in q:
            return [(s,) for s in self._never_tagged_total_liab]
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
        never_tagged_total_liab=frozenset(),
    ):
        self._never_tagged_equity = never_tagged_equity
        self._never_tagged_net_income = never_tagged_net_income
        self._never_tagged_total_assets = never_tagged_total_assets
        self._never_tagged_total_liab = never_tagged_total_liab

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(
            self._never_tagged_equity,
            self._never_tagged_net_income,
            self._never_tagged_total_assets,
            self._never_tagged_total_liab,
        )

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, **kwargs):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(**kwargs))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestRoeRoaDebtToAssetsNeverTaggedFullHistoryReason:
    def test_roe_never_tagged_equity_only_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_equity=frozenset({"RECENTIPO"}))
        row = _quality_row(stockholders_equity=None)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["roe"] is None
        assert metrics["roe_unavailable_reason"] == "stockholders_equity_not_reported"

    def test_roe_never_tagged_net_income_only_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_net_income=frozenset({"RECENTIPO"}))
        row = _quality_row(net_income=None)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["roe"] is None
        assert metrics["roe_unavailable_reason"] == "net_income_not_reported"

    def test_roa_never_tagged_total_assets_only_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_total_assets=frozenset({"RECENTIPO"}))
        row = _quality_row(total_assets=None)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["roa"] is None
        assert metrics["roa_unavailable_reason"] == "no_recent_total_assets_reported"

    def test_debt_to_assets_never_tagged_total_liabilities_only_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_total_liab=frozenset({"RECENTIPO"}))
        row = _quality_row(total_liabilities=None)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["debt_to_assets"] is None
        assert metrics["debt_to_assets_unavailable_reason"] == "total_liabilities_not_reported"

    def test_symbol_not_in_any_gate_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(stockholders_equity=None, net_income=None, total_assets=None, total_liabilities=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["roe_unavailable_reason"] == "missing_sec_data"
        assert metrics["roa_unavailable_reason"] == "missing_sec_data"
        assert metrics["debt_to_assets_unavailable_reason"] == "missing_sec_data"
