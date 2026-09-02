"""Regression test (2026-09-02, "Missing SEC/XBRL data" root-cause audit goal session):
operating_profitability = (OperatingIncome - Interest) / StockholdersEquity is mathematically
undefined when StockholdersEquity is negative or zero - a real, common business-state fact for
mature buyback-heavy filers (live-confirmed AAL/ABBV, both with genuine multi-year negative book
equity on file), not an absent SEC concept. This fell through to the generic "missing_sec_data"
label, unlike pb_ratio/roic_pct/roce_pct which already carve out this exact denominator-sign
case via negative_book_value/negative_invested_capital/negative_capital_employed. Live sample of
the universe's operating_profitability missing_sec_data bucket: 325 of 583 symbols (56%) hit this
exact shape - the single largest component of that field's gap.
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
    # Same 33-column shape as test_reit_no_operating_income_concept_reason_20260901.py's fixture.
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
        None,  # 33 prior_year_gross_profit
    )


class TestOperatingProfitabilityNegativeEquityReason:
    def test_negative_equity_gets_negative_book_value_not_missing_sec_data(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=-3_727_000_000.0,
            operating_income=200_000_000.0,
            interest_expense=50_000_000.0,
        )

        metrics = loader._compute_quality_metrics("AAL", row, ev_metrics=None)

        assert metrics["operating_profitability"] is None
        assert metrics["operating_profitability_unavailable_reason"] == "negative_book_value"

    def test_zero_equity_gets_negative_book_value_not_missing_sec_data(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=0.0,
            operating_income=200_000_000.0,
            interest_expense=50_000_000.0,
        )

        metrics = loader._compute_quality_metrics("ZEROEQ", row, ev_metrics=None)

        assert metrics["operating_profitability"] is None
        assert metrics["operating_profitability_unavailable_reason"] == "negative_book_value"

    def test_negative_equity_wins_over_missing_ebit_input(self, monkeypatch):
        # Negative equity makes the ratio undefined regardless of whether the numerator is also
        # missing - same priority the existing negative_invested_capital check already gives
        # roic_pct over its own "reit_special_entity" structural check.
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=-3_727_000_000.0,
            operating_income=None,
            pretax_income=None,
            income_tax_expense=None,
            interest_expense=None,
        )

        metrics = loader._compute_quality_metrics("NOEBIT", row, ev_metrics=None)

        assert metrics["operating_profitability"] is None
        assert metrics["operating_profitability_unavailable_reason"] == "negative_book_value"

    def test_missing_operating_income_with_positive_equity_still_missing_sec_data(self, monkeypatch):
        # Control: with equity positive (no equity-sign issue) and no REIT-structural exemption,
        # a missing EBIT input must still fall back to the original generic label.
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=12_181_000_000.0,
            operating_income=None,
            pretax_income=None,
            income_tax_expense=None,
            interest_expense=None,
        )

        metrics = loader._compute_quality_metrics("NOEBIT2", row, ev_metrics=None)

        assert metrics["operating_profitability"] is None
        assert metrics["operating_profitability_unavailable_reason"] == "missing_sec_data"

    def test_positive_equity_control_unaffected(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=12_181_000_000.0,
            operating_income=200_000_000.0,
            interest_expense=50_000_000.0,
        )

        metrics = loader._compute_quality_metrics("ABBV2024", row, ev_metrics=None)

        assert metrics["operating_profitability"] is not None
        assert metrics["operating_profitability_unavailable_reason"] is None
