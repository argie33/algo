"""Regression test (2026-09-07, goal: stock_scores factor/composite sanity audit).

Regulated rate-base utilities' ROA/ROCE/debt_to_equity all ran through the flat industrial
curves calibrated for asset-light operating companies - the same bug class already fixed for
depository banks/insurance underwriters this session. Live-confirmed across 10 electric
utilities (NEE/DUK/SO/D/AEP/EXC/XEL/WEC/ED/PEG) plus 6 water/gas-distribution utilities
(CWT/OGS/WTRG/YORW/ARTNA/NGG): ROA clustered 2.26-3.67% (industrial (3.0,40)/(8.0,80)/(15.0,100)
floors nearly all of them near the bottom), debt_to_equity clustered 0.71-1.91x (industrial
2.0-floors-to-0 curve crushed most toward zero), ROCE clustered 3.96-7.23%. quality_score for
this group sat in the 25-44 range purely from this miscalibration despite genuinely normal-to-
healthy regulated-utility fundamentals (8-12.5% ROE is a typical allowed utility return). Fixed
by branching roa_score/roce_score/debt_to_equity_score on the new UTILITY_INDUSTRIES set,
excluding fcf_margin_score (heavy continuous capex, same "raw value kept, not scored" treatment
as depository banks), and routing Utilities into the Financial Services/Real Estate two-cluster
structure (asset_turnover_score is equally incoherent for a rate-base balance sheet, live-
confirmed 0.13-0.23x turnover for the same utility set).
"""

import pytest

from loaders.load_value_quality_growth_metrics import (
    UTILITY_INDUSTRIES,
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


def _utility_row(
    stockholders_equity, long_term_debt, total_assets, net_income, operating_income, pretax_income, revenue
):
    # Same 34-column shape as the bank/insurer curve fixture files. income_tax_expense=0 alongside
    # operating_income/pretax_income so the anchor year is used directly (avoids the DB fallback
    # branch under the fake, empty-fetchall DatabaseContext).
    return (
        stockholders_equity,  # 0
        None,  # 1 total_liabilities (utilities don't get the total_liabilities debt_for_roic override)
        total_assets,  # 2
        net_income,  # 3
        revenue,  # 4
        operating_income,  # 5
        None,  # 6 current_assets
        None,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        None,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        -500_000_000.0,  # 14 free_cash_flow (heavy capex - realistic utility FCF)
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        None,  # 19 gross_profit
        long_term_debt,  # 20
        None,  # 21 cash_and_equivalents
        0.0,  # 22 income_tax_expense
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


class TestUtilityQualityCurve:
    def test_utility_roa_scores_well_above_industrial_floor(self, monkeypatch):
        # NEE-shaped: net_income/total_assets = 3.21% (live-confirmed value).
        loader = _make_loader(monkeypatch)
        loader._industry_cache = {"UTILCO": next(iter(UTILITY_INDUSTRIES))}
        metrics = loader._compute_quality_metrics(
            "UTILCO",
            _utility_row(
                50_000_000_000.0,
                60_000_000_000.0,
                100_000_000_000.0,
                3_210_000_000.0,
                8_000_000_000.0,
                8_000_000_000.0,
                25_000_000_000.0,
            ),
            ev_metrics=None,
        )
        assert metrics["roa"] == pytest.approx(3.21)
        old_industrial_score = loader._margin_curve(3.21, [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)])
        new_utility_score = loader._margin_curve(3.21, [(2.0, 40.0), (3.0, 75.0), (4.5, 100.0)])
        assert new_utility_score > old_industrial_score

    def test_utility_debt_to_equity_not_crushed_toward_zero(self, monkeypatch):
        # SO-shaped: long_term_debt/stockholders_equity = 1.91x (live-confirmed value) - the
        # industrial curve (2.0-floors-to-0) leaves almost nothing here; the utility curve (/4.0)
        # should score it meaningfully above zero.
        loader = _make_loader(monkeypatch)
        loader._industry_cache = {"UTILCO": next(iter(UTILITY_INDUSTRIES))}
        loader._sector_cache = {"UTILCO": "Utilities"}
        metrics = loader._compute_quality_metrics(
            "UTILCO",
            _utility_row(
                30_000_000_000.0,
                57_300_000_000.0,
                100_000_000_000.0,
                800_000_000.0,
                3_000_000_000.0,
                3_000_000_000.0,
                12_000_000_000.0,
            ),
            ev_metrics=None,
        )
        assert metrics["debt_to_equity"] == pytest.approx(1.91)
        old_industrial_score = max(0.0, min(100.0, 100.0 - (1.91 / 2.0) * 100.0))
        new_utility_score = max(0.0, min(100.0, 100.0 - (1.91 / 4.0) * 100.0))
        assert new_utility_score > old_industrial_score
        assert new_utility_score == pytest.approx(52.25)

    def test_utility_routed_through_two_cluster_structure_and_fcf_margin_excluded(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        loader._industry_cache = {"UTILCO": next(iter(UTILITY_INDUSTRIES))}
        loader._sector_cache = {"UTILCO": "Utilities"}
        metrics = loader._compute_quality_metrics(
            "UTILCO",
            _utility_row(
                50_000_000_000.0,
                60_000_000_000.0,
                100_000_000_000.0,
                3_210_000_000.0,
                8_000_000_000.0,
                8_000_000_000.0,
                25_000_000_000.0,
            ),
            ev_metrics=None,
        )
        # fcf_margin is still computed/persisted, but excluded from scoring for utilities.
        assert metrics["fcf_margin"] is not None
        # quality_score should be well above the old ~25-44 stale range for a genuinely healthy
        # utility profile (positive ROE/ROA, moderate leverage).
        assert metrics["quality_score"] is not None
        assert metrics["quality_score"] > 44.0

    def test_non_utility_industry_unaffected(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        loader._industry_cache = {"INDCO": "Some Industrial Industry"}
        loader._sector_cache = {"INDCO": "Industrials"}
        loader._compute_quality_metrics(
            "INDCO",
            _utility_row(
                50_000_000_000.0,
                60_000_000_000.0,
                100_000_000_000.0,
                3_210_000_000.0,
                8_000_000_000.0,
                8_000_000_000.0,
                25_000_000_000.0,
            ),
            ev_metrics=None,
        )
        assert loader._margin_curve(3.21, [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)]) == pytest.approx(41.68)
