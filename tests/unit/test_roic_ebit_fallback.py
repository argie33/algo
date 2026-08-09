"""Regression test: roic_pct's NOPAT numerator must fall back to an EBIT approximation
(pretax_income + interest_expense) when OperatingIncomeLoss isn't tagged in SEC XBRL.

Same root cause as [[interest_coverage's EBIT fallback]] (see
test_interest_coverage_ebit_fallback.py): live audit (2026-08-09) found roic_pct stuck
at 23.5% coverage even after fresh SEC data landed, and traced it to the same class of
real filers (e.g. AFL) that never tag OperatingIncomeLoss at all. This fallback had an
extra wrinkle beyond interest_coverage's: it only ever searched for a rescue row when
income_tax_expense or pretax_income were THEMSELVES missing at the anchor year - for
filers where the anchor year already has both (true for AFL every year), the fallback
never even ran, so roic_operating_income stayed None with no rescue attempted at all.
Live-confirmed 572 real symbols missing roic_pct have a self-consistent
tax/pretax/interest_expense row (anchor or fallback) that only lacks OperatingIncomeLoss.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    """Serves a canned row only to the ROIC tax/pretax fallback query (matched by its
    distinctive column list) - every other fallback query gets None."""

    def __init__(self, fallback_row=None):
        self._fallback_row = fallback_row
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        return []

    def fetchone(self):
        if "SELECT income_tax_expense, pretax_income, operating_income, interest_expense" in self._last_query:
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
    operating_income=None,
    interest_expense=None,
    pretax_income=None,
    income_tax_expense=None,
    stockholders_equity=500_000_000.0,
    long_term_debt=300_000_000.0,
    cash_and_equivalents=50_000_000.0,
):
    # SELECT column order from _compute_quality_metrics's quality_row query: 31 columns,
    # fiscal_year at index 8, matching real fixtures used elsewhere in this test suite.
    return (
        stockholders_equity,  # 0 stockholders_equity
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
    )


class TestRoicEbitFallback:
    def test_uses_ebit_approximation_when_operating_income_missing_at_anchor(self, monkeypatch):
        # AFL-shaped: anchor year already has real tax/pretax/interest_expense together,
        # so the old code never even tried a fallback - operating_income just stayed None.
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            operating_income=None,
            interest_expense=50_000_000.0,
            pretax_income=800_000_000.0,
            income_tax_expense=200_000_000.0,
        )

        metrics = loader._compute_quality_metrics("AFL", row, ev_metrics=None)

        # invested_capital = 500M + 300M - 50M = 750M; EBIT = 800M + 50M = 850M;
        # tax_rate = 200M/800M = 0.25; NOPAT = 850M * 0.75 = 637.5M
        assert metrics["roic_pct"] == (637_500_000.0 / 750_000_000.0) * 100

    def test_real_operating_income_still_wins_over_ebit_fallback(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            operating_income=100_000_000.0,
            interest_expense=50_000_000.0,
            pretax_income=800_000_000.0,
            income_tax_expense=200_000_000.0,
        )

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        # NOPAT = 100M * 0.75 = 75M; roic = 75M / 750M * 100 = 10.0
        assert metrics["roic_pct"] == 10.0

    def test_no_interest_expense_still_fails_cleanly(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            operating_income=None,
            interest_expense=None,
            pretax_income=800_000_000.0,
            income_tax_expense=200_000_000.0,
        )

        metrics = loader._compute_quality_metrics("NODATACO", row, ev_metrics=None)

        assert metrics["roic_pct"] is None

    def test_fallback_year_ebit_approximation_via_db_lookup(self, monkeypatch):
        # Anchor year lacks tax/pretax entirely; the fallback-year DB query must also
        # apply the EBIT approximation when that year lacks operating_income too.
        fallback_row = (200_000_000.0, 800_000_000.0, None, 50_000_000.0)
        loader = _make_loader(monkeypatch, fallback_row=fallback_row)
        row = _quality_row(
            operating_income=None, interest_expense=None, pretax_income=None, income_tax_expense=None
        )

        metrics = loader._compute_quality_metrics("AFL", row, ev_metrics=None)

        assert metrics["roic_pct"] == (637_500_000.0 / 750_000_000.0) * 100
