"""Regression test: roic_pct's invested-capital denominator must fall back to a different
fiscal year's long_term_debt when neither sec_valuations.total_debt nor the anchor year's
own long_term_debt is available.

Unlike the tax/pretax (see test_roic_ebit_fallback.py) and stockholders_equity/
cash_and_equivalents inputs, long_term_debt_bs never got a same-year-substitute fallback
search. Live case: ABCB (Ameris Bancorp) - FY2026 anchor balance sheet has
stockholders_equity/cash_and_equivalents but no long_term_debt (banks tag deposits/FHLB
advances/subordinated debentures under concepts this pipeline doesn't map to
"long_term_debt"), and sec_valuations.total_debt is also NULL for it - roic_pct failed even
though ABCB's FY2023 10-K (still within the 3-year lookback window) reports
long_term_debt=$1.7B. total_debt_ev has no fiscal-year dimension (sec_valuations is a single
latest-snapshot row), so only long_term_debt_bs can be rescued via history search.
Live-confirmed 110 universe symbols have this exact gap.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    """Serves a canned row only to the debt fallback query (matched by its distinctive
    column list) - every other fallback query gets None, so this isolates the new code
    path from the pre-existing tax/pretax and equity/cash fallbacks."""

    def __init__(self, fallback_row=None):
        self._fallback_row = fallback_row
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        return []

    def fetchone(self):
        if "SELECT long_term_debt" in self._last_query:
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


def _quality_row(
    stockholders_equity=4_082_127_000.0,
    long_term_debt=None,
    cash_and_equivalents=237_431_000.0,
    income_tax_expense=121_610_000.0,
    pretax_income=533_764_000.0,
    operating_income=500_000_000.0,
):
    # Same 33-column layout as test_roic_ebit_fallback.py's fixture.
    return (
        stockholders_equity,  # 0 stockholders_equity
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        400_000_000.0,  # 4 revenue
        operating_income,  # 5 operating_income
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2026,  # 8 fiscal_year
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
        long_term_debt,  # 20 long_term_debt
        cash_and_equivalents,  # 21 cash_and_equivalents
        income_tax_expense,  # 22 income_tax_expense
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
    )


class TestRoicPctDebtSameYearFallback:
    def test_falls_back_to_different_fiscal_year_long_term_debt(self, monkeypatch):
        # ABCB-shaped: anchor year (FY2026) has equity/cash/tax/pretax/operating_income but
        # no long_term_debt, and sec_valuations has no total_debt (ev_metrics=None). A prior
        # fiscal year (FY2023) has long_term_debt=$1.7B.
        loader = _make_loader(monkeypatch, fallback_row=(1_700_000_000.0,))
        row = _quality_row(long_term_debt=None)

        metrics = loader._compute_quality_metrics("ABCB", row, ev_metrics=None)

        # invested_capital = 4,082,127,000 + 1,700,000,000 - 237,431,000 = 5,544,696,000
        # tax_rate = 121,610,000 / 533,764,000; NOPAT = 500,000,000 * (1 - tax_rate)
        tax_rate = 121_610_000.0 / 533_764_000.0
        nopat = 500_000_000.0 * (1 - tax_rate)
        invested_capital = 4_082_127_000.0 + 1_700_000_000.0 - 237_431_000.0
        assert metrics["roic_pct"] == (nopat / invested_capital) * 100

    def test_no_debt_in_any_year_fails_cleanly_not_a_crash(self, monkeypatch):
        loader = _make_loader(monkeypatch, fallback_row=None)
        row = _quality_row(long_term_debt=None)

        metrics = loader._compute_quality_metrics("NODEBTCO", row, ev_metrics=None)

        assert metrics["roic_pct"] is None

    def test_real_total_debt_ev_still_wins_over_debt_fallback_query(self, monkeypatch):
        """sec_valuations.total_debt is the primary source - the new fallback must only
        fire when it's also absent, not override a real EV-derived debt figure."""
        loader = _make_loader(monkeypatch, fallback_row=(1_700_000_000.0,))
        row = _quality_row(long_term_debt=None)

        metrics = loader._compute_quality_metrics("HASDEBTEV", row, ev_metrics=(900_000_000.0, None, None))

        tax_rate = 121_610_000.0 / 533_764_000.0
        nopat = 500_000_000.0 * (1 - tax_rate)
        invested_capital = 4_082_127_000.0 + 900_000_000.0 - 237_431_000.0
        assert metrics["roic_pct"] == (nopat / invested_capital) * 100
