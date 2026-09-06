"""Regression test (2026-09-03, "Missing SEC/XBRL data" reduction goal session):
denominator-gate-left-behind bug class - same shape as `10f8edb1a`'s accruals_ratio/total_assets
fix. Three fields' reason chains only ever checked their NUMERATOR's structural gates, never the
DENOMINATOR they also divide by, even though the denominator's own gate functions already exist
and are used by sibling fields:

- operating_profitability = (OperatingIncome - Interest) / StockholdersEquity: only checked
  operating_income's gates plus a negative-equity check; never checked whether stockholders_equity
  was genuinely never tagged / no-recent (as opposed to a real value <= 0). Live-confirmed 19 of
  108 universe operating_profitability "missing_sec_data" rows (e.g. NRP, GLDM, AAAU, PAC, HESM,
  BK) have stockholders_equity in the no_recent/never_tagged gate sets.
- fcf_to_net_income = free_cash_flow / net_income: only checked free_cash_flow's gates. Live-
  confirmed 19 of 176 universe rows (e.g. ESOA, AVLN, ELMT, PARK, OFRM) have net_income in the
  no_recent/never_tagged gate sets.
- ocf_to_net_income = operating_cash_flow / net_income: same shape, same 19 symbols (shares the
  denominator with fcf_to_net_income).
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(
    stockholders_equity=100_000_000.0,
    net_income=50_000_000.0,
    total_assets=700_000_000.0,
    total_liabilities=200_000_000.0,
    revenue=None,
    operating_income=None,
    interest_expense=None,
    operating_cash_flow=None,
    free_cash_flow=None,
):
    row = [None] * 34
    row[0] = stockholders_equity
    row[1] = total_liabilities
    row[2] = total_assets
    row[3] = net_income
    row[4] = revenue
    row[5] = operating_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[10] = interest_expense
    row[13] = operating_cash_flow
    row[14] = free_cash_flow
    return row


class _FakeCursor:
    """Windowed gates (ROW_NUMBER()) always return empty - only the never-tagged full-history
    siblings (plain GROUP BY, no ROW_NUMBER()) can fire in this test."""

    def __init__(self, never_tagged_equity, never_tagged_net_income):
        self._never_tagged_equity = never_tagged_equity
        self._never_tagged_net_income = never_tagged_net_income
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "ROW_NUMBER()" in q:
            return []
        if "annual_income_statement" in q and "net_income" in q:
            return [(s,) for s in self._never_tagged_net_income]
        # "etf_symbols" excluded 2026-09-05 (real-money-readiness audit): a newer sibling gate
        # (_get_etf_trust_no_stockholders_equity_symbols, vqg_symbol_gates.py) also queries
        # annual_balance_sheet+stockholders_equity (joined against etf_symbols) and was
        # otherwise indistinguishable from this fixture's own never-tagged-equity query.
        if (
            "annual_balance_sheet" in q
            and "stockholders_equity" in q
            and "cash_and_equivalents" not in q
            and "etf_symbols" not in q
        ):
            return [(s,) for s in self._never_tagged_equity]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, never_tagged_equity=frozenset(), never_tagged_net_income=frozenset()):
        self._never_tagged_equity = never_tagged_equity
        self._never_tagged_net_income = never_tagged_net_income

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._never_tagged_equity, self._never_tagged_net_income)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, **kwargs):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(**kwargs))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestOperatingProfitabilityNeverTaggedEquity:
    def test_never_tagged_equity_gets_stockholders_equity_not_reported(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_equity=frozenset({"RECENTIPO"}))
        row = _quality_row(stockholders_equity=None, operating_income=50_000_000.0, interest_expense=5_000_000.0)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["operating_profitability"] is None
        assert metrics["operating_profitability_unavailable_reason"] == "stockholders_equity_not_reported"

    def test_negative_equity_still_wins_over_never_tagged_check(self, monkeypatch):
        # A real negative-equity value must still take priority - the new gate only fires when
        # stockholders_equity is None, never on a real value.
        loader = _make_loader(monkeypatch, never_tagged_equity=frozenset({"NEGEQ"}))
        row = _quality_row(stockholders_equity=-1.0, operating_income=50_000_000.0, interest_expense=5_000_000.0)

        metrics = loader._compute_quality_metrics("NEGEQ", row, ev_metrics=None)

        assert metrics["operating_profitability_unavailable_reason"] == "negative_book_value"


class TestFcfOcfToNetIncomeNeverTaggedNetIncome:
    def test_fcf_to_net_income_never_tagged_net_income(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_net_income=frozenset({"RECENTIPO"}))
        row = _quality_row(net_income=None, free_cash_flow=10_000_000.0)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["fcf_to_net_income"] is None
        assert metrics["fcf_to_net_income_unavailable_reason"] == "net_income_not_reported"

    def test_ocf_to_net_income_never_tagged_net_income(self, monkeypatch):
        loader = _make_loader(monkeypatch, never_tagged_net_income=frozenset({"RECENTIPO"}))
        row = _quality_row(net_income=None, operating_cash_flow=10_000_000.0)

        metrics = loader._compute_quality_metrics("RECENTIPO", row, ev_metrics=None)

        assert metrics["ocf_to_net_income"] is None
        assert metrics["ocf_to_net_income_unavailable_reason"] == "net_income_not_reported"

    def test_numerator_gate_still_checked_first_when_both_are_none(self, monkeypatch):
        # When BOTH free_cash_flow and net_income are None and the symbol is in BOTH gate sets,
        # the numerator's own gate (checked first, unchanged ordering) must still win - this fix
        # only extends the chain, it doesn't reorder the existing numerator checks.
        import loaders.load_value_quality_growth_metrics as mod

        loader = _make_loader(monkeypatch, never_tagged_net_income=frozenset({"BOTHMISSING"}))
        monkeypatch.setattr(loader, "_get_no_recent_free_cash_flow_symbols", lambda: frozenset({"BOTHMISSING"}))
        monkeypatch.setattr(loader, "_get_free_cash_flow_available_elsewhere_symbols", lambda: frozenset())
        row = _quality_row(net_income=None, free_cash_flow=None)

        metrics = loader._compute_quality_metrics("BOTHMISSING", row, ev_metrics=None)

        assert metrics["fcf_to_net_income_unavailable_reason"] == "no_recent_free_cash_flow_reported"

    def test_symbols_not_in_gate_keep_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(net_income=None, free_cash_flow=10_000_000.0, operating_cash_flow=10_000_000.0)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["fcf_to_net_income_unavailable_reason"] == "missing_sec_data"
        assert metrics["ocf_to_net_income_unavailable_reason"] == "missing_sec_data"
