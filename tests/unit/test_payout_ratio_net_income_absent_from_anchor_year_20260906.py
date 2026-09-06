"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep): payout_ratio's
reason chain was missing the net_income_absent_from_anchor_year gate that
sustainable_growth_rate/net_margin/roa/roe/ebitda_margin already use (see
_get_net_income_available_elsewhere_symbols()'s docstring in vqg_symbol_gates.py) - a symbol
with real net_income on file in an earlier fiscal year, just not the current anchor year, was
falling straight through to the generic has_real_dividend_history check and getting mislabeled
"missing_sec_data" (Missing SEC/XBRL data) instead of the correct, already-established
"net_income_absent_from_anchor_year" (Legitimate / not applicable).
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row():
    # Same 34-column shape as test_payout_ratio_etf_symbols_recategorize_20260906.py's fixture -
    # net_income=None (anchor year), current_assets/current_liabilities real so the row computes
    # SOME real metrics and doesn't hit the row-level "ALL metrics null" early return first.
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
        # Only the dividend_data query (payout_ratio's own fallback) gets a real row - every
        # other fetchone() in this function (fallback-year lookups etc.) expects None. Should
        # never be reached in the anchor-year-gate-hit case: that gate must win first.
        if "dividend_data" in self._last_query:
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


class TestPayoutRatioNetIncomeAbsentFromAnchorYear:
    def test_net_income_available_elsewhere_gets_anchor_year_reason_not_missing_sec_data(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row()
        with (
            patch.object(loader, "_get_etf_symbols", return_value=frozenset()),
            patch.object(loader, "_get_no_recent_net_income_symbols", return_value=frozenset()),
            patch.object(loader, "_get_never_tagged_net_income_symbols", return_value=frozenset()),
            patch.object(loader, "_get_net_income_available_elsewhere_symbols", return_value=frozenset({"ANCHORCO"})),
        ):
            metrics = loader._compute_quality_metrics("ANCHORCO", row, ev_metrics=None)

        assert metrics["payout_ratio"] is None
        assert metrics["payout_ratio_unavailable_reason"] == "net_income_absent_from_anchor_year"

    def test_symbol_not_in_anchor_year_gate_keeps_missing_sec_data(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        row = _quality_row()
        with (
            patch.object(loader, "_get_etf_symbols", return_value=frozenset()),
            patch.object(loader, "_get_no_recent_net_income_symbols", return_value=frozenset()),
            patch.object(loader, "_get_never_tagged_net_income_symbols", return_value=frozenset()),
            patch.object(loader, "_get_net_income_available_elsewhere_symbols", return_value=frozenset()),
        ):
            metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["payout_ratio"] is None
        assert metrics["payout_ratio_unavailable_reason"] == "missing_sec_data"
