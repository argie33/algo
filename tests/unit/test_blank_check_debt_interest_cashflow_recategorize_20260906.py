"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep): a pre-merger
blank-check SPAC (SIC 6770) already gets "no_revenue_reported" ("Legitimate / not applicable")
directly wired into gross_profitability/operating_margin/gross_margin/ebitda_margin/roic_pct/
roce_pct's own ternary chains (see test_blank_check_spac_no_revenue_reason.py) - but the debt/
interest/cash-flow-derived fields (interest_coverage/debt_to_equity/ebitda/total_debt/
total_cash/accruals_ratio/fcf_margin/fcf_to_net_income/ocf_to_net_income/free_cash_flow/
operating_cash_flow) never got the same check, despite a blank-check shell having the identical
"no real operating business, only trust-account interest income" structural fact: no debt to
itemize, no interest expense beyond trust administration, no meaningful operating/free cash
flow. Same half-wired-fix pattern as the RIC/royalty-trust/ETF-trust broad recategorization
loops elsewhere in this file.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(**overrides):
    # Same 34-column shape as test_roic_pct_debt_to_equity_ric_recategorize_20260905.py's
    # fixture - real stockholders_equity/cash/current-assets-liabilities (a SPAC has a real
    # trust-account balance sheet), no debt/interest-expense/operating-income/dividends concept.
    base = {
        "stockholders_equity": 250_000_000.0,
        "total_liabilities": 5_000_000.0,
        "total_assets": 255_000_000.0,
        "net_income": 5_000_000.0,
        "revenue": None,
        "operating_income": None,
        "current_assets": 250_000_000.0,
        "current_liabilities": 5_000_000.0,
        "fiscal_year": 2025,
        "inventory": None,
        "interest_expense": None,
        "shares_outstanding": 25_000_000.0,
        "cost_of_revenue": None,
        "operating_cash_flow": None,
        "free_cash_flow": None,
        "dividends_paid": None,
        "earnings_per_share": None,
        "prior_year_eps": None,
        "prior_year_revenue": None,
        "gross_profit": None,
        "long_term_debt": None,
        "cash_and_equivalents": 5_000_000.0,
        "income_tax_expense": None,
        "pretax_income": None,
        "prior_year_net_income": None,
        "prior_year_operating_income": None,
        "prior_year_operating_cash_flow": None,
        "prior_year_free_cash_flow": None,
        "prior_year_cost_of_revenue": None,
        "prior_year_total_assets": None,
        "prior_year_stockholders_equity": None,
        "prior_year_pretax_income": None,
        "prior_year_interest_expense": None,
        "prior_year_gross_profit": None,
    }
    base.update(overrides)
    return tuple(base.values())


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


class TestBlankCheckDebtInterestCashflowRecategorize:
    def test_spac_shaped_symbol_across_newly_wired_fields(self, monkeypatch):
        loader = _make_loader(monkeypatch, blank_check_symbols=frozenset({"SPACX"}))
        metrics = loader._compute_quality_metrics("SPACX", _quality_row(), ev_metrics=(None, None, None, None))

        for field in (
            "interest_coverage",
            "debt_to_equity",
            "asset_turnover",
            "ebitda",
            "total_debt",
            "total_cash",
            "accruals_ratio",
            "fcf_margin",
            "fcf_to_net_income",
            "ocf_to_net_income",
            "free_cash_flow",
            "operating_cash_flow",
        ):
            assert metrics[field] is None, f"{field} unexpectedly computed a real value"
            assert metrics[f"{field}_unavailable_reason"] == "no_revenue_reported", (
                f"{field}_unavailable_reason was {metrics[f'{field}_unavailable_reason']!r}"
            )

    def test_non_blank_check_symbol_keeps_generic_reasons(self, monkeypatch):
        loader = _make_loader(monkeypatch, blank_check_symbols=frozenset({"SPACX"}))
        metrics = loader._compute_quality_metrics("NORMALCO", _quality_row(), ev_metrics=(None, None, None, None))

        for field in ("interest_coverage", "total_debt", "fcf_margin", "free_cash_flow"):
            assert metrics[f"{field}_unavailable_reason"] != "no_revenue_reported"

    def test_real_computed_values_are_not_clobbered(self, monkeypatch):
        # This fixture's real current_assets/current_liabilities/total_assets/net_income let
        # current_ratio/quick_ratio/roa/net_margin/debt_to_assets compute real values outright -
        # the recategorize loop's `metrics.get(_field) is None` guard must leave them untouched.
        loader = _make_loader(monkeypatch, blank_check_symbols=frozenset({"SPACX"}))
        metrics = loader._compute_quality_metrics("SPACX", _quality_row(), ev_metrics=(None, None, None, None))

        for field in ("current_ratio", "quick_ratio", "roa", "net_margin", "debt_to_assets"):
            assert metrics[field] is not None, f"{field} was unexpectedly None"
            assert metrics.get(f"{field}_unavailable_reason") is None
