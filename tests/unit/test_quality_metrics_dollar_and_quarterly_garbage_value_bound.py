"""Regression test for two more instances of the near-zero-denominator garbage-value class
already fixed for margins/ROIC/trend fields (see test_quality_metrics_ratio_garbage_value_bound.py
and MAX_TREND_PERCENTAGE_POINTS's docstring) - found live during the 2026-08-09 metrics
pipeline re-run triggered to backfill the sales_revenue_net IFRS fix.

1. quarterly_growth_momentum/earnings_growth_4q_avg/eps_growth_stability had NO bound at all
   (every sibling growth/trend field in this file already had one) - live-confirmed via DUO and
   NIQ, both hitting `NumericValueOutOfRange: ... precision 10, scale 4` on the quality_metrics
   INSERT, aborting the entire 3-table write for those symbols, not just the one garbage field.

2. free_cash_flow/operating_cash_flow/total_debt/total_cash/ebitda (absolute dollar amounts,
   NUMERIC(15,2) columns) had no sanity bound at all - live-confirmed via VFS and KEP (both
   foreign filers), hitting `NumericValueOutOfRange: ... precision 15, scale 2` (max abs value
   < 10^13, i.e. $10 trillion) on the same INSERT, same whole-row-lost failure mode. Root cause
   of why these two symbols' figures are that large (likely a missing local-currency-to-USD
   conversion, same class of bug as sec_statements.py's other foreign-filer fixes) is not fixed
   here - this bound only prevents the crash-and-lose-everything symptom.
"""

