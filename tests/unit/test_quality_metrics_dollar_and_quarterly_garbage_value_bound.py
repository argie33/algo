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
    def _quarters(self, revenues, net_incomes=None, epss=None):
        net_incomes = net_incomes or [1_000_000.0] * len(revenues)
        epss = epss or [0.5] * len(revenues)
        return [
            (2025, 4 - i, net_incomes[i], revenues[i], epss[i]) for i in range(len(revenues))
        ]

    def test_near_zero_prior_quarter_revenue_marked_unavailable(self, monkeypatch):
        # A near-zero (but nonzero) prior-quarter revenue makes the QoQ growth rate - and
        # therefore the 3-quarter average - mathematically enormous.
        rows = self._quarters([100_000_000.0, 0.01, 100_000_000.0, 100_000_000.0])
        loader = _make_loader(monkeypatch, quarterly_rows=rows)

        metrics = loader._compute_quarterly_metrics("DUO")

        assert metrics.get("quarterly_growth_momentum") is None
        assert metrics.get("quarterly_growth_momentum_unavailable_reason") == "garbage_metric_value_abs_gt_100000"

    def test_near_zero_prior_quarter_eps_marked_unavailable(self, monkeypatch):
        rows = self._quarters(
            [100_000_000.0, 100_000_000.0, 100_000_000.0, 100_000_000.0],
            epss=[0.5, 0.0001, 0.5, 0.5],
        )
        loader = _make_loader(monkeypatch, quarterly_rows=rows)

        metrics = loader._compute_quarterly_metrics("NIQ")

        assert metrics.get("earnings_growth_4q_avg") is None
        assert metrics.get("earnings_growth_4q_avg_unavailable_reason") == "garbage_metric_value_abs_gt_100000"

    def test_normal_quarterly_growth_still_computes(self, monkeypatch):
        rows = self._quarters([100_000_000.0, 105_000_000.0, 110_000_000.0, 115_000_000.0])
        loader = _make_loader(monkeypatch, quarterly_rows=rows)

        metrics = loader._compute_quarterly_metrics("NORMALCO2")

        assert metrics.get("quarterly_growth_momentum") is not None
        assert abs(metrics["quarterly_growth_momentum"]) < 100_000.0
