"""Regression test (2026-08-19, "no SEC data" audit, roic_pct/gross_margin/ebitda_margin
follow-up): roic_pct/gross_margin/ebitda_margin were mislabeled "missing_sec_data" for SEC-
classified blank-check (SIC 6770, pre-merger SPAC) companies, reading as a loader failure
instead of the genuine structural fact that a shell company with no operating business has
no meaningful revenue/gross-profit/return-on-capital to report. Live-confirmed: 343
universe symbols carry this SIC classification; 326/270/314 of them respectively were
mislabeled this way. Same "SEC's own classification settles it, not a data gap" pattern as
_get_unclassified_balance_sheet_symbols (REITs/banks) and _get_no_tax_concept_symbols
(tonnage-tax shipping filers).
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


def _make_loader(monkeypatch, blank_check_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    monkeypatch.setattr(loader, "_get_blank_check_symbols", lambda: blank_check_symbols)
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
    cost_of_revenue=None,
    gross_profit=None,
):
    # Same 34-column shape as test_roic_pct_structural_tax_exempt_reason.py's fixture.
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
        cost_of_revenue,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        gross_profit,  # 19 gross_profit
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


class TestBlankCheckSpacNoRevenueReason:
    def test_roic_pct_gets_no_revenue_reported_for_blank_check_symbol(self, monkeypatch):
        loader = _make_loader(monkeypatch, blank_check_symbols=frozenset({"SPACX"}))
        row = _quality_row(
            stockholders_equity=250_000_000.0,
            long_term_debt=None,
            cash_and_equivalents=5_000_000.0,
            operating_income=55_132_949.0,
            income_tax_expense=None,
            pretax_income=None,
        )

        metrics = loader._compute_quality_metrics("SPACX", row, ev_metrics=None)

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "no_revenue_reported"

    def test_roic_pct_control_non_spac_still_reports_missing_sec_data(self, monkeypatch):
        # Same inputs as above but the symbol is NOT in the blank-check set - must keep the
        # original "missing_sec_data" behavior, not silently assume any filer missing tax
        # data is a shell company.
        loader = _make_loader(monkeypatch, blank_check_symbols=frozenset())
        row = _quality_row(
            stockholders_equity=250_000_000.0,
            long_term_debt=None,
            cash_and_equivalents=5_000_000.0,
            operating_income=55_132_949.0,
            income_tax_expense=None,
            pretax_income=None,
        )

        metrics = loader._compute_quality_metrics("REALCO", row, ev_metrics=None)

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "missing_sec_data"

    def test_gross_margin_gets_no_revenue_reported_for_blank_check_symbol(self, monkeypatch):
        # A SPAC that explicitly tags $0 revenue and $0 COGS (real SEC data, not absent) -
        # gross_profit_used = 0 - 0 = 0 (not None), so this must NOT hit the
        # reit_special_entity ("no gross profit concept at all") branch; it fails downstream
        # because revenue itself is 0, which is the genuine blank-check case.
        loader = _make_loader(monkeypatch, blank_check_symbols=frozenset({"SPACX"}))
        row = _quality_row(revenue=0.0, cost_of_revenue=0.0, gross_profit=None)

        metrics = loader._compute_quality_metrics("SPACX", row, ev_metrics=None)

        assert metrics["gross_margin"] is None
        assert metrics["gross_margin_unavailable_reason"] == "no_revenue_reported"

    def test_ebitda_margin_gets_no_revenue_reported_for_blank_check_symbol(self, monkeypatch):
        # Deliberately NOT in _get_no_recent_revenue_symbols() (default empty via
        # _FakeCursor) - a too-recently-IPO'd SPAC without 3 years of filing history yet
        # must still be caught via its SIC classification alone.
        loader = _make_loader(monkeypatch, blank_check_symbols=frozenset({"SPACX"}))
        row = _quality_row(revenue=0.0, cost_of_revenue=0.0, operating_income=-236_236.0)

        metrics = loader._compute_quality_metrics("SPACX", row, ev_metrics=None)

        assert metrics["ebitda_margin"] is None
        assert metrics["ebitda_margin_unavailable_reason"] == "no_revenue_reported"
