"""Regression test (2026-09-13, live-caught via ScoreRatioOutlierChecker's roic_pct batch:
DCBO/IBKR/NTNX/MANH/INDV all flagged 396-879%, none excluded by the existing
`invested_capital < 0.01 * abs(nopat)` floor from test_roic_roce_immaterial_capital_base_floor_
20260908.py): that floor only catches an immaterial invested_capital relative to NOPAT, not the
DCBO shape - a large, real balance sheet (equity ~$74M, funded almost entirely by cash) where
equity+debt-minus-cash nets down to a near-zero invested_capital (~$54K) that is still >1% of a
proportionally small nopat, so the ratio (~889%) slips through under the |ratio|>1000 ceiling too.
Fix: a second floor compares invested_capital to the GROSS pre-cash-netting base (equity + debt)
directly - same treatment as the existing floor (falls through to cross-year fallback, else
"implausible_ratio").
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


def _make_loader(monkeypatch, fallback_rows=()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(list(fallback_rows)))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(
    stockholders_equity=None,
    long_term_debt=None,
    cash_and_equivalents=None,
    operating_income=None,
    income_tax_expense=None,
    pretax_income=None,
):
    # Same 33-column shape as test_roic_roce_immaterial_capital_base_floor_20260908.py's fixture.
    return (
        stockholders_equity,  # 0
        200_000_000.0,  # 1 total_liabilities
        1_240_852_000.0,  # 2 total_assets
        13_836_000.0,  # 3 net_income
        None,  # 4 revenue
        operating_income,  # 5
        150_000_000.0,  # 6 current_assets
        102_566_000.0,  # 7 current_liabilities
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


# DCBO-shaped (live-confirmed 2026-09-13): stockholders_equity=$74,091,000, cash=$74,037,000,
# no debt -> invested_capital=$54,000. operating_income=$600,000/pretax=$600,000/tax=$120,000
# (20% effective rate) -> nopat=$480,000, computed_roic_pct=888.9% (~= DCBO's live 879.33%).
# invested_capital ($54,000) is NOT under 1% of nopat ($4,800) - the existing floor misses it -
# but IS under 1% of the gross capital base ($740,910) - the new floor catches it.
_ROIC_GROSS_BASE_ANCHOR = {
    "stockholders_equity": 74_091_000.0,
    "long_term_debt": 0.0,
    "cash_and_equivalents": 74_037_000.0,
    "operating_income": 600_000.0,
    "income_tax_expense": 120_000.0,
    "pretax_income": 600_000.0,
}

# Older fiscal year, fully coherent same-year pair (same shape as the cross-year fallback test).
_PLAUSIBLE_FALLBACK_ROW = (10_000_000.0, 2_000_000.0, 10_000_000.0, 50_000_000.0, 1_000_000.0, 5_000_000.0)


class TestRoicGrossCapitalBaseFloor:
    def test_roic_pct_immaterial_vs_gross_base_excluded_no_fallback(self, monkeypatch):
        loader = _make_loader(monkeypatch, [])
        row = _quality_row(**_ROIC_GROSS_BASE_ANCHOR)

        metrics = loader._compute_quality_metrics("DCBOLIKE", row, ev_metrics=None)

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "implausible_ratio"

    def test_roic_pct_immaterial_vs_gross_base_uses_cross_year_fallback(self, monkeypatch):
        loader = _make_loader(monkeypatch, [_PLAUSIBLE_FALLBACK_ROW])
        row = _quality_row(**_ROIC_GROSS_BASE_ANCHOR)

        metrics = loader._compute_quality_metrics("DCBOLIKE", row, ev_metrics=None)

        assert metrics["roic_pct"] == pytest.approx(14.814814814814813)
        assert metrics.get("roic_pct_unavailable_reason") is None

    def test_normal_capital_base_still_unaffected(self, monkeypatch):
        loader = _make_loader(monkeypatch, [])
        row = _quality_row(
            stockholders_equity=50_000_000.0,
            long_term_debt=5_000_000.0,
            cash_and_equivalents=1_000_000.0,
            operating_income=10_000_000.0,
            income_tax_expense=2_000_000.0,
            pretax_income=10_000_000.0,
        )

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["roic_pct"] == pytest.approx(14.814814814814813)
