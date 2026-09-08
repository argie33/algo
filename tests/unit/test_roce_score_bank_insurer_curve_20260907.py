"""Regression test (2026-09-07, goal: stock_scores factor/composite sanity audit).

roce_score used the same industrial curve ((8.0,40),(15.0,75),(25.0,100)) for every sector, even
though capital_employed already uses debt_for_roic=total_liabilities for depository banks/
insurers (see that override's own comment near debt_to_equity_score) - a bank's capital_employed
is therefore ~its entire deposit-funded balance sheet, structurally floors roce_pct into single
digits regardless of real capital efficiency. Live-confirmed: JPM=3.85%, BAC=3.40%, WFC=3.03%,
C=3.87%, GS=12.55%, MS=4.21% (all real quality_metrics values) - the industrial curve scored
JPM/BAC/WFC/C around 15-19 despite GS's genuinely-higher 12.55% showing real cross-sectional
variation exists to reward. Same bug class as debt_to_equity_score/roa_score's bank/insurer
curve fixes (test_debt_to_equity_score_bank_insurer_curve_20260907.py,
test_roa_fcf_margin_score_bank_insurer_curve_20260907.py) - fixed the same way, branching on
DEPOSITORY_BANK_INDUSTRIES/INSURANCE_UNDERWRITER_INDUSTRIES.

Insurers get the same single blended curve precedent as those two fixes' INSURANCE_UNDERWRITER_
INDUSTRIES override: P&C underwriters (PGR/TRV/ALL live-confirmed roce_pct 5.72-11.79%) run
meaningfully higher than life insurers (MET/PRU live-confirmed ~0.82-0.85%).
"""

import pytest

from loaders.load_value_quality_growth_metrics import (
    DEPOSITORY_BANK_INDUSTRIES,
    INSURANCE_UNDERWRITER_INDUSTRIES,
    ValueQualityGrowthMetricsLoader,
)


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


def _make_loader(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    return loader


def _bank_row(
    stockholders_equity, total_liabilities, operating_income, income_tax_expense, pretax_income, long_term_debt=None
):
    # Same 34-column shape as test_debt_to_equity_score_bank_insurer_curve_20260907.py's fixture.
    # income_tax_expense/pretax_income set alongside operating_income so the anchor year is used
    # directly - avoids the DB fallback-query branch (see _compute_quality_metrics's own comment
    # near roic_tax_expense/roic_pretax_income/roic_operating_income), keeping roce_pct
    # deterministic under the fake, empty-fetchall DatabaseContext.
    return (
        stockholders_equity,  # 0
        total_liabilities,  # 1
        11_000_000_000.0,  # 2 total_assets
        330_000_000.0,  # 3 net_income
        1_500_000_000.0,  # 4 revenue
        operating_income,  # 5
        None,  # 6 current_assets
        None,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        None,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        150_000_000.0,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        None,  # 19 gross_profit
        long_term_debt,  # 20
        None,  # 21 cash_and_equivalents
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


class TestRoceScoreBankInsurerCurve:
    def test_bank_low_absolute_roce_scores_well_above_industrial_floor(self, monkeypatch):
        # JPM-shaped: capital_employed = 1B equity + 10B total_liabilities = 11B;
        # operating_income=$385M -> roce_pct=3.5%. Under the old industrial curve
        # ((8.0,40),...) this scores ~17.5; the bank curve ((3.0,40),(6.0,75),(10.0,100))
        # scores it meaningfully higher instead.
        loader = _make_loader(monkeypatch)
        loader._industry_cache = {"BANKCO": next(iter(DEPOSITORY_BANK_INDUSTRIES))}
        metrics = loader._compute_quality_metrics(
            "BANKCO",
            _bank_row(1_000_000_000.0, 10_000_000_000.0, 385_000_000.0, 80_000_000.0, 400_000_000.0),
            ev_metrics=None,
        )
        assert metrics["roce_pct"] == pytest.approx(3.5)
        old_industrial_score = loader._margin_curve(3.5, [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)])
        new_bank_score = loader._margin_curve(3.5, [(3.0, 40.0), (6.0, 75.0), (10.0, 100.0)])
        assert new_bank_score > old_industrial_score
        assert new_bank_score == 40.0 + (3.5 - 3.0) / (6.0 - 3.0) * (75.0 - 40.0)

    def test_insurer_roce_uses_its_own_curve(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        loader._industry_cache = {"INSURECO": next(iter(INSURANCE_UNDERWRITER_INDUSTRIES))}
        metrics = loader._compute_quality_metrics(
            "INSURECO",
            _bank_row(1_000_000_000.0, 10_000_000_000.0, 660_000_000.0, 80_000_000.0, 400_000_000.0),
            ev_metrics=None,
        )
        assert metrics["roce_pct"] == 6.0
        expected = 75.0 + (6.0 - 5.0) / (10.0 - 5.0) * (100.0 - 75.0)
        assert loader._margin_curve(6.0, [(2.0, 40.0), (5.0, 75.0), (10.0, 100.0)]) == expected

    def test_industrial_symbol_roce_curve_unchanged(self, monkeypatch):
        # Non-bank/insurer: debt_for_roic falls back to long_term_debt, not total_liabilities -
        # capital_employed = 1B equity + 9B long_term_debt = 10B; operating_income=$800M ->
        # roce_pct=8.0%, landing exactly on the industrial curve's first breakpoint.
        loader = _make_loader(monkeypatch)
        loader._industry_cache = {"INDCO": "Some Industrial Industry"}
        metrics = loader._compute_quality_metrics(
            "INDCO",
            _bank_row(
                1_000_000_000.0,
                10_000_000_000.0,
                800_000_000.0,
                80_000_000.0,
                400_000_000.0,
                long_term_debt=9_000_000_000.0,
            ),
            ev_metrics=None,
        )
        assert metrics["roce_pct"] == pytest.approx(8.0)
        assert loader._margin_curve(8.0, [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)]) == 40.0
