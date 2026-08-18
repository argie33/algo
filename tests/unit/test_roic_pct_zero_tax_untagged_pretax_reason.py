"""Regression test (2026-08-18, missing factor inputs audit): roic_pct's effective_tax_rate
computation stayed None forever for filers that explicitly tag IncomeTaxExpenseBenefit=$0
every year but never tag any of the three pretax_income concepts sec_statements.py maps -
live-confirmed on RZLT/PASG/AKTS-class filers (simple loss-making biotechs/small-caps with no
separate "before tax" line since there's nothing to reconcile against $0 tax). This is NOT the
net_income+income_tax_expense approximation (rejected: only ~75% agreement across the universe
due to noncontrolling-interest/discontinued-ops adjustments) - effective_tax_rate = tax/pretax
needs no approximation when tax is EXACTLY 0, since 0/x = 0 for any nonzero x regardless of x's
untagged value. 289 universe symbols had exactly this tax_expense=0/pretax_income=NULL
combination.
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


def _make_loader(monkeypatch, no_tax_concept_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    monkeypatch.setattr(loader, "_get_no_tax_concept_symbols", lambda: no_tax_concept_symbols)
    return loader


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
        -74_400_000.0,  # 3 net_income
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
        None,  # 33 prior_year_gross_profit
    )


class TestRoicPctZeroTaxUntaggedPretaxReason:
    def test_zero_tax_untagged_pretax_computes_roic_pct(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=82_569_000.0,
            long_term_debt=1_111_000.0,
            cash_and_equivalents=11_236_000.0,
            operating_income=-79_894_000.0,
            income_tax_expense=0.0,
            pretax_income=None,
        )

        metrics = loader._compute_quality_metrics("RZLT", row, ev_metrics=None)

        assert metrics["roic_pct"] is not None
        assert metrics["roic_pct_unavailable_reason"] is None

    def test_none_tax_untagged_pretax_still_reports_missing_sec_data(self, monkeypatch):
        # Control: income_tax_expense is None (never reported at all, not confirmed $0) - must
        # NOT be treated the same as an exact $0 tax expense, since we don't actually know the
        # rate in that case.
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=82_569_000.0,
            long_term_debt=None,
            cash_and_equivalents=11_236_000.0,
            operating_income=-79_894_000.0,
            income_tax_expense=None,
            pretax_income=None,
        )

        metrics = loader._compute_quality_metrics("UNKNOWNCO", row, ev_metrics=None)

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "missing_sec_data"
