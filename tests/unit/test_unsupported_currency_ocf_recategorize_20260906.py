"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep, same-day
follow-up to the has_unsupported_currency_only_fact fix in load_financial_statements.py /
utils/external/sec_statements_shared.py and its sec_valuations.dcf_fcf sibling
recategorization in load_sec_valuations.py's _recategorize_unsupported_currency_dcf_fcf_
reason): a foreign private issuer whose annual_cash_flow row was already tagged
"unsupported_currency_no_fx_rate" (real operating_cash_flow, only tagged under a
hyperinflationary/unsupported local currency like ARS - GGAL/BBAR/BSAC/SUPV/TEO/TKC/TGS/TV
and more, live-confirmed via real SEC companyfacts) has a real, non-fabricatable ocf=None,
not a genuine loader gap - same "reason-string-doesn't-match-real-cause" bug class as the
RIC/royalty-trust recategorizations, never wired into quality_metrics/value_metrics' own
cash-flow-derived reason chains.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(**overrides):
    # Same 34-column shape as the sibling RIC-recategorize tests - free_cash_flow/
    # operating_cash_flow (indices 13/14) None, everything else a plausible real filer.
    base = [
        5_000_000_000.0,  # 0 stockholders_equity
        None,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        None,  # 4 revenue
        None,  # 5 operating_income
        None,  # 6 current_assets
        None,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        1_000_000.0,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow - structurally absent, tagged only in an unsupported currency
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


def _make_loader(monkeypatch, unsupported_currency_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    monkeypatch.setattr(loader, "_get_registered_investment_company_symbols", lambda: frozenset(), raising=False)
    monkeypatch.setattr(loader, "_get_etf_trust_no_stockholders_equity_symbols", lambda: frozenset(), raising=False)
    monkeypatch.setattr(
        loader, "_get_unsupported_currency_ocf_symbols", lambda: unsupported_currency_symbols, raising=False
    )
    return loader


class TestUnsupportedCurrencyOcfRecategorize:
    def test_fpi_shaped_symbol_reports_unsupported_currency_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, unsupported_currency_symbols=frozenset({"GGAL"}))
        metrics = loader._compute_quality_metrics("GGAL", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["free_cash_flow"] is None
        assert metrics["free_cash_flow_unavailable_reason"] == "unsupported_currency_no_fx_rate"
        assert metrics["operating_cash_flow"] is None
        assert metrics["operating_cash_flow_unavailable_reason"] == "unsupported_currency_no_fx_rate"

    def test_non_fpi_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, unsupported_currency_symbols=frozenset({"GGAL"}))
        metrics = loader._compute_quality_metrics("NORMALCO", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["free_cash_flow_unavailable_reason"] != "unsupported_currency_no_fx_rate"
        assert metrics["operating_cash_flow_unavailable_reason"] != "unsupported_currency_no_fx_rate"
