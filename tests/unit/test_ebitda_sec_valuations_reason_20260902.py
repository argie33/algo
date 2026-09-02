"""Regression test: quality_metrics.ebitda_unavailable_reason must reuse sec_valuations' own
`reason` column, same fix/pattern as total_cash/cash_per_share
(test_total_cash_cash_per_share_sec_valuations_reason_20260902.py) - ebitda_ev comes from the
exact same ev_metrics tuple as total_cash_ev, just never got the same treatment.

Found live 2026-09-02: ebitda_unavailable_reason only checked the REIT/no-tax-concept gate
before falling to generic "missing_sec_data", never sec_valuations.reason one column away.
Live-confirmed 78 of 119 (66%) of the remaining ebitda missing_sec_data rows have a
sec_valuations row with a real reason; 27 more have no sec_valuations row at all.
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


class TestEbitdaSecValuationsReason:
    def _loader(self, monkeypatch):
        import loaders.load_value_quality_growth_metrics as mod

        monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext())
        return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)

    def test_no_sec_valuations_row_gets_dedicated_reason(self, monkeypatch):
        loader = self._loader(monkeypatch)

        metrics = loader._compute_quality_metrics("NOROW", _quality_row(), ev_metrics=None)

        assert metrics["ebitda"] is None
        assert metrics["ebitda_unavailable_reason"] == "no_sec_valuations_row"

    def test_sec_valuations_reason_propagates(self, monkeypatch):
        loader = self._loader(monkeypatch)
        # (total_debt, total_cash, ebitda, reason) - ebitda is None, but sec_valuations already
        # recorded a real, specific reason for this row.
        ev_metrics = (100_000_000.0, 50_000_000.0, None, "income_statement_revenue_and_eps_null")

        metrics = loader._compute_quality_metrics("HASREASON", _quality_row(), ev_metrics=ev_metrics)

        assert metrics["ebitda"] is None
        assert metrics["ebitda_unavailable_reason"] == "income_statement_revenue_and_eps_null"

    def test_row_exists_no_reason_keeps_generic_reason(self, monkeypatch):
        loader = self._loader(monkeypatch)
        ev_metrics = (100_000_000.0, 50_000_000.0, None, None)

        metrics = loader._compute_quality_metrics("NOREASON", _quality_row(), ev_metrics=ev_metrics)

        assert metrics["ebitda"] is None
        assert metrics["ebitda_unavailable_reason"] == "missing_sec_data"

    def test_legacy_3tuple_ev_metrics_still_works(self, monkeypatch):
        # Backward compatibility: older callers/tests may still pass a bare 3-tuple with no
        # reason column - must not raise an IndexError.
        loader = self._loader(monkeypatch)
        ev_metrics = (100_000_000.0, 50_000_000.0, None)

        metrics = loader._compute_quality_metrics("LEGACY", _quality_row(), ev_metrics=ev_metrics)

        assert metrics["ebitda"] is None
        assert metrics["ebitda_unavailable_reason"] == "missing_sec_data"

    def test_real_ebitda_still_computes_normally(self, monkeypatch):
        loader = self._loader(monkeypatch)
        ev_metrics = (100_000_000.0, 50_000_000.0, 60_000_000.0, None)

        metrics = loader._compute_quality_metrics("NORMALCO", _quality_row(), ev_metrics=ev_metrics)

        assert metrics["ebitda"] == 60_000_000.0
        assert metrics.get("ebitda_unavailable_reason") is None
