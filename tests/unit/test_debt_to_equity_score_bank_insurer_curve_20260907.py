"""Regression test (2026-09-07, goal: stock_scores factor/composite sanity audit).

debt_to_equity_score used the same 0.5/1.0/2.0x industrial-leverage curve for every sector,
even though the depository-bank/insurance-underwriter debt_for_roic override (see
loaders/helpers/vqg_quality.py's comment on that override) deliberately computes their
debt_to_equity using total_liabilities (deposits/policy reserves), which sits at 8-15x for a
healthy bank by construction. Live-verified: JPM/BAC/WFC all showed quality_score in the 28-39
range with debt_to_equity_score floored to 0.0 despite genuinely strong ROA/ROE/ROCE, because
the industrial curve floors anything >= 2.0x to 0. This zeroed ~25-27% of the Quality
safety_cluster_score for essentially every bank/insurer in the universe regardless of actual
balance-sheet health.

Fixed by branching debt_to_equity_score on the same DEPOSITORY_BANK_INDUSTRIES/
INSURANCE_UNDERWRITER_INDUSTRIES industry check the debt_for_roic override already uses,
recalibrated to each sector's typical deposit/reserve-inclusive leverage range instead of the
industrial 0.5/1.0/2.0x scale.
"""

from loaders.helpers.vqg_quality_batch import QualityBatchMixin
from loaders.load_value_quality_growth_metrics import (
    DEPOSITORY_BANK_INDUSTRIES,
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


def _bank_row():
    # Same 34-column shape as test_quality_roe_negative_equity_score_floor_20260905.py's fixture.
    # total_liabilities=$10B, stockholders_equity=$1B -> debt_to_equity=10.0 after the
    # depository-bank debt_for_roic override, the same magnitude JPM/BAC/WFC live-verified at.
    return (
        1_000_000_000.0,  # 0 stockholders_equity
        10_000_000_000.0,  # 1 total_liabilities
        11_000_000_000.0,  # 2 total_assets
        200_000_000.0,  # 3 net_income
        1_500_000_000.0,  # 4 revenue
        None,  # 5 operating_income
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


class TestDebtToEquityScoreBankInsurerCurve:
    def test_bank_debt_to_equity_is_deposit_inclusive_and_high(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        loader._industry_cache = {"BANKCO": next(iter(DEPOSITORY_BANK_INDUSTRIES))}
        metrics = loader._compute_quality_metrics("BANKCO", _bank_row(), ev_metrics=None)

        assert metrics["debt_to_equity"] == 10.0

    def test_bank_debt_to_equity_score_not_floored_to_zero(self, monkeypatch):
        # Before the fix, any D/E >= 2.0 (every deposit-funded bank, by construction) floored
        # to 0.0 under the industrial curve. The bank-specific curve (/20.0) instead scores a
        # real, well-capitalized bank's 10.0x leverage around the middle of the range.
        loader = _make_loader(monkeypatch)
        import loaders.load_value_quality_growth_metrics as mod

        loader._industry_cache = {"BANKCO": next(iter(DEPOSITORY_BANK_INDUSTRIES))}
        loader._sector_cache = {"BANKCO": "Financial Services"}

        captured_calls = []
        # _weighted_avg now lives on QualityBatchMixin (extracted 2026-09-08, file-size
        # ratchet), not directly on ValueQualityGrowthMetricsLoader's own __dict__.
        original_weighted_avg = QualityBatchMixin.__dict__["_weighted_avg"].__func__

        def spy_weighted_avg(components, min_weight_pct=0.0):
            captured_calls.append(components)
            return original_weighted_avg(components, min_weight_pct=min_weight_pct)

        monkeypatch.setattr(mod.ValueQualityGrowthMetricsLoader, "_weighted_avg", staticmethod(spy_weighted_avg))

        loader._compute_quality_metrics("BANKCO", _bank_row(), ev_metrics=None)

        # REWRITE 2026-09-07 (sector-neutral-zscore rewrite): the old Financial Services
        # two-cluster branch (profitability cluster called first, safety cluster second) was
        # collapsed to the same single flat 8-component call every sector uses -
        # debt_to_equity_score is the 5th component: [roe, roa, roce, fcf_margin,
        # debt_to_equity, margin_volatility, asset_turnover, gross_profitability].
        flat_call = captured_calls[0]
        debt_to_equity_score = flat_call[4][0]

        assert debt_to_equity_score is not None
        assert debt_to_equity_score == 50.0  # 100 - (10.0 / 20.0) * 100
        assert debt_to_equity_score > 0.0
