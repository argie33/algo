"""Regression test for the 2026-08-31 fix (goal session: "get all the data we need" full-
coverage audit): quality_metrics.gross_profitability (the Novy-Marx asset-based profitability
ratio) had two bugs, both diverging from its sibling gross_margin/gross_margin_trend despite
using the exact same underlying SEC concepts.

1. Missed-fallback bug: gross_profitability recomputed its numerator from ONLY the current
   anchor fiscal year's gross_profit/cost_of_revenue, ignoring gross_profit_used - the
   fallback-enriched figure computed a few lines above it in the same method (3-year window,
   then full history) that gross_margin already benefits from. Live DB sample: 437 of 1,941
   gross_profitability "missing_sec_data" symbols have a real gross_profit/cost_of_revenue
   figure somewhere in history that this fallback already recovers for gross_margin.

2. Mislabeled reason: unlike gross_margin/gross_margin_trend/current_ratio/quick_ratio, which
   all use no_gross_profit_concept/unclassified_balance_sheet to correctly report
   "reit_special_entity" for filers that structurally never report a COGS/gross-profit
   concept, gross_profitability always reported the generic "missing_sec_data" - reading as a
   fixable loader gap even for banks/REITs/service filers where the concept genuinely doesn't
   exist. Live-confirmed against real SEC companyfacts JSON: REGN ($7.9B FY2026 revenue) and
   JAZZ ($4.3B revenue) tag zero CostOfRevenue/CostOfGoodsSold/CostOfGoodsAndServicesSold since
   ~2020 - many commercial-stage pharma/biotech filers present an expense-based income
   statement with no gross-profit-style subtotal at all, the same structural-gap class as
   REITs/banks, not a loader bug.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    # _compute_quality_metrics issues many other DatabaseContext("read") fallback queries
    # (tax, balance sheet, debt, FCF, ...) besides the gross_profit/cost_of_revenue one this
    # test targets - only answer the gross-profit query with the configured fallback_row, so
    # those unrelated queries see "no fallback data" (None) instead of a same-shape-mismatched
    # tuple from a completely different query.
    def __init__(self, fallback_row=None):
        self._fallback_row = fallback_row
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        return []

    def fetchone(self):
        if "SELECT gross_profit, cost_of_revenue, revenue" in self._last_query:
            return self._fallback_row
        return None


class _FakeDatabaseContext:
    def __init__(self, fallback_row=None):
        self._fallback_row = fallback_row

    def __enter__(self):
        return _FakeCursor(self._fallback_row)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, fallback_row=None):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(fallback_row))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(gross_profit=None, cost_of_revenue=None, revenue=None):
    # Same 34-column shape as test_quality_metrics_implausible_ratio_reason.py's fixture.
    # total_assets (index 2) fixed at 700_000_000.0 so gross_profitability is computable
    # whenever a numerator is found.
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
        cost_of_revenue,  # 12
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        gross_profit,  # 19
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


class TestGrossProfitabilityReusesGrossMarginsFallback:
    def test_recovers_value_from_fallback_year_when_current_year_has_neither(self, monkeypatch):
        # Current year (row above) has gross_profit=None, cost_of_revenue=None - only a
        # fallback DB query can find anything. Fallback row: (gross_profit, cost_of_revenue,
        # revenue) = (140_000_000.0, None, None) - a real prior-year gross_profit on file.
        loader = _make_loader(monkeypatch, fallback_row=(140_000_000.0, None, None))
        row = _quality_row()

        metrics = loader._compute_quality_metrics("RECOVERED", row, ev_metrics=None)

        assert metrics["gross_profitability"] == 140_000_000.0 / 700_000_000.0 * 100.0
        assert metrics["gross_profitability_unavailable_reason"] is None

    def test_never_reported_reports_reit_special_entity_not_missing_sec_data(self, monkeypatch):
        # No current-year data AND no fallback row at all (fetchone always None) - this
        # symbol has never once reported gross_profit/cost_of_revenue, the same structural-
        # gap class gross_margin already labels "reit_special_entity".
        loader = _make_loader(monkeypatch, fallback_row=None)
        row = _quality_row()

        metrics = loader._compute_quality_metrics("NOGROSSPROFIT", row, ev_metrics=None)

        assert metrics["gross_profitability"] is None
        assert metrics["gross_profitability_unavailable_reason"] == "reit_special_entity"
        # gross_margin must agree - same underlying signal, same label.
        assert metrics["gross_margin_unavailable_reason"] == "reit_special_entity"

    def test_missing_total_assets_still_reports_missing_sec_data(self, monkeypatch):
        # Control: a real gross_profit on hand but no total_assets is a genuine SEC data gap,
        # not a structural no-COGS-concept case - must NOT be swept into "reit_special_entity".
        loader = _make_loader(monkeypatch, fallback_row=None)
        row = list(_quality_row(gross_profit=50_000_000.0))
        row[2] = None  # total_assets
        metrics = loader._compute_quality_metrics("NOASSETS", tuple(row), ev_metrics=None)

        assert metrics["gross_profitability"] is None
        assert metrics["gross_profitability_unavailable_reason"] == "missing_sec_data"
