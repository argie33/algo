"""Regression test: roic_operating_income (feeds roce_pct/roic_pct, the EBIT-approximation
fallback = pretax_income + interest_expense) must compute a real value for a symbol
double-confirmed structurally debt-free, instead of falling to the generic
"operating_income_not_itemized" reason.

Found 2026-09-10 (goal: "Missing SEC/XBRL data" under-500 sweep, operating_income_not_itemized
investigation). Live-confirmed via EDHL and NEWP: both are in
_get_never_tagged_debt_components_symbols() AND _get_never_tagged_interest_expense_symbols()
(the same double-confirmed-debt-free gate debt_for_roic/total_debt already trust for a real
$0, see test_debt_for_roic_confirmed_debt_free_zero_fallback_20260904.py), have a real, current
pretax_income on file, but never tagged operating_income OR interest_expense in any fiscal
year - so roic_operating_income stayed None (no operating_income, and the EBIT-approximation
fallback requires interest_expense to be non-None too, which it never was) even though the
correct answer (EBIT = pretax_income + $0 real interest) was fully derivable. This test locks
in the fix: roic_interest_expense gets the same 0.0 coercion debt_for_roic already receives,
gated on the identical double-confirmed signal.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(
    pretax_income=5_000_000.0, income_tax_expense=1_000_000.0, operating_income=None, interest_expense=None
):
    # 34-column shape (index 33 = prior_year_gross_profit), matching
    # test_debt_for_roic_confirmed_debt_free_zero_fallback_20260904.py's fixture.
    row = [None] * 34
    row[0] = 50_000_000.0  # stockholders_equity
    row[1] = 5_000_000.0  # total_liabilities
    row[2] = 55_000_000.0  # total_assets
    row[3] = 4_000_000.0  # net_income
    row[4] = 30_000_000.0  # revenue
    row[5] = operating_income
    row[6] = 15_000_000.0  # current_assets
    row[7] = 5_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[10] = interest_expense
    row[20] = None  # long_term_debt
    row[21] = 10_000_000.0  # cash_and_equivalents
    row[22] = income_tax_expense
    row[23] = pretax_income
    return row


class _FakeCursor:
    def __init__(self, never_tagged_debt_symbols, never_tagged_interest_symbols):
        self._never_tagged_debt = never_tagged_debt_symbols
        self._never_tagged_interest = never_tagged_interest_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        q = self._last_query
        if "annual_income_statement" in q and "interest_expense" in q:
            return [(s,) for s in self._never_tagged_interest]
        if "annual_balance_sheet" in q and "short_term_debt" in q and "ROW_NUMBER" not in q:
            return [(s,) for s in self._never_tagged_debt]
        return []

    def fetchone(self):
        # The tax/pretax fallback-year search: nothing better on file than the anchor row
        # itself (operating_income/interest_expense never tagged in ANY fiscal year).
        return None


class _FakeDatabaseContext:
    def __init__(self, never_tagged_debt_symbols=frozenset(), never_tagged_interest_symbols=frozenset()):
        self._never_tagged_debt = never_tagged_debt_symbols
        self._never_tagged_interest = never_tagged_interest_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._never_tagged_debt, self._never_tagged_interest)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, never_tagged_debt_symbols=frozenset(), never_tagged_interest_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(
        mod,
        "DatabaseContext",
        _FakeDatabaseContext(never_tagged_debt_symbols, never_tagged_interest_symbols),
    )
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestRoicOperatingIncomeConfirmedDebtFreeInterestZero:
    def test_double_confirmed_debt_free_computes_operating_income_from_pretax_alone(self, monkeypatch):
        loader = _make_loader(
            monkeypatch,
            never_tagged_debt_symbols=frozenset({"DEBTFREE"}),
            never_tagged_interest_symbols=frozenset({"DEBTFREE"}),
        )
        row = _quality_row(pretax_income=5_000_000.0, income_tax_expense=1_000_000.0)

        metrics = loader._compute_quality_metrics("DEBTFREE", row, ev_metrics=(None, None, None))

        # EBIT = pretax_income + $0 real interest expense.
        assert metrics.get("roce_pct_unavailable_reason") is None
        assert metrics["roce_pct"] is not None

    def test_debt_never_tagged_but_interest_expense_reported_stays_unavailable(self, monkeypatch):
        # Debt components never itemized, but real interest expense IS on file somewhere -
        # contradicts "genuinely no debt/interest" - must NOT coerce interest_expense to zero.
        loader = _make_loader(
            monkeypatch,
            never_tagged_debt_symbols=frozenset({"HASINTEREST"}),
            never_tagged_interest_symbols=frozenset(),
        )
        row = _quality_row(pretax_income=5_000_000.0, income_tax_expense=1_000_000.0)

        metrics = loader._compute_quality_metrics("HASINTEREST", row, ev_metrics=(None, None, None))

        # debt_for_roic also stays unresolved for this symbol (not double-confirmed
        # debt-free), so capital_employed itself is None - a different failure reason than
        # operating_income_not_itemized, but still correctly unavailable, not a fabricated 0.
        assert metrics["roce_pct"] is None
        assert metrics.get("roce_pct_unavailable_reason") is not None

    def test_real_operating_income_untouched(self, monkeypatch):
        loader = _make_loader(
            monkeypatch,
            never_tagged_debt_symbols=frozenset({"DEBTFREE"}),
            never_tagged_interest_symbols=frozenset({"DEBTFREE"}),
        )
        row = _quality_row(pretax_income=5_000_000.0, income_tax_expense=1_000_000.0, operating_income=6_000_000.0)

        metrics = loader._compute_quality_metrics("DEBTFREE", row, ev_metrics=(None, None, None))

        assert metrics.get("roce_pct_unavailable_reason") is None
        assert metrics["roce_pct"] is not None
