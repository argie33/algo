"""Regression test: gross_margin_unavailable_reason must also treat a symbol from the broader
_get_no_recent_revenue_symbols()/_get_never_tagged_revenue_symbols() gate as "no_revenue_reported",
not just a symbol caught by the narrower SIC-code _get_blank_check_symbols() check.

Found live 2026-09-03 (goal: "Missing SEC/XBRL data" reduction, sibling-left-behind bug class -
same shape as bf82fc6d0's total_debt fix and this session's ebitda_margin/fcf_margin/
asset_turnover fix, see test_ebitda_fcf_asset_turnover_never_tagged_revenue_sibling_gap_20260903.py):
ps_ratio_unavailable_reason/ev_revenue_unavailable_reason/ebitda_margin_unavailable_reason/
fcf_margin_unavailable_reason/asset_turnover_unavailable_reason all OR in
_get_no_recent_revenue_symbols() and _get_never_tagged_revenue_symbols() for the identical
"genuinely no revenue reported" fact, but gross_margin only ever checked _get_blank_check_symbols()
(SIC 6770 pre-merger SPAC shells specifically) - live-confirmed 23 of 61 (38%) universe gross_margin
"missing_sec_data" rows are non-blank-check symbols (GNPX, CLRB, BOBS, PARK, OFRM, and more -
pre-revenue biotech/thin-filing-history/recent listings) already covered by the broader gate its
siblings use.
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


def _make_loader(
    monkeypatch,
    blank_check_symbols=frozenset(),
    no_recent_revenue_symbols=frozenset(),
    never_tagged_revenue_symbols=frozenset(),
):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    monkeypatch.setattr(loader, "_get_blank_check_symbols", lambda: blank_check_symbols)
    monkeypatch.setattr(loader, "_get_no_recent_revenue_symbols", lambda: no_recent_revenue_symbols)
    monkeypatch.setattr(loader, "_get_never_tagged_revenue_symbols", lambda: never_tagged_revenue_symbols)
    return loader


def _quality_row(revenue=None, cost_of_revenue=None, gross_profit=None):
    # Same 34-column shape as test_blank_check_spac_no_revenue_reason.py's fixture.
    return (
        None,  # 0 stockholders_equity
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        revenue,  # 4
        None,  # 5 operating_income
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        None,  # 11 shares_outstanding
        cost_of_revenue,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        gross_profit,  # 19 gross_profit
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


class TestGrossMarginNeverTaggedRevenueSiblingGap:
    def test_never_tagged_only_symbol_gets_no_revenue_reason(self, monkeypatch):
        # $0 revenue/COGS (real SEC data, not absent) so gross_profit_used = 0, not None -
        # must NOT hit reit_special_entity; must fail downstream on the genuine no-revenue cause.
        loader = _make_loader(monkeypatch, never_tagged_revenue_symbols=frozenset({"THIN"}))
        row = _quality_row(revenue=0.0, cost_of_revenue=0.0, gross_profit=None)

        metrics = loader._compute_quality_metrics("THIN", row, ev_metrics=None)

        assert metrics["gross_margin"] is None
        assert metrics["gross_margin_unavailable_reason"] == "no_revenue_reported"

    def test_no_recent_revenue_only_symbol_gets_no_revenue_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_revenue_symbols=frozenset({"NOREV"}))
        row = _quality_row(revenue=0.0, cost_of_revenue=0.0, gross_profit=None)

        metrics = loader._compute_quality_metrics("NOREV", row, ev_metrics=None)

        assert metrics["gross_margin"] is None
        assert metrics["gross_margin_unavailable_reason"] == "no_revenue_reported"

    def test_symbol_in_no_gate_keeps_generic_reason(self, monkeypatch):
        # Sanity check: a symbol in none of the three revenue-gap sets stays "missing_sec_data".
        loader = _make_loader(monkeypatch, never_tagged_revenue_symbols=frozenset({"THIN"}))
        row = _quality_row(revenue=0.0, cost_of_revenue=0.0, gross_profit=None)

        metrics = loader._compute_quality_metrics("OTHER", row, ev_metrics=None)

        assert metrics["gross_margin_unavailable_reason"] == "missing_sec_data"
