"""Regression test (2026-08-18, "missing factor inputs" audit continued): roic_pct's
effective_tax_rate computation stayed "missing_sec_data" for REITs/mortgage trusts (ADC/Agree
Realty, AAT/American Assets Trust, ABR/Arbor Realty live-confirmed via real annual_income_statement
rows) whose 10-Ks go straight from revenue to net income with no distinct "income before tax"
subtotal line to tag at all - not a data gap, a structural absence of the pretax_income concept
itself, same class as _get_no_tax_concept_symbols's fully-tax-exempt filers. Unlike that fully
tax-exempt case, these filers DO report a real, usually small, income_tax_expense most years
(built-in-gains tax on a taxable REIT subsidiary, state tax) - live-confirmed ADC FY2025:
income_tax_expense=$1.735M on net_income=$204.3M (~0.85% of net income).

Fixed by treating a filer confirmed to have zero pretax_income concept in 3+ years
(_get_never_tagged_pretax_income_symbols) as having pretax_income approximated by
net_income + income_tax_expense FOR THE SAME FISCAL YEAR (never mixes years - see
roic_net_income's fallback-row tracking in load_value_quality_growth_metrics.py), bounded by
the same [-0.60, 0.60] plausibility check as every other effective_tax_rate branch.
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


def _make_loader(monkeypatch, never_tagged_pretax_income_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    monkeypatch.setattr(loader, "_get_never_tagged_pretax_income_symbols", lambda: never_tagged_pretax_income_symbols)
    # No filer here is in the fully-tax-exempt set - the two structural fallbacks are
    # independent branches and must not accidentally rely on each other.
    monkeypatch.setattr(loader, "_get_no_tax_concept_symbols", lambda: frozenset())
    return loader


def _quality_row(
    stockholders_equity=None,
    net_income=None,
    operating_income=None,
    long_term_debt=None,
    cash_and_equivalents=None,
    income_tax_expense=None,
    pretax_income=None,
    interest_expense=None,
):
    # Same 33-column shape as test_roic_pct_structural_tax_exempt_reason.py's fixture.
    return (
        stockholders_equity,  # 0
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        net_income,  # 3
        None,  # 4 revenue
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


class TestRoicPctNeverTaggedPretaxIncomeReason:
    def test_reit_with_small_tax_and_no_pretax_concept_computes_roic_pct(self, monkeypatch):
        # ADC-shaped: real operating_income, real (small) income_tax_expense, pretax_income
        # never tagged, symbol confirmed structurally pretax-absent.
        loader = _make_loader(monkeypatch, never_tagged_pretax_income_symbols=frozenset({"ADC"}))
        row = _quality_row(
            stockholders_equity=6_270_985_000.0,
            long_term_debt=3_323_378_000.0,  # DebtInstrumentCarryingAmount fallback, see load_financial_statements.py
            cash_and_equivalents=10_000_000.0,
            operating_income=340_395_000.0,
            income_tax_expense=1_735_000.0,
            pretax_income=None,
            net_income=204_349_000.0,
        )

        metrics = loader._compute_quality_metrics("ADC", row, ev_metrics=None)

        assert metrics["roic_pct"] is not None
        assert metrics["roic_pct_unavailable_reason"] is None
        invested_capital = 6_270_985_000.0 + 3_323_378_000.0 - 10_000_000.0
        # The implied rate (~0.84%) should barely dent NOPAT vs. treating tax as 0.
        assert metrics["roic_pct"] < (340_395_000.0 / invested_capital) * 100

    def test_symbol_not_in_never_tagged_set_still_reports_missing_sec_data(self, monkeypatch):
        # Control: identical inputs, but the symbol is NOT confirmed structurally
        # pretax-absent - must keep reporting "missing_sec_data", not silently assume every
        # filer with a missing pretax_income is a REIT-like structural case.
        loader = _make_loader(monkeypatch, never_tagged_pretax_income_symbols=frozenset())
        row = _quality_row(
            stockholders_equity=6_270_985_000.0,
            long_term_debt=None,
            cash_and_equivalents=10_000_000.0,
            operating_income=340_395_000.0,
            income_tax_expense=1_735_000.0,
            pretax_income=None,
            net_income=204_349_000.0,
        )

        metrics = loader._compute_quality_metrics("NOTAREIT", row, ev_metrics=None)

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "missing_sec_data"

    def test_implausibly_large_implied_rate_stays_unavailable(self, monkeypatch):
        # tax_expense so large relative to net_income that the implied rate blows past the
        # [-0.60, 0.60] plausibility bound - must not silently accept a wild approximation.
        loader = _make_loader(monkeypatch, never_tagged_pretax_income_symbols=frozenset({"WILDCO"}))
        row = _quality_row(
            stockholders_equity=6_270_985_000.0,
            long_term_debt=None,
            cash_and_equivalents=10_000_000.0,
            operating_income=340_395_000.0,
            income_tax_expense=900_000_000.0,
            pretax_income=None,
            net_income=100_000_000.0,
        )

        metrics = loader._compute_quality_metrics("WILDCO", row, ev_metrics=None)

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "implausible_ratio"