import pytest

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    def __init__(self, rows=None):
        self._rows = rows or []

    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, rows=None):
        self._rows = rows

    def __enter__(self):
        return _FakeCursor(self._rows)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, quarterly_rows=None):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(quarterly_rows))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(
    operating_cash_flow=None,
    free_cash_flow=None,
):
    # Same 31-column shape as test_quality_metrics_ratio_garbage_value_bound.py's fixture.
    return (
        500_000_000.0,  # 0 stockholders_equity
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        200_000_000.0,  # 4 revenue
        30_000_000.0,  # 5 operating_income
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        None,  # 11 shares_outstanding
        120_000_000.0,  # 12 cost_of_revenue
        operating_cash_flow,  # 13
        free_cash_flow,  # 14
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        80_000_000.0,  # 19 gross_profit
        None,  # 20 long_term_debt
        None,  # 21 cash_and_equivalents
        None,  # 22 income_tax_expense
        None,  # 23 pretax_income
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


class TestAbsoluteDollarValueGarbageBound:
    def test_implausible_operating_cash_flow_marked_unavailable(self, monkeypatch):
        # VFS/KEP-shaped: a foreign-filer figure orders of magnitude past any real company,
        # would overflow the NUMERIC(15,2) column (max abs < $10 trillion).
        loader = _make_loader(monkeypatch)
        row = _quality_row(operating_cash_flow=50_000_000_000_000.0)

        metrics = loader._compute_quality_metrics("VFS", row, ev_metrics=None)

        assert metrics["operating_cash_flow"] is None

    def test_implausible_ebitda_marked_unavailable(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row()
        # ev_metrics = (total_debt, total_cash, ebitda)
        ev_metrics = (None, None, 50_000_000_000_000.0)

        metrics = loader._compute_quality_metrics("KEP", row, ev_metrics=ev_metrics)

        assert metrics["ebitda"] is None

    def test_normal_dollar_values_still_compute(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(operating_cash_flow=100_000_000.0, free_cash_flow=80_000_000.0)
        ev_metrics = (300_000_000.0, 150_000_000.0, 120_000_000.0)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=ev_metrics)

        assert metrics["operating_cash_flow"] == 100_000_000.0
        assert metrics["free_cash_flow"] == 80_000_000.0
        assert metrics["total_debt"] == 300_000_000.0
        assert metrics["total_cash"] == 150_000_000.0
        assert metrics["ebitda"] == 120_000_000.0


class TestQuarterlyGrowthMomentumGarbageBound:
    def _quarters(
        self,
        revenues,
        net_incomes=None,
        epss=None,
        prior_revenues=None,
        prior_net_incomes=None,
        prior_epss=None,
    ):
        """Builds 8 quarters (2 fiscal years) so each of the last 4 quarters has a
        same-quarter-prior-year match (loader compares YoY, not sequential QoQ - see the
        2026-08-28 fix in loaders/load_value_quality_growth_metrics.py). `revenues`/
        `net_incomes`/`epss` are the 4 most-recent (2025) quarters; `prior_*` are their
        2024 year-ago counterparts (default: same values, i.e. 0% YoY growth) unless a
        test overrides one to exercise a specific comparison.
        """
        net_incomes = net_incomes or [1_000_000.0] * len(revenues)
        epss = epss or [0.5] * len(revenues)
        prior_revenues = prior_revenues or list(revenues)
        prior_net_incomes = prior_net_incomes or list(net_incomes)
        prior_epss = prior_epss or list(epss)
        current = [(2025, 4 - i, net_incomes[i], revenues[i], epss[i]) for i in range(len(revenues))]
        prior = [
            (2024, 4 - i, prior_net_incomes[i], prior_revenues[i], prior_epss[i]) for i in range(len(prior_revenues))
        ]
        return current + prior

    def test_near_zero_prior_quarter_revenue_excluded_not_diluting_average(self, monkeypatch):
        # FIXED 2026-09-03: same "bound each quarter before averaging" fix as
        # eps_growth_rates above, applied to the revenue side - a near-zero (but nonzero)
        # same-quarter-prior-year revenue used to make one quarter's ratio mathematically
        # enormous and get diluted, un-excluded, into the 4-quarter average. Now that
        # quarter is excluded before averaging, leaving the 3 genuinely-0%-growth quarters.
        rows = self._quarters(
            [100_000_000.0, 100_000_000.0, 100_000_000.0, 100_000_000.0],
            prior_revenues=[100_000_000.0, 0.01, 100_000_000.0, 100_000_000.0],
        )
        loader = _make_loader(monkeypatch, quarterly_rows=rows)

        metrics = loader._compute_quarterly_metrics("DUO")

        assert metrics.get("quarterly_growth_momentum") == 0.0
        assert metrics.get("quarterly_growth_momentum_unavailable_reason") is None

    def test_single_garbage_revenue_quarter_diluted_average_now_excluded(self, monkeypatch):
        # Mixed case (mirrors the AFL-style EPS test above): 3 quarters with real, moderate
        # revenue growth plus 1 quarter whose prior-year revenue was implausibly tiny - the
        # bad quarter must be excluded, not averaged in with the 3 real ones.
        rows = self._quarters(
            [110_000_000.0, 120_000_000.0, 105_000_000.0, 115_000_000.0],
            prior_revenues=[100_000_000.0, 20.0, 100_000_000.0, 100_000_000.0],
        )
        loader = _make_loader(monkeypatch, quarterly_rows=rows)

        metrics = loader._compute_quarterly_metrics("DUOLIKE")

        # Only the 3 quarters with a real $100M prior-year base contribute: growth rates
        # 10%, 5%, 15% -> average 10%. The $20-based quarter must be excluded.
        assert metrics.get("quarterly_growth_momentum") == pytest.approx(10.0, abs=1e-2)
        assert metrics.get("quarterly_growth_momentum_unavailable_reason") is None

    def test_all_quarters_implausible_revenue_still_marked_unavailable(self, monkeypatch):
        rows = self._quarters(
            [100_000_000.0, 100_000_000.0, 100_000_000.0, 100_000_000.0],
            prior_revenues=[20.0, 20.0, 20.0, 20.0],
        )
        loader = _make_loader(monkeypatch, quarterly_rows=rows)

        metrics = loader._compute_quarterly_metrics("ALLGARBAGEREVCO")

        assert metrics.get("quarterly_growth_momentum") is None

    def test_near_zero_prior_quarter_eps_excluded_not_diluting_average(self, monkeypatch):
        # FIXED 2026-09-03 (goal session: "implausible values" investigation, AFL live
        # evidence): a single quarter's implausible ratio (prior_eps=0.0001 here) used to
        # get included un-bounded and only the AGGREGATE was checked - with 3 other 0%-
        # growth quarters diluting it, real cases like AFL's 1948.03% average stayed under
        # the 2000% cap and got silently trusted. Now the implausible quarter is excluded
        # from the average BEFORE combining (same "bound each side, not just the result"
        # governance as the margin_trend fix elsewhere in this file), leaving only the 3
        # genuinely-0%-growth quarters - a real, computable average, not a total loss of
        # signal, and no longer silently corruptible by one garbage quarter either.
        rows = self._quarters(
            [100_000_000.0, 100_000_000.0, 100_000_000.0, 100_000_000.0],
            epss=[0.5, 0.5, 0.5, 0.5],
            prior_epss=[0.5, 0.0001, 0.5, 0.5],
        )
        loader = _make_loader(monkeypatch, quarterly_rows=rows)

        metrics = loader._compute_quarterly_metrics("NIQ")

        assert metrics.get("earnings_growth_4q_avg") == 0.0
        assert metrics.get("earnings_growth_4q_avg_unavailable_reason") is None

    def test_afl_style_single_garbage_quarter_diluted_average_now_excluded(self, monkeypatch):
        # AFL-shaped: 3 quarters with real, moderate growth plus 1 quarter whose prior-year
        # EPS was implausibly tiny - before the fix, that one quarter's huge ratio (diluted
        # by the other 3) could still land the AVERAGE under the 2000% cap and get trusted
        # as real data. Now the bad quarter is excluded before averaging, so the result
        # reflects only the 3 genuinely-computable quarters, not a distorted blend.
        rows = self._quarters(
            [100_000_000.0] * 4,
            epss=[1.10, 1.20, 1.05, 1.15],
            prior_epss=[1.00, 0.0002, 1.00, 1.00],
        )
        loader = _make_loader(monkeypatch, quarterly_rows=rows)

        metrics = loader._compute_quarterly_metrics("AFLLIKE")

        # Only the 3 quarters with a real prior-year base (1.00) contribute: growth rates
        # 10%, 5%, 15% -> average 10%. The 0.0002-based quarter (~549,900% growth) must be
        # excluded, not averaged in.
        assert metrics.get("earnings_growth_4q_avg") == pytest.approx(10.0, abs=1e-2)
        assert metrics.get("earnings_growth_4q_avg_unavailable_reason") is None

    def test_all_quarters_implausible_still_marked_unavailable(self, monkeypatch):
        # Control: when EVERY quarter's individual ratio is implausible (not just one
        # diluted by normal siblings), eps_growth_rates ends up empty and the field
        # correctly falls through to the existing "no usable data" path.
        rows = self._quarters(
            [100_000_000.0, 100_000_000.0, 100_000_000.0, 100_000_000.0],
            epss=[0.5, 0.5, 0.5, 0.5],
            prior_epss=[0.0001, 0.0001, 0.0001, 0.0001],
        )
        loader = _make_loader(monkeypatch, quarterly_rows=rows)

        metrics = loader._compute_quarterly_metrics("ALLGARBAGECO")

        assert metrics.get("earnings_growth_4q_avg") is None

    def test_normal_quarterly_growth_still_computes(self, monkeypatch):
        rows = self._quarters(
            [100_000_000.0, 105_000_000.0, 110_000_000.0, 115_000_000.0],
            prior_revenues=[95_000_000.0, 100_000_000.0, 105_000_000.0, 110_000_000.0],
        )
        loader = _make_loader(monkeypatch, quarterly_rows=rows)

        metrics = loader._compute_quarterly_metrics("NORMALCO2")

        assert metrics.get("quarterly_growth_momentum") is not None
        assert abs(metrics["quarterly_growth_momentum"]) < 100_000.0


# TestEarningsSurpriseAvgGarbageBound REMOVED 2026-09-07 (goal-mode score sanity audit): the
# (last_eps - forward_eps)/|forward_eps| "earnings surprise" proxy this class bounded was
# itself the bug, not just its missing outlier guard - it compared a trailing single-quarter
# actual EPS against a forward FULL-YEAR analyst estimate, producing negative "surprise"
# values for real, live, consistently-beating companies (e.g. NVDA: -84.02% proxy vs. real
# per-quarter consensus surprises of +3.46% to +8.02%, live-confirmed against
# load_earnings_calendar.py's independently-sourced ground truth). Population-scale check:
# 931 of ~5,140 symbols showed the mathematically-impossible combination this proxy could
# produce (earnings_beat_rate=100 alongside earnings_surprise_avg<0, or the reverse) against
# load_enhanced_quality_growth_metrics.py's correct, real consensus-vs-actual computation.
# The proxy block in load_value_quality_growth_metrics.py was removed entirely (see that
# file's own "Phase 3A" removal note) rather than just adding the missing bound this class
# tested for - a correctly-bounded wrong formula is still wrong. That loader's
# _compute_earnings_surprise_metrics is now the sole source of both columns.
