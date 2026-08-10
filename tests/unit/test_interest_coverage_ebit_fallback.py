"""Regression test: interest_coverage must fall back to an EBIT approximation
(pretax_income + interest_expense) when OperatingIncomeLoss isn't tagged in SEC XBRL.

Live DB audit (2026-08-09) found interest_coverage stuck at 57.5% coverage (3280/5709)
even after a fresh full-universe SEC data refresh - disproving the standing theory that
the gap was just stale/missing source data. Root cause: 647 real symbols (e.g. TJX, AFL,
JCI - all with real debt, all reporting interest_expense and pretax_income every fiscal
year) never tag OperatingIncomeLoss in XBRL at all (confirmed via a comment in
sec_statements.py documenting the same finding for SWK/KMX/BXP), so
interest_coverage_operating_income stayed None despite abundant real data to compute the
ratio from. EBIT = Pretax Income + Interest Expense is the standard textbook
approximation used exactly for this case, and is added here as a second-tier fallback -
below OperatingIncomeLoss, never overriding a real operating_income value.

Also covers a second, related bug surfaced by live-verifying the above fix against real
data: a near-zero interest_expense denominator (real but rounding-error-scale, e.g. $5-
$11) produces a numerically meaningless ratio in the hundreds of thousands regardless of
whether the numerator is a real OperatingIncomeLoss value or the EBIT approximation -
live-confirmed via IKT/ENVB (real operating_income, pre-existing code path, not the
fallback this session added). Both paths are now bounded at |ratio| <= 1000.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    """Serves a canned row only to the interest_coverage fallback query (matched by its
    distinctive column list) - every other fallback query this loader may also issue
    (gross_profit, ROIC tax/equity, dividend_data, etc.) gets None, so those metrics
    just take their own already-tested 'no data' path instead of getting a mismatched
    row shape."""

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


def _quality_row(
    operating_income=None,
    interest_expense=None,
    pretax_income=None,
):
    # SELECT column order from _compute_quality_metrics's quality_row query: 31 columns,
    # fiscal_year at index 8, matching real fixtures used elsewhere in this test suite.
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
    )


class TestInterestCoverageEbitFallback:
    def test_uses_ebit_approximation_when_operating_income_missing(self, monkeypatch):
        # TJX-shaped: real interest_expense + pretax_income every year, no OperatingIncomeLoss.
        loader = _make_loader(monkeypatch)
        row = _quality_row(operating_income=None, interest_expense=79_000_000.0, pretax_income=1_721_000_000.0)

        metrics = loader._compute_quality_metrics("TJX", row, ev_metrics=None)

        expected = (1_721_000_000.0 + 79_000_000.0) / 79_000_000.0
        assert metrics["interest_coverage"] == expected

    def test_real_operating_income_still_wins_over_ebit_fallback(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            operating_income=60_000_000.0, interest_expense=10_000_000.0, pretax_income=1_000_000_000.0
        )

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["interest_coverage"] == 6.0  # 60M / 10M, not the pretax-based value

    def test_no_pretax_income_still_fails_cleanly(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(operating_income=None, interest_expense=10_000_000.0, pretax_income=None)

        metrics = loader._compute_quality_metrics("NODATACO", row, ev_metrics=None)

        assert metrics["interest_coverage"] is None

    def test_fallback_year_ebit_approximation_via_db_lookup(self, monkeypatch):
        # Anchor year has no usable interest_expense at all; the fallback-year DB query
        # must also apply the EBIT approximation, not just the anchor-year path.
        fallback_row = (79_000_000.0, None, 1_721_000_000.0)  # interest_expense, operating_income, pretax_income
        loader = _make_loader(monkeypatch, fallback_row=fallback_row)
        row = _quality_row(operating_income=None, interest_expense=None, pretax_income=None)

        metrics = loader._compute_quality_metrics("TJX", row, ev_metrics=None)

        expected = (1_721_000_000.0 + 79_000_000.0) / 79_000_000.0
        assert metrics["interest_coverage"] == expected

    def test_negligible_interest_expense_denominator_marked_unavailable_via_ebit_path(self, monkeypatch):
        # Live DB audit (2026-08-09) found 162 real symbols where a near-zero reported
        # interest charge against a large loss produced ratios in the hundreds of
        # thousands (worst case: -3,625,721x) - not a meaningful signal, just noise from
        # dividing by a near-zero denominator. Must be marked unavailable, not stored as
        # a nonsensical extreme value.
        loader = _make_loader(monkeypatch)
        row = _quality_row(operating_income=None, interest_expense=10.0, pretax_income=-36_000_000.0)

        metrics = loader._compute_quality_metrics("DISTRESSEDCO", row, ev_metrics=None)

        assert metrics["interest_coverage"] is None

    def test_negligible_interest_expense_denominator_marked_unavailable_via_real_operating_income(
        self, monkeypatch
    ):
        # The same near-zero-denominator failure mode hits a real, already-shipped
        # OperatingIncomeLoss-based ratio just as badly - live-confirmed via IKT/ENVB
        # (real, if hugely negative, operating_income against a real $5-$11 interest
        # expense). The bound must not be scoped to only the EBIT approximation path.
        loader = _make_loader(monkeypatch)
        row = _quality_row(operating_income=-17_841_919.0, interest_expense=5.0, pretax_income=None)

        metrics = loader._compute_quality_metrics("IKT", row, ev_metrics=None)

        assert metrics["interest_coverage"] is None

    def test_real_operating_income_based_ratio_within_bound_still_computes(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(operating_income=60_000_000.0, interest_expense=10_000_000.0, pretax_income=None)

        metrics = loader._compute_quality_metrics("NORMALCO2", row, ev_metrics=None)

        assert metrics["interest_coverage"] == 6.0
