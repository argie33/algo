"""Regression test (2026-09-01, "missing SEC/XBRL data" audit goal session): AGNC/ARE/AMH-class
REITs and Marine Shipping tonnage-tax filers never tag OperatingIncomeLoss OR pretax_income/
income_tax_expense at all (live-confirmed: real, complete, filed 10-Ks with operating_income,
pretax_income, AND income_tax_expense all NULL every fiscal year 2020-2025). That's a permanent
business-structural fact (different accounting model), not a data gap - same class as
unclassified_balance_sheet/no_gross_profit_concept - but operating_profitability/
interest_coverage/roic_pct/roce_pct were still generically labeled "missing_sec_data" whenever
operating_income_for_margin (or roic_operating_income, its ROIC/ROCE-side sibling) came back
None, because the existing _get_no_tax_concept_symbols() structural check
(test_roic_pct_structural_tax_exempt_reason.py) was only ever wired into roic_pct's
effective_tax_rate=0.0 branch, not into these fields' "no EBIT input at all" case. Fixed by
reusing that same already-tested helper to recategorize these fields to "reit_special_entity"
once their EBIT-chain input is confirmed unrecoverable - the raw values stay None either way
(no fabricated numbers), only the label changes from "fixable XBRL gap" to "structural, not
applicable".

EXTENDED 2026-09-02 (same goal, continuation session): operating_margin fails on the exact same
`operating_income_for_margin is None` condition (same variable, same gate, immediately below
where `no_operating_income_concept` is computed) but was the one sibling left generically
labeled - live-confirmed 89/205 (43%) of the universe's operating_margin `missing_sec_data`
rows (AGNC/ARE/EGP/HR and more) are this exact REIT/no-tax-concept case.
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


class TestReitNoOperatingIncomeConceptReason:
    def test_reit_structural_symbol_gets_reit_special_entity_not_missing_sec_data(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_tax_concept_symbols=frozenset({"AGNC"}))
        row = _quality_row(
            stockholders_equity=12_181_000_000.0,
            long_term_debt=None,
            cash_and_equivalents=500_000_000.0,
            operating_income=None,
            income_tax_expense=None,
            pretax_income=None,
            interest_expense=100_000_000.0,
        )

        metrics = loader._compute_quality_metrics("AGNC", row, ev_metrics=None)

        # No fabricated values - these stay None either way.
        assert metrics["operating_profitability"] is None
        assert metrics.get("roic_pct") is None
        assert metrics.get("roce_pct") is None
        assert metrics.get("interest_coverage") is None
        assert metrics.get("operating_margin") is None

        # But the label changes from "fixable XBRL gap" to "structural, not applicable".
        assert metrics["operating_profitability_unavailable_reason"] == "reit_special_entity"
        assert metrics["roic_pct_unavailable_reason"] == "reit_special_entity"
        assert metrics["roce_pct_unavailable_reason"] == "reit_special_entity"
        assert metrics["interest_coverage_unavailable_reason"] == "reit_special_entity"
        assert metrics["operating_margin_unavailable_reason"] == "reit_special_entity"

    def test_symbol_not_in_structural_set_still_reports_missing_sec_data(self, monkeypatch):
        # Control: identical missing operating_income/pretax_income/income_tax_expense inputs,
        # but the symbol is NOT in the structural no-tax-concept set - must keep the original
        # "missing_sec_data" behavior, not silently assume every unknown filer is a REIT.
        loader = _make_loader(monkeypatch, no_tax_concept_symbols=frozenset())
        row = _quality_row(
            stockholders_equity=12_181_000_000.0,
            long_term_debt=None,
            cash_and_equivalents=500_000_000.0,
            operating_income=None,
            income_tax_expense=None,
            pretax_income=None,
            interest_expense=100_000_000.0,
        )

        metrics = loader._compute_quality_metrics("NOTAREIT", row, ev_metrics=None)

        assert metrics["operating_profitability_unavailable_reason"] == "missing_sec_data"
        assert metrics["roic_pct_unavailable_reason"] == "missing_sec_data"
        assert metrics["roce_pct_unavailable_reason"] == "missing_sec_data"
        assert metrics["interest_coverage_unavailable_reason"] == "missing_sec_data"
        assert metrics["operating_margin_unavailable_reason"] == "missing_sec_data"
