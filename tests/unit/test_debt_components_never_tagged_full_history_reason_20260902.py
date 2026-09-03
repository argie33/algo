"""Regression test: total_debt/debt_to_equity/roic_pct/roce_pct_unavailable_reason must reuse
"total_debt_not_itemized" for a symbol that has never once tagged any debt component (long_term_
debt, short_term_debt, operating_lease_liability, finance_lease_liability) ANYWHERE in its
filing history, even when it doesn't yet have the 3 consecutive real fiscal years
_get_no_recent_debt_components_symbols() requires - not just fall through to generic
"missing_sec_data".

Found live 2026-09-02 (same /goal session as the roe/roa/debt_to_assets and 6-more-call-sites
fixes): this is the single largest never-tagged-gate win found this session - live-verified
against quality_metrics debt_to_equity 115 of 132 (87%), roce_pct 115 of 198 (58%), roic_pct 97
of 215 (45%), total_debt 33 of 49 (67%) of their respective "missing_sec_data" residual rows
recovered. Deliberately NOT wired into value_metrics.ev_revenue/ev_ebitda_unavailable_reason -
live-checked only 14/232 and 1/49 rows overlap there, consistent with load_sec_valuations.py's
EV computation treating missing total_debt as 0 rather than blocking (a different, still-open
root cause - see [[interest_coverage_and_pe_ratio_reason_gates_fixed_20260902]]).
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(stockholders_equity=100_000_000.0, net_income=50_000_000.0, total_assets=700_000_000.0):
    row = [None] * 34
    row[0] = stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = total_assets
    row[3] = net_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    return row


class _FakeCursor:
    """Windowed gates (ROW_NUMBER()) always return empty - only the never-tagged full-history
    debt-components sibling (plain GROUP BY, no ROW_NUMBER()) can fire in this test."""

    def __init__(self, never_tagged_debt):
        self._never_tagged_debt = never_tagged_debt
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "ROW_NUMBER()" in q:
            return []
        if "long_term_debt" in q:
            return [(s,) for s in self._never_tagged_debt]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, never_tagged_debt=frozenset()):
        self._never_tagged_debt = never_tagged_debt

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._never_tagged_debt)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, never_tagged_debt=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(never_tagged_debt))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestDebtComponentsNeverTaggedFullHistoryReason:
    def test_total_debt_never_tagged_debt_components(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_debt=frozenset({"RECENTIPO"}))

        metrics = loader._compute_quality_metrics("RECENTIPO", _quality_row(), ev_metrics=None)

        assert metrics["total_debt"] is None
        assert metrics["total_debt_unavailable_reason"] == "total_debt_not_itemized"

    def test_debt_to_equity_never_tagged_debt_components(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_debt=frozenset({"RECENTIPO"}))

        metrics = loader._compute_quality_metrics("RECENTIPO", _quality_row(), ev_metrics=None)

        assert metrics["debt_to_equity"] is None
        assert metrics["debt_to_equity_unavailable_reason"] == "total_debt_not_itemized"

    def test_roic_pct_never_tagged_debt_components(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_debt=frozenset({"RECENTIPO"}))

        metrics = loader._compute_quality_metrics("RECENTIPO", _quality_row(), ev_metrics=None)

        assert metrics["roic_pct_unavailable_reason"] == "total_debt_not_itemized"

    def test_roce_pct_never_tagged_debt_components(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_debt=frozenset({"RECENTIPO"}))

        metrics = loader._compute_quality_metrics("RECENTIPO", _quality_row(), ev_metrics=None)

        assert metrics["roce_pct_unavailable_reason"] == "total_debt_not_itemized"

    def test_symbol_not_in_gate_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)

        metrics = loader._compute_quality_metrics("NORMALCO", _quality_row(), ev_metrics=None)

        # total_debt reads ev_metrics=None as "no sec_valuations row at all" since bf82fc6d0
        # wired total_debt into the same no_sec_valuations_row/sec_valuations.reason
        # propagation its sibling fields (total_cash/cash_per_share/ebitda) already had - the
        # real, more specific cause, not the generic fallback this test originally asserted.
        assert metrics["total_debt_unavailable_reason"] == "no_sec_valuations_row"
        # debt_to_equity doesn't read from ev_metrics/sec_valuations at all (it uses
        # debt_for_roic and its own quality_row-derived gates), so it's unaffected and still
        # correctly falls through to the generic label here.
        assert metrics["debt_to_equity_unavailable_reason"] == "missing_sec_data"
