"""Regression test (2026-09-10, "under 500" SEC/XBRL missing-data push): two real
debt_to_equity gaps found while live-auditing quality_metrics.debt_to_equity_unavailable_
reason='missing_sec_data' rows against real SEC companyfacts.

1. A real, literal $0.00 anchor-year stockholders_equity (live-confirmed FLOC/INR/WBI - a
   genuinely tagged value, not a missing one) fell into the same generic branch as "equity
   was never tagged at all" and landed on the vague "missing_sec_data" reason instead of
   "implausible_ratio" (division by zero) - same near-zero-denominator discipline
   roic_pct/roce_pct above it in vqg_quality.py already apply.

2. debt_for_roic's only fallback (when total_debt_ev and the anchor year's own long_term_debt
   are both absent) searched ONLY the `long_term_debt` column - live-confirmed ATHR (real
   short_term_debt, never long_term_debt) and BRNS (real operating_lease_liability, never
   long_term_debt) have genuine, current SEC debt data that fallback couldn't see, so
   debt_for_roic stayed None and fell through to "missing_sec_data" too.
   _fetch_total_debt_components_fallback sums all 4 canonical debt components - the SAME
   definition sec_valuations_checks.py's own total_debt fallback already uses - as a final
   rescue tier.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    def __init__(self, fetchone_result=None):
        self._fetchone_result = fetchone_result

    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return self._fetchone_result


class _FakeDatabaseContext:
    def __init__(self, fetchone_result=None):
        self._fetchone_result = fetchone_result

    def __enter__(self):
        return _FakeCursor(self._fetchone_result)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, fetchone_result=None):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(fetchone_result))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(
    stockholders_equity=None,
    total_liabilities=200_000_000.0,
    total_assets=700_000_000.0,
    net_income=50_000_000.0,
    revenue=None,
    operating_income=None,
    current_assets=150_000_000.0,
    current_liabilities=100_000_000.0,
    inventory=None,
    cost_of_revenue=None,
    gross_profit=None,
    long_term_debt=None,
    cash_and_equivalents=None,
    income_tax_expense=None,
    pretax_income=None,
    interest_expense=None,
):
    # Same 34-column shape as test_quality_metrics_roe_debt_ratio_implausible_bound.py's
    # fixture.
    return (
        stockholders_equity,  # 0
        total_liabilities,  # 1
        total_assets,  # 2
        net_income,  # 3
        revenue,  # 4
        operating_income,  # 5
        current_assets,  # 6
        current_liabilities,  # 7
        2025,  # 8 fiscal_year
        inventory,  # 9
        interest_expense,  # 10
        None,  # 11 shares_outstanding
        cost_of_revenue,  # 12
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
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


class TestDebtToEquityZeroEquity:
    def test_zero_stockholders_equity_reports_implausible_ratio_not_missing_sec_data(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        # A real, tagged $0.00 equity (not None) with real debt - division is undefined, not
        # "SEC data is missing".
        row = _quality_row(stockholders_equity=0.0, long_term_debt=100_000_000.0)

        metrics = loader._compute_quality_metrics("FLOC", row, ev_metrics=None)

        assert metrics["debt_to_equity"] is None
        assert metrics["debt_to_equity_unavailable_reason"] == "implausible_ratio"


class TestDebtForRoicTotalDebtComponentsFallback:
    def test_fetch_total_debt_components_fallback_sums_all_four_components(self, monkeypatch):
        # long_term_debt NULL, short_term_debt real - same shape as the live ATHR gap.
        loader = _make_loader(monkeypatch, fetchone_result=(None, 20_516.0, None, None))

        result = loader._fetch_total_debt_components_fallback("ATHR")

        assert result == 20_516.0

    def test_fetch_total_debt_components_fallback_returns_none_when_all_null(self, monkeypatch):
        loader = _make_loader(monkeypatch, fetchone_result=None)

        result = loader._fetch_total_debt_components_fallback("NODEBTCO")

        assert result is None

    def test_debt_to_equity_recovers_via_lease_only_fallback(self, monkeypatch):
        # long_term_debt never tagged anywhere (anchor row AND the plain long_term_debt
        # fallback both come up empty) but operating_lease_liability is real - same shape as
        # the live BRNS gap. Row has no long_term_debt/total_debt_ev; the fake DB layer
        # returns the lease-liability-only fallback row for every fallback query fired.
        # cash_and_equivalents is set (non-None) so the separate stockholders_equity/cash
        # anchor-fallback query (a different column shape) never fires against this same
        # fixed fake cursor - keeps this test isolated to the debt-only fallback path.
        loader = _make_loader(monkeypatch, fetchone_result=(None, None, 11_281_000.0, None))
        row = _quality_row(stockholders_equity=74_208_000.0, long_term_debt=None, cash_and_equivalents=1_000_000.0)

        metrics = loader._compute_quality_metrics("BRNS", row, ev_metrics=None)

        assert metrics["debt_to_equity"] is not None
        assert metrics["debt_to_equity"] == 11_281_000.0 / 74_208_000.0
