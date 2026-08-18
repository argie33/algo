"""Regression test (2026-08-18, "no SEC data" audit goal, roic_pct follow-up): roic_pct's
effective_tax_rate computation requires roic_pretax_income > 0 (a real reported pretax loss
makes "effective tax rate" undefined in the usual sense - real filers report all sorts of tax
expense/benefit against a loss from valuation allowances, NOL carrybacks, etc., not a
meaningful rate). When that gate fails, roic_pct was always labeled the generic
"missing_sec_data" reason - identical to what an actual SEC extraction gap gets - even though
we have complete real tax_expense/pretax_income data and the company is simply unprofitable
that year. Same distinction already established for pe_ratio/ev_ebitda/payout_ratio via the
"unprofitable_stock" reason (see their code in load_value_quality_growth_metrics.py).

Fixed by tracking roic_pct_unprofitable = (roic_pretax_income is not None and
roic_pretax_income <= 0) and using it in the final reason assignment, same precedence as
"implausible_ratio" (garbage-value bound still wins if it also fires).
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
    long_term_debt=None,
    cash_and_equivalents=None,
    income_tax_expense=None,
    pretax_income=None,
    interest_expense=None,
):
    # Same 33-column shape as test_quality_metrics_implausible_ratio_reason.py's fixture.
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
    )


class TestRoicPctUnprofitableStockReason:
    def test_real_pretax_loss_reports_unprofitable_stock(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=200_000_000.0,
            long_term_debt=50_000_000.0,
            cash_and_equivalents=10_000_000.0,
            operating_income=-3_000_000.0,
            income_tax_expense=-1_000_000.0,
            pretax_income=-5_000_000.0,
        )

        metrics = loader._compute_quality_metrics("LOSSCO", row, ev_metrics=None)

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "unprofitable_stock"

    def test_genuinely_missing_tax_data_still_reports_missing_sec_data(self, monkeypatch):
        # Control: no tax/pretax data anywhere (not a loss-year suppression) must keep the
        # original "missing_sec_data" reason, not be swept into "unprofitable_stock".
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=200_000_000.0,
            long_term_debt=50_000_000.0,
            cash_and_equivalents=10_000_000.0,
            operating_income=10_000_000.0,
            income_tax_expense=None,
            pretax_income=None,
        )

        metrics = loader._compute_quality_metrics("NODATACO", row, ev_metrics=None)

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "missing_sec_data"

    def test_profitable_company_still_computes_roic_pct(self, monkeypatch):
        # Control: a real, profitable, in-bounds case must be unaffected by this change.
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=200_000_000.0,
            long_term_debt=50_000_000.0,
            cash_and_equivalents=10_000_000.0,
            operating_income=40_000_000.0,
            income_tax_expense=8_000_000.0,
            pretax_income=32_000_000.0,
        )

        metrics = loader._compute_quality_metrics("PROFITCO", row, ev_metrics=None)

        assert metrics["roic_pct"] is not None
        assert metrics["roic_pct_unavailable_reason"] is None
