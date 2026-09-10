"""Regression test (2026-09-10, goal: "SEC/XBRL missing data to zero" sweep, under-500 push):
the royalty-trust and blank-check recategorize loops in vqg_quality_recategorize.py each have a
`_trust_source_reasons`/`_blank_check_source_reasons` fallback set gating which generic reasons
they're allowed to overwrite - both sets were missing "no_recent_free_cash_flow_reported", even
though fcf_margin/free_cash_flow/operating_cash_flow/fcf_to_net_income/ocf_to_net_income are all
in their respective recategorize-fields tuples.

fcf_margin's own reason chain (vqg_quality_reasons_profitability.py) resolves to
"no_recent_free_cash_flow_reported" (via _get_no_recent_free_cash_flow_symbols()/
_get_never_tagged_free_cash_flow_symbols()) BEFORE ever falling through to the generic
"missing_sec_data" fallback both source-reason sets were originally built around, so live
royalty-trust (NRT) and blank-check-SPAC (COPL/LEGO/MTNE/NWAX/XFLH) symbols in that gate's live
query result never got recategorized for this field - same half-wired-fix pattern this file's
other tests already document for the RIC/ETF-trust loops.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(**overrides):
    base = [
        None,  # 0 stockholders_equity
        None,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        200_000_000.0,  # 4 revenue
        None,  # 5 operating_income
        None,  # 6 current_assets
        None,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        1_000_000.0,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        None,  # 19 gross_profit
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
    ]
    return tuple(base)


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
    monkeypatch, no_recent_fcf_symbols, blank_check_symbols=frozenset(), royalty_trust_symbols=frozenset()
):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    monkeypatch.setattr(loader, "_get_registered_investment_company_symbols", lambda: frozenset())
    monkeypatch.setattr(loader, "_get_etf_trust_no_stockholders_equity_symbols", lambda: frozenset())
    monkeypatch.setattr(loader, "_get_no_recent_capex_symbols", lambda: frozenset())
    monkeypatch.setattr(loader, "_get_no_recent_free_cash_flow_symbols", lambda: no_recent_fcf_symbols)
    monkeypatch.setattr(loader, "_get_never_tagged_free_cash_flow_symbols", lambda: frozenset())
    monkeypatch.setattr(loader, "_get_no_recent_revenue_symbols", lambda: frozenset())
    monkeypatch.setattr(loader, "_get_never_tagged_revenue_symbols", lambda: frozenset())
    monkeypatch.setattr(loader, "_get_free_cash_flow_available_elsewhere_symbols", lambda: frozenset())
    monkeypatch.setattr(loader, "_get_blank_check_symbols", lambda: blank_check_symbols)
    monkeypatch.setattr(loader, "_ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS", royalty_trust_symbols)
    return loader


class TestNoRecentFreeCashFlowReasonRecategorizeGap:
    def test_royalty_trust_symbol_recategorizes_fcf_margin(self, monkeypatch):
        loader = _make_loader(
            monkeypatch,
            no_recent_fcf_symbols=frozenset({"NRT"}),
            royalty_trust_symbols=frozenset({"NRT"}),
        )
        metrics = loader._compute_quality_metrics("NRT", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["fcf_margin"] is None
        assert metrics["fcf_margin_unavailable_reason"] == "reit_special_entity"

    def test_blank_check_symbol_recategorizes_fcf_margin(self, monkeypatch):
        loader = _make_loader(
            monkeypatch,
            no_recent_fcf_symbols=frozenset({"SPACX"}),
            blank_check_symbols=frozenset({"SPACX"}),
        )
        metrics = loader._compute_quality_metrics("SPACX", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["fcf_margin"] is None
        assert metrics["fcf_margin_unavailable_reason"] == "no_revenue_reported"

    def test_non_trust_non_blank_check_symbol_keeps_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_fcf_symbols=frozenset({"NORMALCO"}))
        metrics = loader._compute_quality_metrics("NORMALCO", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["fcf_margin_unavailable_reason"] == "no_recent_free_cash_flow_reported"
