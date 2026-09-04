"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, WELL follow-up): the interest_coverage fallback-year search only ever triggered when
interest_expense ITSELF was missing/invalid - but a filer can have a perfectly real, valid
current-year interest_expense while ONLY operating_income/pretax_income are missing for that
specific anchor year, and this case skipped the fallback search entirely.

Live-confirmed via WELL (Welltower): FY2025 has real interest_expense=$579.6M and
income_tax_expense=$-7.1M, but pretax_income is NULL that one year despite being real and
populated FY2021-2024 ($524,442,000 FY2024). Same "anchor-year-specific extraction gap, real
data one year back" class already fixed for other fields via the no-recent-X gates.

Also verifies the fix does NOT overwrite a real, valid current-year interest_expense with a
stale fallback-year value when interest_expense wasn't the reason the fallback fired - doing
so would mix a current-year denominator with a stale numerator/year.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    def __init__(self, fallback_row=None):
        self._fallback_row = fallback_row
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        return []

    def fetchone(self):
        if "SELECT interest_expense, operating_income, pretax_income" in self._last_query:
            return self._fallback_row
        return None


class _FakeDatabaseContext:
    def __init__(self, cursor):
        self._cur = cursor

    def __enter__(self):
        return self._cur

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, fallback_row=None):
    import loaders.load_value_quality_growth_metrics as mod

    cursor = _FakeCursor(fallback_row)
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(cursor))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(operating_income=None, interest_expense=None, pretax_income=None):
    return (
        500_000_000.0,  # 0 stockholders_equity
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        400_000_000.0,  # 4 revenue
        operating_income,  # 5 operating_income
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        interest_expense,  # 10 interest_expense
        None,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        None,  # 19 gross_profit
        None,  # 20 long_term_debt
        None,  # 21 cash_and_equivalents
        None,  # 22 income_tax_expense
        pretax_income,  # 23 pretax_income
        None,  # 24 prior_year_net_income
        None,  # 25 prior_year_operating_income
        None,  # 26 prior_year_operating_cash_flow
        None,  # 27 prior_year_free_cash_flow
        None,  # 28 prior_year_cost_of_revenue
        None,  # 29 prior_year_total_assets
        None,  # 30 prior_year_stockholders_equity
        None,  # 31 prior_year_pretax_income
        None,  # 32 prior_year_interest_expense
        None,  # 33 prior_year_gross_profit
    )


class TestInterestCoverageIncomeInputsMissingFallback:
    def test_well_style_anchor_year_gap_recovered_without_touching_real_interest_expense(self, monkeypatch):
        # WELL-shaped: FY2025 has a real, valid current-year interest_expense but NULL
        # operating_income/pretax_income; FY2024's real pretax_income is what the fallback
        # search should find.
        fallback_row = (593_030_000.0, None, 524_442_000.0)  # FY2024: interest_expense, operating_income, pretax_income
        loader = _make_loader(monkeypatch, fallback_row=fallback_row)
        row = _quality_row(operating_income=None, interest_expense=579_589_000.0, pretax_income=None)

        metrics = loader._compute_quality_metrics("WELL", row, ev_metrics=None)

        # Must use the CURRENT year's real interest_expense (579,589,000), not the fallback
        # row's (593,030,000) - interest_expense itself was never the problem here.
        expected = (524_442_000.0 + 579_589_000.0) / 579_589_000.0
        assert metrics["interest_coverage"] == expected

    def test_both_inputs_present_never_triggers_fallback_search(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(operating_income=60_000_000.0, interest_expense=10_000_000.0, pretax_income=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["interest_coverage"] == 6.0

    def test_no_fallback_row_available_still_fails_cleanly(self, monkeypatch):
        loader = _make_loader(monkeypatch, fallback_row=None)
        row = _quality_row(operating_income=None, interest_expense=579_589_000.0, pretax_income=None)

        metrics = loader._compute_quality_metrics("NODATACO", row, ev_metrics=None)

        assert metrics["interest_coverage"] is None
