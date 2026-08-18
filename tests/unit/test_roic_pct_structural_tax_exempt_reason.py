"""Regression test (2026-08-18, country/industry SEC audit): roic_pct's effective_tax_rate
computation stayed None forever for filers that never once tag a pretax_income/
income_tax_expense concept (e.g. Marshall-Islands/Greek-operated shipping companies exempt
from US corporate income tax under IRC Section 883's tonnage-tax regime - GASS/ESEA/DSX and
13 more "Marine Shipping" symbols confirmed live). That is a genuine, permanent business-state
fact (structurally tax-exempt), not an absent SEC concept - same "3 consecutive years missing a
concept = structural, not a data gap" pattern already used for REIT/bank/insurer unclassified
balance sheets (_get_unclassified_balance_sheet_symbols). Fixed by treating a filer in
_get_no_tax_concept_symbols() as having a 0% effective tax rate, so roic_pct computes a real
NOPAT = operating_income instead of being marked "missing_sec_data".
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
    # Same 33-column shape as test_quality_metrics_implausible_ratio_reason.py's fixture.
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


class TestRoicPctStructuralTaxExemptReason:
    def test_structurally_tax_exempt_symbol_computes_roic_pct(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_tax_concept_symbols=frozenset({"GASS"}))
        row = _quality_row(
            stockholders_equity=690_326_610.0,
            long_term_debt=85_881_055.0,
            cash_and_equivalents=99_077_831.0,
            operating_income=55_132_949.0,
            income_tax_expense=None,
            pretax_income=None,
        )

        metrics = loader._compute_quality_metrics("GASS", row, ev_metrics=None)

        assert metrics["roic_pct"] is not None
        assert metrics["roic_pct_unavailable_reason"] is None

    def test_symbol_not_in_structural_set_still_reports_missing_sec_data(self, monkeypatch):
        # Control: the same missing tax/pretax inputs as above, but the symbol is NOT in the
        # structural no-tax-concept set - must keep the original "missing_sec_data" behavior,
        # not silently assume every unknown filer is tax-exempt.
        loader = _make_loader(monkeypatch, no_tax_concept_symbols=frozenset())
        row = _quality_row(
            stockholders_equity=690_326_610.0,
            long_term_debt=85_881_055.0,
            cash_and_equivalents=99_077_831.0,
            operating_income=55_132_949.0,
            income_tax_expense=None,
            pretax_income=None,
        )

        metrics = loader._compute_quality_metrics("NOTSHIPPINGCO", row, ev_metrics=None)

        assert metrics["roic_pct"] is None
        assert metrics["roic_pct_unavailable_reason"] == "missing_sec_data"
