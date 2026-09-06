"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep): payout_ratio/
roce_pct/ebitda_margin/gross_profitability/asset_turnover/roa/operating_margin/net_margin/
current_ratio/quick_ratio/debt_to_assets/gross_margin/ebitda never had a registered-investment-
company (RIC) recategorization pass, unlike their siblings (roic_pct/debt_to_equity/total_debt/
total_cash/cash_per_share/interest_coverage) already wired into the `_ric_recategorize_fields`
loop near the end of `_compute_quality_metrics`.

A RIC (closed-end fund/investment trust) files a "Statement of Changes in Net Assets" - no
`dividends_paid`/operating_income/debt-component concepts to tag at all, even when it reports a
real, positive net_income (GGN-shaped: distributions are real cash outflows, just never tagged
under the conventional XBRL concept). Each of these fields' own ternary chain already falls back
to a reason already listed in `_ric_source_reasons` (e.g. "missing_sec_data") when no more
specific gate matches - they just weren't in the recategorize loop's field tuple, the same
half-wired-fix pattern as total_cash/cash_per_share/interest_coverage before their own fixes.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(**overrides):
    # Same 34-column shape as test_roic_pct_debt_to_equity_ric_recategorize_20260905.py's fixture.
    base = [
        5_000_000_000.0,  # 0 stockholders_equity - real, GGN-shaped
        None,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income - real and positive, GGN-shaped
        200_000_000.0,  # 4 revenue - real (interest/dividend income), GGN-shaped
        None,  # 5 operating_income - never itemized, GGN-shaped
        None,  # 6 current_assets
        None,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        1_000_000.0,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid - structurally absent, a RIC never tags this concept
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        None,  # 19 gross_profit
        None,  # 20 long_term_debt - structurally absent, a RIC has no debt concept
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
    def __init__(self):
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        return []

    def fetchone(self):
        # payout_ratio's own chain queries dividend_data for real recent history when
        # dividends_paid is None - a RIC genuinely does pay real distributions (just never
        # tags them under the conventional dividends_paid XBRL concept), so this must return
        # a row to reach "missing_sec_data" (a _ric_source_reasons member) rather than
        # "non_dividend_paying_stock" (which correctly stays generic, not a RIC-specific gap).
        # Every other fetchone() call in this function (fallback-year lookups etc.) expects
        # None (no fallback row available) - only dividend_data's own query gets a real row.
        if "dividend_data" in self._last_query:
            return (1,)
        return None


class _FakeDatabaseContext:
    def __enter__(self):
        return _FakeCursor()

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, ric_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    monkeypatch.setattr(loader, "_get_registered_investment_company_symbols", lambda: ric_symbols, raising=False)
    return loader


class TestPayoutRatioRicRecategorize:
    def test_ggn_shaped_ric_reports_registered_investment_company_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, ric_symbols=frozenset({"GGN"}))
        metrics = loader._compute_quality_metrics("GGN", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["payout_ratio"] is None
        assert metrics["payout_ratio_unavailable_reason"] == "registered_investment_company_no_xbrl"

    def test_non_ric_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, ric_symbols=frozenset({"GGN"}))
        metrics = loader._compute_quality_metrics("NORMALCO", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["payout_ratio_unavailable_reason"] != "registered_investment_company_no_xbrl"


class TestNewlyWiredFieldsRicRecategorize:
    def test_ggn_shaped_ric_across_all_newly_wired_fields(self, monkeypatch):
        loader = _make_loader(monkeypatch, ric_symbols=frozenset({"GGN"}))
        metrics = loader._compute_quality_metrics("GGN", _quality_row(), ev_metrics=(None, None, None, None))

        # gross_profitability/gross_margin/asset_turnover/roa/net_margin are deliberately
        # excluded from this fixture's assertion: GGN reports real revenue/net_income/
        # total_assets normally (only dividends_paid/operating_income/debt/current-assets-
        # liabilities/gross_profit/interest_expense are structurally absent), so asset_turnover/
        # roa/net_margin compute real values outright and gross_profitability/gross_margin hit
        # their own earlier "reit_special_entity" gate first (same no_gross_profit_concept check
        # - see test_ric_gross_profitability_hits_reit_gate_first below). All five stay in the
        # actual `_ric_recategorize_fields` fix - they're still needed for the (different) RIC
        # rows that do fall through to missing_sec_data on them.
        for field in (
            "ebitda_margin",
            "operating_margin",
            "current_ratio",
            "quick_ratio",
            "debt_to_assets",
            "ebitda",
        ):
            assert metrics[field] is None, f"{field} unexpectedly computed a real value"
            assert metrics[f"{field}_unavailable_reason"] == "registered_investment_company_no_xbrl", (
                f"{field}_unavailable_reason was {metrics[f'{field}_unavailable_reason']!r}"
            )

    def test_non_ric_keeps_generic_reasons(self, monkeypatch):
        loader = _make_loader(monkeypatch, ric_symbols=frozenset({"GGN"}))
        metrics = loader._compute_quality_metrics("NORMALCO", _quality_row(), ev_metrics=(None, None, None, None))

        for field in ("ebitda_margin", "current_ratio", "gross_margin", "ebitda"):
            assert metrics[f"{field}_unavailable_reason"] != "registered_investment_company_no_xbrl"

    def test_ric_gross_profitability_hits_reit_gate_first(self, monkeypatch):
        # This fixture's gross_profit=None trips gross_profitability's own earlier
        # no_gross_profit_concept check before ever reaching missing_sec_data, so it correctly
        # lands on "reit_special_entity" instead of the new RIC reason - both are
        # "Legitimate / not applicable" in /api/scores/coverage, just via different specific
        # causes. Recorded so a future session doesn't mistake this for the new fallback
        # failing to fire.
        loader = _make_loader(monkeypatch, ric_symbols=frozenset({"GGN"}))
        metrics = loader._compute_quality_metrics("GGN", _quality_row(), ev_metrics=(None, None, None, None))

        assert metrics["gross_profitability"] is None
        assert metrics["gross_profitability_unavailable_reason"] == "reit_special_entity"
