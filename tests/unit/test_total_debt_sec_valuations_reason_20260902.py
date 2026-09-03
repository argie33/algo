"""Regression test: total_debt_unavailable_reason must reuse sec_valuations' own `reason`
column and the "no_sec_valuations_row" label - same fix `1547b826c` already applied to its
sibling fields total_cash_unavailable_reason/cash_per_share_unavailable_reason/
ebitda_unavailable_reason (see test_total_cash_cash_per_share_sec_valuations_reason_20260902.py),
but never extended to total_debt even though total_debt_ev comes from the exact same
ev_metrics tuple, one field above in the same file.

Found live 2026-09-02 (same /goal session, quality_row_db anchor-year investigation follow-
up): total_debt_unavailable_reason only ever checked the debt-components negative gates
(_get_no_recent_debt_components_symbols()/_get_never_tagged_debt_components_symbols()) and
fell straight to generic "missing_sec_data" otherwise - discarding a real sec_valuations
reason or the no-row case that its sibling fields on the identical row already surface.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor()

    def __exit__(self, *exc):
        return False


def _quality_row():
    # 34-column shape (index 33 = prior_year_gross_profit).
    row = [None] * 34
    row[0] = 100_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = 700_000_000.0  # total_assets
    row[3] = 50_000_000.0  # net_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[11] = 10_000_000.0  # shares_outstanding
    return row


class TestTotalDebtSecValuationsReason:
    def _loader(self, monkeypatch):
        import loaders.load_value_quality_growth_metrics as mod

        monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext())
        return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)

    def test_no_sec_valuations_row_gets_dedicated_reason(self, monkeypatch):
        loader = self._loader(monkeypatch)

        metrics = loader._compute_quality_metrics("NOROW", _quality_row(), ev_metrics=None)

        assert metrics["total_debt"] is None
        assert metrics["total_debt_unavailable_reason"] == "no_sec_valuations_row"

    def test_sec_valuations_reason_propagates(self, monkeypatch):
        loader = self._loader(monkeypatch)
        # (total_debt, total_cash, ebitda, reason) - total_debt is None, but sec_valuations
        # already recorded a real, specific reason for this row.
        ev_metrics = (None, None, None, "income_statement_revenue_and_eps_null")

        metrics = loader._compute_quality_metrics("HASREASON", _quality_row(), ev_metrics=ev_metrics)

        assert metrics["total_debt"] is None
        assert metrics["total_debt_unavailable_reason"] == "income_statement_revenue_and_eps_null"

    def test_row_exists_no_reason_keeps_generic_reason(self, monkeypatch):
        loader = self._loader(monkeypatch)
        ev_metrics = (None, None, None, None)

        metrics = loader._compute_quality_metrics("NOREASON", _quality_row(), ev_metrics=ev_metrics)

        assert metrics["total_debt"] is None
        assert metrics["total_debt_unavailable_reason"] == "missing_sec_data"

    def test_legacy_3tuple_ev_metrics_still_works(self, monkeypatch):
        # Backward compatibility: older callers/tests may still pass a bare 3-tuple with no
        # reason column - must not raise an IndexError.
        loader = self._loader(monkeypatch)
        ev_metrics = (None, None, None)

        metrics = loader._compute_quality_metrics("LEGACY", _quality_row(), ev_metrics=ev_metrics)

        assert metrics["total_debt"] is None
        assert metrics["total_debt_unavailable_reason"] == "missing_sec_data"

    def test_debt_components_gate_still_takes_priority_over_sec_valuations_reason(self, monkeypatch):
        """A symbol that genuinely never itemizes debt components must keep the more
        specific, better-tested "total_debt_not_itemized" label even when sec_valuations
        also happens to carry an unrelated reason string on the same row."""
        loader = self._loader(monkeypatch)
        loader._never_tagged_debt_components_symbols_cache = frozenset({"NODEBT"})
        loader._no_recent_debt_components_symbols_cache = frozenset()
        ev_metrics = (None, None, None, "income_statement_revenue_and_eps_null")

        metrics = loader._compute_quality_metrics("NODEBT", _quality_row(), ev_metrics=ev_metrics)

        assert metrics["total_debt"] is None
        assert metrics["total_debt_unavailable_reason"] == "total_debt_not_itemized"

    def test_real_total_debt_still_computes_normally(self, monkeypatch):
        loader = self._loader(monkeypatch)
        ev_metrics = (300_000_000.0, 50_000_000.0, 0.0, None)

        metrics = loader._compute_quality_metrics("NORMALCO", _quality_row(), ev_metrics=ev_metrics)

        assert metrics["total_debt"] == 300_000_000.0
        assert metrics.get("total_debt_unavailable_reason") is None
