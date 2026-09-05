"""Regression test (2026-09-05, "SEC/XBRL missing data to zero" goal session): roic_pct and
roce_pct's |ratio| > 1000 implausible-value bound had no cross-year fallback, unlike
roe/roa/asset_turnover (see `_find_plausible_cross_year_ratio`'s docstring) - an anchor year
with a near-zero/negative invested_capital or capital_employed (extraction artifact, not a
real business characteristic) threw the symbol straight to implausible_ratio even when an
older fiscal year has a fully coherent (operating_income, tax, pretax, equity, cash, debt)
same-year pair. See memory `roic_pct_implausible_ratio_no_cross_year_fallback_scoped_20260904`
for the prior session's scoping of this gap (176 roic_pct + 4 roce_pct rows, not implemented
that session).
"""

import pytest

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    def __init__(self, fallback_rows):
        self._fallback_rows = fallback_rows
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        # Other DB calls made during _compute_quality_metrics (symbol-gate lookups, the
        # ROE/ROA cross-year helper, etc.) share this same fake DatabaseContext - only the
        # roic/roce cross-year fallback's own query should see the crafted fallback row.
        if "ais.operating_income" in self._last_query:
            return self._fallback_rows
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, fallback_rows):
        self._fallback_rows = fallback_rows

    def __enter__(self):
        return _FakeCursor(self._fallback_rows)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, fallback_rows):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(fallback_rows))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(
    stockholders_equity=None,
    long_term_debt=None,
    cash_and_equivalents=None,
    operating_income=None,
    income_tax_expense=None,
    pretax_income=None,
):
    # Same 33-column shape as test_quality_metrics_implausible_ratio_reason.py's fixture.
    return (
        stockholders_equity,  # 0
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        None,  # 4 revenue
        operating_income,  # 5
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        None,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        None,  # 19 gross_profit
        long_term_debt,  # 20
        cash_and_equivalents,  # 21
        income_tax_expense,  # 22
        pretax_income,  # 23
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


# Anchor year: invested_capital = -999M + 1000M - 0.5M = 0.5M, nopat = 10M*(1-0.2) = 8M,
# ratio = 8M/0.5M*100 = 1,600,000% - past the |ratio|>1000 bound (same anchor as
# test_quality_metrics_implausible_ratio_reason.py's MCK case).
_ANCHOR_ROW_KWARGS = {
    "stockholders_equity": -999_000_000.0,
    "long_term_debt": 1_000_000_000.0,
    "cash_and_equivalents": 500_000.0,
    "operating_income": 10_000_000.0,
    "income_tax_expense": 2_000_000.0,
    "pretax_income": 10_000_000.0,
}

# Older fiscal year, fully coherent same-year pair: invested_capital = 50M+5M-1M = 54M,
# nopat = 10M*(1-0.2) = 8M, ratio = 8M/54M*100 = 14.8% - plausible.
_PLAUSIBLE_FALLBACK_ROW = (10_000_000.0, 2_000_000.0, 10_000_000.0, 50_000_000.0, 1_000_000.0, 5_000_000.0)

# capital_employed = 50M+5M = 55M, ratio (EBIT/capital_employed) = 10M/55M*100 = 18.2% - plausible.

# Separate anchor for roce_pct: capital_employed = -999.5M + 1000M = 0.5M,
# ratio = 10M/0.5M*100 = 2,000,000% - clearly past the |ratio|>1000 bound (the roic_pct
# anchor above computes an anchor capital_employed of exactly 1000%, the boundary, which
# doesn't trip the bound - roce_pct needs its own more extreme anchor to exercise it).
_ROCE_ANCHOR_ROW_KWARGS = {
    "stockholders_equity": -999_500_000.0,
    "long_term_debt": 1_000_000_000.0,
    "cash_and_equivalents": 100_000.0,
    "operating_income": 10_000_000.0,
    "income_tax_expense": 2_000_000.0,
    "pretax_income": 10_000_000.0,
}


class TestRoicRoceCrossYearFallback:
    def test_roic_pct_uses_plausible_cross_year_fallback(self, monkeypatch):
        loader = _make_loader(monkeypatch, [_PLAUSIBLE_FALLBACK_ROW])
        row = _quality_row(**_ANCHOR_ROW_KWARGS)

        metrics = loader._compute_quality_metrics("MCK", row, ev_metrics=None)

        assert metrics["roic_pct"] == pytest.approx(14.814814814814813)
        assert metrics.get("roic_pct_unavailable_reason") is None

    def test_roic_pct_falls_through_to_implausible_when_no_fallback_row_qualifies(self, monkeypatch):
        loader = _make_loader(monkeypatch, [])
        row = _quality_row(**_ANCHOR_ROW_KWARGS)

        metrics = loader._compute_quality_metrics("MCK", row, ev_metrics=None)

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "implausible_ratio"

    def test_roce_pct_uses_plausible_cross_year_fallback(self, monkeypatch):
        loader = _make_loader(monkeypatch, [_PLAUSIBLE_FALLBACK_ROW])
        row = _quality_row(**_ROCE_ANCHOR_ROW_KWARGS)

        metrics = loader._compute_quality_metrics("MCK", row, ev_metrics=None)

        assert metrics["roce_pct"] == pytest.approx(18.181818181818183)
        assert metrics.get("roce_pct_unavailable_reason") is None
