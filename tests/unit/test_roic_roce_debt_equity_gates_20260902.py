"""Regression test: roic_pct/roce_pct_unavailable_reason must reuse the debt/equity structural
gates just wired into debt_to_equity - all three fields share the same
debt_for_roic/roic_stockholders_equity inputs, so a genuinely debt-free or no-recent-equity
filer should get the same specific reason, not the generic "missing_sec_data" fallback.

Found live 2026-09-02 (goal: "no SEC data" audit continuation): invested_capital/capital_employed
come back None whenever debt_for_roic or roic_stockholders_equity is None - the existing
negative_invested_capital/negative_capital_employed branches only catch a *computed* non-None
value <= 0, not a missing input. Live-confirmed 264/350 (75%) of roic_pct and 328/394 (83%) of
roce_pct's "missing_sec_data" rows are this exact gap.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(stockholders_equity=100_000_000.0, cash_and_equivalents=20_000_000.0, long_term_debt=None):
    # 34-column shape (index 33 = prior_year_gross_profit).
    row = [None] * 34
    row[0] = stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = 700_000_000.0  # total_assets
    row[3] = 50_000_000.0  # net_income
    row[5] = 60_000_000.0  # operating_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[20] = long_term_debt
    row[21] = cash_and_equivalents
    row[22] = 12_000_000.0  # income_tax_expense
    row[23] = 60_000_000.0  # pretax_income
    return row


class _FakeCursor:
    def __init__(self, no_recent_debt_symbols, no_recent_equity_symbols):
        self._no_recent_debt = no_recent_debt_symbols
        self._no_recent_equity = no_recent_equity_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "annual_balance_sheet" in q and "short_term_debt" in q:
            return [(s,) for s in self._no_recent_debt]
        if "annual_balance_sheet" in q and "stockholders_equity" in q and "cash_and_equivalents" not in q:
            return [(s,) for s in self._no_recent_equity]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, no_recent_debt_symbols=frozenset(), no_recent_equity_symbols=frozenset()):
        self._no_recent_debt = no_recent_debt_symbols
        self._no_recent_equity = no_recent_equity_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._no_recent_debt, self._no_recent_equity)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, no_recent_debt_symbols=frozenset(), no_recent_equity_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(
        mod,
        "DatabaseContext",
        _FakeDatabaseContext(no_recent_debt_symbols, no_recent_equity_symbols),
    )
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestRoicRoceDebtEquityGates:
    def test_no_recent_debt_gets_not_itemized_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_debt_symbols=frozenset({"DEBTFREE"}))
        row = _quality_row(long_term_debt=None)

        metrics = loader._compute_quality_metrics("DEBTFREE", row, ev_metrics=(None, None, None))

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "total_debt_not_itemized"
        assert metrics["roce_pct"] is None
        assert metrics["roce_pct_unavailable_reason"] == "total_debt_not_itemized"

    def test_no_recent_equity_gets_not_reported_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_equity_symbols=frozenset({"NOEQ"}))
        row = _quality_row(stockholders_equity=None, long_term_debt=80_000_000.0)

        metrics = loader._compute_quality_metrics("NOEQ", row, ev_metrics=(None, None, None))

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "stockholders_equity_not_reported"
        assert metrics["roce_pct"] is None
        assert metrics["roce_pct_unavailable_reason"] == "stockholders_equity_not_reported"

    def test_symbol_not_in_either_set_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(long_term_debt=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=(None, None, None))

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "missing_sec_data"
        assert metrics["roce_pct"] is None
        assert metrics["roce_pct_unavailable_reason"] == "missing_sec_data"
