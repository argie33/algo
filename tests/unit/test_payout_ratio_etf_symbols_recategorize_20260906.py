"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep, same-day
follow-up to total_debt_unavailable_reason's own etf_symbols check): an ETF/UIT (SPY, IGV,
BKDV live-confirmed) has no "net_income" concept at all - it distributes fund income rather
than reporting corporate earnings - so a real dividend payment on file was mislabeled
"missing_sec_data" instead of "etf_trust_no_gaap_financials". Same "etf_symbols membership
alone is sufficient" rationale already used for total_debt - an ETF's absence of a net_income
concept doesn't depend on listing age the way _get_etf_trust_no_stockholders_equity_symbols()'s
narrower balance-sheet-history requirement does.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row():
    # Same 34-column shape as test_payout_ratio_roce_ebitda_margin_ric_recategorize_20260906.py's
    # fixture, but net_income=None (an ETF has no net_income concept at all, unlike a RIC which
    # can report a real positive net_income). current_assets/current_liabilities are real so the
    # row computes SOME real metrics (current_ratio) - otherwise the row-level "ALL metrics
    # null" early return fires first and never reaches payout_ratio's own per-field ternary at
    # all (a real, previously-encountered test-fixture trap, not a fixture preference).
    return (
        500_000_000.0,  # 0 stockholders_equity
        None,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        None,  # 3 net_income
        None,  # 4 revenue
        None,  # 5 operating_income
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
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
    )


class _FakeCursor:
    def __init__(self):
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        return []

    def fetchone(self):
        if "dividend_data" in self._last_query:
            # A real dividend payment on file (has_real_dividend_history would be True) - if
            # this ever gets reached for the ETF case, the fix has regressed.
            return (1,)
        return None


class _FakeDatabaseContext:
    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor()

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext())
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestPayoutRatioEtfSymbolsRecategorize:
    def test_etf_symbol_gets_etf_trust_reason_not_missing_sec_data(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row()
        with (
            patch.object(loader, "_get_etf_symbols", return_value=frozenset({"SPY"})),
            patch.object(loader, "_get_no_recent_net_income_symbols", return_value=frozenset()),
            patch.object(loader, "_get_never_tagged_net_income_symbols", return_value=frozenset()),
        ):
            metrics = loader._compute_quality_metrics("SPY", row, ev_metrics=None)

        assert metrics["payout_ratio"] is None
        assert metrics["payout_ratio_unavailable_reason"] == "etf_trust_no_gaap_financials"

    def test_non_etf_symbol_with_real_dividend_history_keeps_missing_sec_data(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row()
        with (
            patch.object(loader, "_get_etf_symbols", return_value=frozenset({"SPY"})),
            patch.object(loader, "_get_no_recent_net_income_symbols", return_value=frozenset()),
            patch.object(loader, "_get_never_tagged_net_income_symbols", return_value=frozenset()),
        ):
            metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["payout_ratio"] is None
        assert metrics["payout_ratio_unavailable_reason"] == "missing_sec_data"
