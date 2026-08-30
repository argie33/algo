"""Regression test (2026-08-17, "no SEC data" audit goal): the |ratio| > 1000 garbage-value
bound shared by gross_margin, ebitda_margin, roic_pct, operating_margin, net_margin, and
interest_coverage (see test_quality_metrics_ratio_garbage_value_bound.py /
test_interest_coverage_ebit_fallback.py for the bound itself) labeled every suppressed value
with the generic "missing_sec_data" reason - identical to what a real SEC extraction gap gets.

Live DB audit found this bound firing about as often on real, if extreme, values (pre-revenue
biotechs and SPACs with near-zero revenue against normal-scale expenses - a genuine business
characteristic, not corrupted data) as on actual garbage (mis-scaled/mis-tagged SEC facts like
CRML's revenue=$540). Both cases reported "missing_sec_data" ("SEC data not available"), which
reads as a loader/extraction failure even when the loader worked fine and computed a real ratio
that was then deliberately suppressed as implausible - directly inflating the appearance of
"loaders are failing" when the actual cause is a suppression-and-mislabeling bug. Fixed by
reusing the "implausible_ratio" reason string payout_ratio already established for its own
analogous bound, so the frontend can distinguish "we computed something and didn't trust it"
from "SEC never reported this data at all".
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __enter__(self):
        return _FakeCursor()

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(
    stockholders_equity=None,
    revenue=None,
    operating_income=None,
    cost_of_revenue=None,
    gross_profit=None,
    long_term_debt=None,
    cash_and_equivalents=None,
    income_tax_expense=None,
    pretax_income=None,
    interest_expense=None,
    free_cash_flow=None,
    operating_cash_flow=None,
):
    # Same 33-column shape as test_quality_metrics_ratio_garbage_value_bound.py's fixture.
    return (
        stockholders_equity,  # 0
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        revenue,  # 4
        operating_income,  # 5
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        interest_expense,  # 10 interest_expense
        None,  # 11 shares_outstanding
        cost_of_revenue,  # 12
        operating_cash_flow,  # 13
        free_cash_flow,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        gross_profit,  # 19
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


class TestImplausibleRatioReasonNotConflatedWithMissingSecData:
    def test_gross_margin_bound_reports_implausible_ratio(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(gross_profit=125_000_000.0, revenue=540.0)

        metrics = loader._compute_quality_metrics("CRML", row, ev_metrics=None)

        assert metrics["gross_margin"] is None
        assert metrics["gross_margin_unavailable_reason"] == "implausible_ratio"

    def test_ebitda_margin_bound_reports_implausible_ratio(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(revenue=2_454_000.0)
        ev_metrics = (None, None, 155_771_000.0)

        metrics = loader._compute_quality_metrics("CLBT", row, ev_metrics=ev_metrics)

        assert metrics["ebitda_margin"] is None
        assert metrics["ebitda_margin_unavailable_reason"] == "implausible_ratio"

    def test_roic_pct_bound_reports_implausible_ratio(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=-999_000_000.0,
            long_term_debt=1_000_000_000.0,
            cash_and_equivalents=500_000.0,
            operating_income=10_000_000.0,
            income_tax_expense=2_000_000.0,
            pretax_income=10_000_000.0,
        )

        metrics = loader._compute_quality_metrics("MCK", row, ev_metrics=None)

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "implausible_ratio"

    def test_operating_margin_bound_reports_implausible_ratio(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(operating_income=35_000_000.0, revenue=987_000.0)

        metrics = loader._compute_quality_metrics("KARO", row, ev_metrics=None)

        assert metrics["operating_margin"] is None
        assert metrics["operating_margin_unavailable_reason"] == "implausible_ratio"

    def test_net_margin_bound_reports_implausible_ratio(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(revenue=987_000.0)

        metrics = loader._compute_quality_metrics("KARO", row, ev_metrics=None)

        assert metrics["net_margin"] is None
        assert metrics["net_margin_unavailable_reason"] == "implausible_ratio"

    def test_interest_coverage_bound_reports_implausible_ratio(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(operating_income=-17_841_919.0, interest_expense=5.0, pretax_income=None)

        metrics = loader._compute_quality_metrics("IKT", row, ev_metrics=None)

        assert metrics["interest_coverage"] is None
        assert metrics["interest_coverage_unavailable_reason"] == "implausible_ratio"

    def test_fcf_margin_bound_reports_implausible_ratio(self, monkeypatch):
        # ADDED 2026-08-26 (Quality pillar exhaustive-input review): fcf_margin's first
        # production run had no bound at all (unlike every sibling ratio tested above) - live-
        # caught 321 rows with |fcf_margin| > 500% (e.g. MYSE: -776,645%, revenue ~$550), same
        # near-zero-revenue-shell failure mode as gross_margin/net_margin/operating_margin above.
        loader = _make_loader(monkeypatch)
        row = _quality_row(revenue=1_000.0, free_cash_flow=-2_000_000.0)

        metrics = loader._compute_quality_metrics("MYSE", row, ev_metrics=None)

        assert metrics["fcf_margin"] is None
        assert metrics["fcf_margin_unavailable_reason"] == "implausible_ratio"

    def test_operating_profitability_bound_reports_implausible_ratio(self, monkeypatch):
        # ADDED 2026-08-30 (goal: full-data audit, live sanity-check pass): operating_profitability
        # had no bound at all (unlike every sibling ratio tested above) - live-caught
        # min=-93,407.89%/max=16,821.79% already on file, same near-zero-denominator failure mode
        # as fcf_margin above, but for stockholders_equity instead of revenue.
        loader = _make_loader(monkeypatch)
        row = _quality_row(stockholders_equity=500_000.0, operating_income=10_000_000.0)

        metrics = loader._compute_quality_metrics("TINYEQ", row, ev_metrics=None)

        assert metrics["operating_profitability"] is None
        assert metrics["operating_profitability_unavailable_reason"] == "implausible_ratio"

    def test_accruals_ratio_bound_reports_implausible_ratio(self, monkeypatch):
        # ADDED 2026-08-30 (goal: full-data audit, live sanity-check pass): accruals_ratio
        # ((net_income - operating_cash_flow) / total_assets * 100) had no bound at all - live-
        # caught min=-6,910.69%/max=50,558.09% already on file, same near-zero-total_assets
        # failure mode as gross_profitability above (same denominator).
        loader = _make_loader(monkeypatch)
        # fixture's total_assets is fixed at 700_000_000.0, net_income at 50_000_000.0 - a large
        # negative operating_cash_flow makes (net_income - ocf) / total_assets blow past 1000%.
        row = _quality_row(operating_cash_flow=-8_000_000_000.0)

        metrics = loader._compute_quality_metrics("HUGEACCRUAL", row, ev_metrics=None)

        assert metrics["accruals_ratio"] is None
        assert metrics["accruals_ratio_unavailable_reason"] == "implausible_ratio"

    def test_genuine_missing_data_still_reports_missing_sec_data(self, monkeypatch):
        # Control: no revenue/operating_income at all (not a bound suppression) must keep
        # the original "missing_sec_data" reason, not be swept into "implausible_ratio".
        loader = _make_loader(monkeypatch)
        row = _quality_row(operating_income=None, revenue=None)

        metrics = loader._compute_quality_metrics("NODATACO", row, ev_metrics=None)

        assert metrics["operating_margin"] is None
        assert metrics["operating_margin_unavailable_reason"] == "missing_sec_data"
